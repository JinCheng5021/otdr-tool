import type { PutBlobResult } from '@vercel/blob';
import { upload } from '@vercel/blob/client';

const MULTIPART_UPLOAD_THRESHOLD_BYTES = 100 * 1024 * 1024;
const MAX_CONCURRENT_UPLOADS = 3;
const INPUT_EXTENSION_PRIORITY = ['.sor', '.msor', '.trc'] as const;

export type SupportedInputExtension =
  (typeof INPUT_EXTENSION_PRIORITY)[number];

export interface BlobInputFile {
  original_name: string;
  pathname: string;
  size: number;
}

export interface BlobInputSession {
  upload_id: string;
  selected_extension: SupportedInputExtension;
  files: BlobInputFile[];
  ignored_count: number;
  maximum_total_size_in_bytes: number;
}

export interface BlobConversionResult {
  upload_id: string;
  status: 'succeeded';
  filename: string;
  output_pathname: string;
  content_type: string;
  size: number;
}

interface SignedDownloadResult {
  download_url: string;
  valid_until: number;
}

export interface InputFileSelection {
  selectedExtension: SupportedInputExtension;
  selectedFiles: File[];
  ignoredFiles: File[];
}

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf('.');
  return dot >= 0 ? filename.slice(dot).toLowerCase() : '';
}

export function selectInputFiles(files: File[]): InputFileSelection {
  const selectedExtension = INPUT_EXTENSION_PRIORITY.find((extension) =>
    files.some((file) => extensionOf(file.name) === extension),
  );
  if (!selectedExtension) {
    throw new Error('Không có file .sor, .msor hoặc .trc hợp lệ.');
  }

  return {
    selectedExtension,
    selectedFiles: files.filter(
      (file) => extensionOf(file.name) === selectedExtension,
    ),
    ignoredFiles: files.filter(
      (file) => extensionOf(file.name) !== selectedExtension,
    ),
  };
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  try {
    const payload = await response.json();
    if (
      payload &&
      typeof payload === 'object' &&
      typeof (payload as { detail?: unknown }).detail === 'string'
    ) {
      return new Error((payload as { detail: string }).detail);
    }
  } catch {
    // Keep the stable fallback when the server did not return JSON.
  }
  return new Error(fallback);
}

export async function requestBlobInput(files: File[]): Promise<BlobInputSession> {
  const response = await fetch('/trace/api/blob-input', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      files: files.map((file) => ({ name: file.name, size: file.size })),
    }),
  });
  if (!response.ok) {
    throw await responseError(response, 'Không thể khởi tạo phiên tải tệp.');
  }

  const value: unknown = await response.json();
  if (
    !value ||
    typeof value !== 'object' ||
    typeof (value as BlobInputSession).upload_id !== 'string' ||
    !INPUT_EXTENSION_PRIORITY.includes(
      (value as BlobInputSession).selected_extension,
    ) ||
    !Array.isArray((value as BlobInputSession).files) ||
    typeof (value as BlobInputSession).ignored_count !== 'number' ||
    typeof (value as BlobInputSession).maximum_total_size_in_bytes !== 'number' ||
    (value as BlobInputSession).maximum_total_size_in_bytes <= 0
  ) {
    throw new Error('Phản hồi khởi tạo Vercel Blob không hợp lệ.');
  }

  const session = value as BlobInputSession;
  if (
    session.files.length !== files.length ||
    session.files.some(
      (item, index) =>
        typeof item?.original_name !== 'string' ||
        typeof item?.pathname !== 'string' ||
        typeof item?.size !== 'number' ||
        item.original_name !== files[index].name ||
        item.size !== files[index].size,
    )
  ) {
    throw new Error('Danh sách file Vercel Blob không khớp yêu cầu tải lên.');
  }
  return session;
}

export async function uploadFilesToBlob(
  files: File[],
  session: BlobInputSession,
  onProgress?: (percentage: number) => void,
): Promise<PutBlobResult[]> {
  if (files.length === 0 || files.length !== session.files.length) {
    throw new Error('Danh sách file tải lên không hợp lệ.');
  }

  const uploadedBytes = new Array(files.length).fill(0);
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
  const results = new Array<PutBlobResult>(files.length);
  let nextIndex = 0;

  const reportProgress = (): void => {
    if (!onProgress) return;
    const completedBytes = uploadedBytes.reduce((sum, size) => sum + size, 0);
    const percentage = totalBytes > 0
      ? Math.round((completedBytes / totalBytes) * 100)
      : 100;
    onProgress(Math.min(100, percentage));
  };

  const worker = async (): Promise<void> => {
    while (nextIndex < files.length) {
      const index = nextIndex;
      nextIndex += 1;
      const file = files[index];
      const descriptor = session.files[index];
      if (
        descriptor.original_name !== file.name ||
        descriptor.size !== file.size
      ) {
        throw new Error('Thông tin file tải lên không khớp phiên Vercel Blob.');
      }

      const result = await upload(descriptor.pathname, file, {
        access: 'private',
        handleUploadUrl: '/api/blob/upload',
        contentType: 'application/octet-stream',
        multipart: file.size > MULTIPART_UPLOAD_THRESHOLD_BYTES,
        clientPayload: JSON.stringify({ uploadId: session.upload_id }),
        onUploadProgress: ({ loaded }) => {
          uploadedBytes[index] = Math.min(file.size, loaded);
          reportProgress();
        },
      });

      if (result.pathname !== descriptor.pathname) {
        throw new Error(
          'Vercel Blob trả về pathname không khớp với phiên tải tệp.',
        );
      }
      uploadedBytes[index] = file.size;
      results[index] = result;
      reportProgress();
    }
  };

  const workerCount = Math.min(MAX_CONCURRENT_UPLOADS, files.length);
  await Promise.all(
    Array.from({ length: workerCount }, () => worker()),
  );
  return results;
}

export async function parseBlobConversionResponse(
  response: Response,
): Promise<BlobConversionResult> {
  if (!response.ok) {
    throw await responseError(response, 'Có lỗi xảy ra khi xử lý file.');
  }

  const value: unknown = await response.json();
  if (
    !value ||
    typeof value !== 'object' ||
    (value as BlobConversionResult).status !== 'succeeded' ||
    typeof (value as BlobConversionResult).filename !== 'string' ||
    typeof (value as BlobConversionResult).output_pathname !== 'string'
  ) {
    throw new Error('Phản hồi chuyển đổi từ Vercel Blob không hợp lệ.');
  }
  return value as BlobConversionResult;
}

export async function requestSignedDownload(
  outputPathname: string,
): Promise<SignedDownloadResult> {
  const response = await fetch('/api/blob/signed-get', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pathname: outputPathname }),
  });
  if (!response.ok) {
    throw await responseError(response, 'Không thể tạo liên kết tải báo cáo.');
  }

  const value: unknown = await response.json();
  if (
    !value ||
    typeof value !== 'object' ||
    typeof (value as SignedDownloadResult).download_url !== 'string' ||
    typeof (value as SignedDownloadResult).valid_until !== 'number'
  ) {
    throw new Error('Phản hồi liên kết tải báo cáo không hợp lệ.');
  }
  return value as SignedDownloadResult;
}

export function downloadFromSignedUrl(downloadUrl: string, filename: string): void {
  const anchor = document.createElement('a');
  anchor.style.display = 'none';
  anchor.href = downloadUrl;
  anchor.download = filename;
  anchor.referrerPolicy = 'no-referrer';
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
}
