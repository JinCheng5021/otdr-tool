import type { PutBlobResult } from '@vercel/blob';
import { upload } from '@vercel/blob/client';
import JSZip from 'jszip';

const MULTIPART_UPLOAD_THRESHOLD_BYTES = 100 * 1024 * 1024;

export interface BlobInputSession {
  upload_id: string;
  pathname: string;
  maximum_size_in_bytes: number;
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

export async function requestBlobInput(): Promise<BlobInputSession> {
  const response = await fetch('/trace/api/blob-input', { method: 'POST' });
  if (!response.ok) {
    throw await responseError(response, 'Không thể khởi tạo phiên tải tệp.');
  }

  const value: unknown = await response.json();
  if (
    !value ||
    typeof value !== 'object' ||
    typeof (value as BlobInputSession).upload_id !== 'string' ||
    typeof (value as BlobInputSession).pathname !== 'string' ||
    typeof (value as BlobInputSession).maximum_size_in_bytes !== 'number' ||
    (value as BlobInputSession).maximum_size_in_bytes <= 0
  ) {
    throw new Error('Phản hồi khởi tạo Vercel Blob không hợp lệ.');
  }

  return value as BlobInputSession;
}

export async function createBatchZip(
  files: File[],
  maximumSizeInBytes: number,
  onProgress?: (percentage: number) => void,
): Promise<Blob> {
  if (files.length === 0) {
    throw new Error('Vui lòng chọn ít nhất 1 file để xuất báo cáo.');
  }

  const zip = new JSZip();
  const width = Math.max(6, String(files.length).length);
  files.forEach((file, index) => {
    const directory = String(index + 1).padStart(width, '0');
    zip.file(`${directory}/${file.name}`, file, { createFolders: true });
  });

  const batch = await zip.generateAsync(
    {
      type: 'blob',
      compression: 'DEFLATE',
      compressionOptions: { level: 6 },
      mimeType: 'application/zip',
    },
    (metadata) => onProgress?.(Math.round(metadata.percent)),
  );

  if (batch.size > maximumSizeInBytes) {
    throw new Error(
      `Tệp ZIP vượt quá giới hạn ${maximumSizeInBytes} byte của hệ thống.`,
    );
  }
  return batch;
}

export async function uploadBatchToBlob(
  batch: Blob,
  session: BlobInputSession,
  onProgress?: (percentage: number) => void,
): Promise<PutBlobResult> {
  const result = await upload(session.pathname, batch, {
    access: 'private',
    handleUploadUrl: '/api/blob/upload',
    contentType: 'application/zip',
    multipart: batch.size > MULTIPART_UPLOAD_THRESHOLD_BYTES,
    clientPayload: JSON.stringify({ uploadId: session.upload_id }),
    onUploadProgress: ({ percentage }) => onProgress?.(Math.round(percentage)),
  });

  if (result.pathname !== session.pathname) {
    throw new Error('Vercel Blob trả về pathname không khớp với phiên tải tệp.');
  }
  return result;
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
