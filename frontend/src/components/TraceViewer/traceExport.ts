const MAX_CONCURRENT_UPLOADS = 3;
const MAX_UPLOAD_ATTEMPTS = 3;
const UPLOAD_REQUEST_TIMEOUT_MS = 10 * 60 * 1000;
const INPUT_EXTENSION_PRIORITY = ['.sor', '.msor', '.trc'] as const;

export type SupportedInputExtension =
  (typeof INPUT_EXTENSION_PRIORITY)[number];

export interface StorageInputFile {
  original_name: string;
  pathname: string;
  size: number;
}

export interface StorageInputSession {
  upload_id: string;
  selected_extension: SupportedInputExtension;
  files: StorageInputFile[];
  ignored_count: number;
  maximum_total_size_in_bytes: number;
  upload_authorization: string;
  authorization_valid_until: number;
}

export interface StorageConversionResult {
  upload_id: string;
  status: 'succeeded';
  filename: string;
  output_pathname: string;
  content_type: string;
  size: number;
}

export interface StorageUploadResult {
  pathname: string;
  size: number;
  content_type: string;
}

interface SignedDownloadResult {
  download_url: string;
  valid_until: number;
}

interface SingleUploadPlan {
  mode: 'single';
  pathname: string;
  size: number;
  upload_url: string;
  valid_until: number;
  required_headers: Record<string, string>;
}

interface MultipartPartPlan {
  part_number: number;
  size: number;
}

interface MultipartUploadPlan {
  mode: 'multipart';
  pathname: string;
  size: number;
  multipart_upload_id: string;
  part_size: number;
  parts: MultipartPartPlan[];
  valid_until: number;
}

type UploadPlan = SingleUploadPlan | MultipartUploadPlan;

interface MultipartPartUploadPlan {
  pathname: string;
  size: number;
  multipart_upload_id: string;
  part_number: number;
  part_size: number;
  upload_url: string;
  valid_until: number;
}

export interface InputFileSelection {
  selectedExtension: SupportedInputExtension;
  selectedFiles: File[];
  ignoredFiles: File[];
}

interface XhrUploadResult {
  etag: string | null;
  alreadyExists: boolean;
}

class UploadRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly retryable: boolean,
  ) {
    super(message);
  }
}

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf('.');
  return dot >= 0 ? filename.slice(dot).toLowerCase() : '';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isCloudflareR2Url(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  try {
    const parsed = new URL(value);
    return (
      parsed.protocol === 'https:' &&
      parsed.hostname.endsWith('.r2.cloudflarestorage.com')
    );
  } catch {
    return false;
  }
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
      isRecord(payload) &&
      typeof payload.detail === 'string'
    ) {
      return new Error(payload.detail);
    }
  } catch {
    // Keep the stable fallback when the server did not return JSON.
  }
  return new Error(fallback);
}

export async function requestStorageInput(
  files: File[],
): Promise<StorageInputSession> {
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
    !isRecord(value) ||
    typeof value.upload_id !== 'string' ||
    !INPUT_EXTENSION_PRIORITY.includes(
      value.selected_extension as SupportedInputExtension,
    ) ||
    !Array.isArray(value.files) ||
    typeof value.ignored_count !== 'number' ||
    typeof value.maximum_total_size_in_bytes !== 'number' ||
    value.maximum_total_size_in_bytes <= 0 ||
    typeof value.upload_authorization !== 'string' ||
    !value.upload_authorization ||
    typeof value.authorization_valid_until !== 'number'
  ) {
    throw new Error('Phản hồi khởi tạo Cloudflare R2 không hợp lệ.');
  }

  const session = value as unknown as StorageInputSession;
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
    throw new Error('Danh sách file Cloudflare R2 không khớp yêu cầu tải lên.');
  }
  return session;
}

function storageRequestBody(
  descriptor: StorageInputFile,
  session: StorageInputSession,
): Record<string, unknown> {
  return {
    pathname: descriptor.pathname,
    upload_id: session.upload_id,
    size: descriptor.size,
    content_type: 'application/octet-stream',
    upload_authorization: session.upload_authorization,
  };
}

async function requestUploadPlan(
  descriptor: StorageInputFile,
  session: StorageInputSession,
  signal?: AbortSignal,
): Promise<UploadPlan> {
  const response = await fetch('/trace/api/storage/prepare-upload', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(storageRequestBody(descriptor, session)),
    signal,
  });
  if (!response.ok) {
    throw await responseError(
      response,
      'Không thể tạo liên kết tải file lên Cloudflare R2.',
    );
  }

  const value: unknown = await response.json();
  if (
    !isRecord(value) ||
    value.pathname !== descriptor.pathname ||
    value.size !== descriptor.size ||
    typeof value.valid_until !== 'number'
  ) {
    throw new Error('Kế hoạch tải file Cloudflare R2 không hợp lệ.');
  }

  if (value.mode === 'single') {
    if (
      !isCloudflareR2Url(value.upload_url) ||
      !isRecord(value.required_headers) ||
      value.required_headers['Content-Type'] !== 'application/octet-stream' ||
      value.required_headers['If-None-Match'] !== '*'
    ) {
      throw new Error('Liên kết tải file Cloudflare R2 không hợp lệ.');
    }
    return value as unknown as SingleUploadPlan;
  }

  if (
    value.mode !== 'multipart' ||
    typeof value.multipart_upload_id !== 'string' ||
    !value.multipart_upload_id ||
    typeof value.part_size !== 'number' ||
    value.part_size <= 0 ||
    !Array.isArray(value.parts) ||
    value.parts.length === 0
  ) {
    throw new Error('Kế hoạch multipart Cloudflare R2 không hợp lệ.');
  }

  let plannedSize = 0;
  for (let index = 0; index < value.parts.length; index += 1) {
    const item = value.parts[index];
    if (
      !isRecord(item) ||
      item.part_number !== index + 1 ||
      typeof item.size !== 'number' ||
      item.size <= 0
    ) {
      throw new Error('Danh sách multipart Cloudflare R2 không hợp lệ.');
    }
    plannedSize += item.size;
  }
  if (plannedSize !== descriptor.size) {
    throw new Error('Kích thước multipart Cloudflare R2 không khớp file.');
  }
  return value as unknown as MultipartUploadPlan;
}

async function requestMultipartPartUrl(
  descriptor: StorageInputFile,
  session: StorageInputSession,
  plan: MultipartUploadPlan,
  part: MultipartPartPlan,
  signal?: AbortSignal,
): Promise<string> {
  const response = await fetch('/trace/api/storage/multipart-part-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...storageRequestBody(descriptor, session),
      multipart_upload_id: plan.multipart_upload_id,
      part_number: part.part_number,
      part_size: part.size,
    }),
    signal,
  });
  if (!response.ok) {
    throw await responseError(
      response,
      'Không thể tạo liên kết tải phần file lên Cloudflare R2.',
    );
  }
  const value: unknown = await response.json();
  if (
    !isRecord(value) ||
    value.pathname !== descriptor.pathname ||
    value.size !== descriptor.size ||
    value.multipart_upload_id !== plan.multipart_upload_id ||
    value.part_number !== part.part_number ||
    value.part_size !== part.size ||
    !isCloudflareR2Url(value.upload_url) ||
    typeof value.valid_until !== 'number'
  ) {
    throw new Error('Liên kết multipart Cloudflare R2 không hợp lệ.');
  }
  return (value as unknown as MultipartPartUploadPlan).upload_url;
}

function putWithProgress(
  uploadUrl: string,
  payload: Blob,
  headers: Record<string, string>,
  onProgress: (loaded: number) => void,
  signal: AbortSignal,
): Promise<XhrUploadResult> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    let settled = false;
    const cleanup = (): void => {
      signal.removeEventListener('abort', abortRequest);
    };
    const finish = (callback: () => void): void => {
      if (settled) return;
      settled = true;
      cleanup();
      callback();
    };
    const abortRequest = (): void => request.abort();
    if (signal.aborted) {
      reject(new UploadRequestError(
        'Đã hủy tải file lên Cloudflare R2.',
        0,
        false,
      ));
      return;
    }
    request.open('PUT', uploadUrl, true);
    request.timeout = UPLOAD_REQUEST_TIMEOUT_MS;
    Object.entries(headers).forEach(([name, value]) => {
      request.setRequestHeader(name, value);
    });
    request.upload.onprogress = (event) => {
      onProgress(Math.min(payload.size, event.loaded));
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        finish(() => resolve({
            etag: request.getResponseHeader('ETag'),
            alreadyExists: false,
          }));
        return;
      }
      if (request.status === 412) {
        finish(() => resolve({ etag: null, alreadyExists: true }));
        return;
      }
      finish(() => reject(new UploadRequestError(
        `Cloudflare R2 từ chối tải file (HTTP ${request.status}).`,
        request.status,
        request.status === 400 || request.status === 403 ||
          request.status === 408 || request.status === 429 ||
          request.status >= 500,
      )));
    };
    request.onerror = () => finish(() => reject(new UploadRequestError(
      'Mất kết nối khi tải file lên Cloudflare R2.',
      0,
      true,
    )));
    request.ontimeout = () => finish(() => reject(new UploadRequestError(
      'Quá thời gian tải file lên Cloudflare R2.',
      0,
      true,
    )));
    request.onabort = () => finish(() => reject(new UploadRequestError(
      'Đã hủy tải file lên Cloudflare R2.',
      0,
      false,
    )));
    signal.addEventListener('abort', abortRequest, { once: true });
    request.send(payload);
  });
}

function retryDelay(attempt: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      signal.removeEventListener('abort', abortDelay);
      resolve();
    }, 250 * (2 ** attempt));
    const abortDelay = (): void => {
      window.clearTimeout(timeoutId);
      reject(new UploadRequestError(
        'Đã hủy tải file lên Cloudflare R2.',
        0,
        false,
      ));
    };
    if (signal.aborted) {
      abortDelay();
      return;
    }
    signal.addEventListener('abort', abortDelay, { once: true });
  });
}

async function putWithRetry(
  uploadUrlFactory: (attempt: number) => Promise<string>,
  payload: Blob,
  headers: Record<string, string>,
  onProgress: (loaded: number) => void,
  signal: AbortSignal,
): Promise<XhrUploadResult> {
  let lastError: unknown;
  for (let attempt = 0; attempt < MAX_UPLOAD_ATTEMPTS; attempt += 1) {
    try {
      const uploadUrl = await uploadUrlFactory(attempt);
      return await putWithProgress(
        uploadUrl,
        payload,
        headers,
        onProgress,
        signal,
      );
    } catch (error) {
      lastError = error;
      if (
        !(error instanceof UploadRequestError) ||
        !error.retryable ||
        attempt === MAX_UPLOAD_ATTEMPTS - 1
      ) {
        throw error;
      }
      onProgress(0);
      await retryDelay(attempt, signal);
    }
  }
  throw lastError;
}

async function verifyUploadedObject(
  descriptor: StorageInputFile,
  session: StorageInputSession,
  signal?: AbortSignal,
): Promise<StorageUploadResult> {
  const response = await fetch('/trace/api/storage/verify-upload', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(storageRequestBody(descriptor, session)),
    signal,
  });
  if (!response.ok) {
    throw await responseError(response, 'Cloudflare R2 không xác minh được file.');
  }
  const value: unknown = await response.json();
  if (
    !isRecord(value) ||
    value.pathname !== descriptor.pathname ||
    value.size !== descriptor.size ||
    typeof value.content_type !== 'string'
  ) {
    throw new Error('Phản hồi xác minh Cloudflare R2 không hợp lệ.');
  }
  return value as unknown as StorageUploadResult;
}

async function completeMultipartUpload(
  descriptor: StorageInputFile,
  session: StorageInputSession,
  plan: MultipartUploadPlan,
  parts: Array<{ part_number: number; etag: string }>,
  signal?: AbortSignal,
): Promise<StorageUploadResult> {
  const response = await fetch('/trace/api/storage/complete-multipart', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...storageRequestBody(descriptor, session),
      multipart_upload_id: plan.multipart_upload_id,
      parts,
    }),
    signal,
  });
  if (!response.ok) {
    throw await responseError(
      response,
      'Không thể hoàn tất multipart upload Cloudflare R2.',
    );
  }
  const value: unknown = await response.json();
  if (
    !isRecord(value) ||
    value.pathname !== descriptor.pathname ||
    value.size !== descriptor.size ||
    typeof value.content_type !== 'string'
  ) {
    throw new Error('Phản hồi multipart Cloudflare R2 không hợp lệ.');
  }
  return value as unknown as StorageUploadResult;
}

async function abortMultipartUpload(
  descriptor: StorageInputFile,
  session: StorageInputSession,
  plan: MultipartUploadPlan,
): Promise<void> {
  try {
    const response = await fetch('/trace/api/storage/abort-multipart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...storageRequestBody(descriptor, session),
        multipart_upload_id: plan.multipart_upload_id,
      }),
    });
    if (!response.ok) {
      throw new Error('Cloudflare R2 không xác nhận hủy multipart upload.');
    }
  } catch {
    // R2 lifecycle remains the final cleanup guard for abandoned uploads.
  }
}

async function uploadSingleFile(
  file: File,
  descriptor: StorageInputFile,
  session: StorageInputSession,
  plan: SingleUploadPlan,
  onProgress: (loaded: number) => void,
  signal: AbortSignal,
): Promise<StorageUploadResult> {
  try {
    const result = await putWithRetry(
      async (attempt) => {
        if (attempt === 0) return plan.upload_url;
        const refreshed = await requestUploadPlan(
          descriptor,
          session,
          signal,
        );
        if (refreshed.mode !== 'single') {
          throw new Error('Kế hoạch tải lại Cloudflare R2 không hợp lệ.');
        }
        return refreshed.upload_url;
      },
      file,
      plan.required_headers,
      onProgress,
      signal,
    );
    if (!result.alreadyExists) {
      return {
        pathname: descriptor.pathname,
        size: descriptor.size,
        content_type: 'application/octet-stream',
      };
    }
  } catch (uploadError) {
    if (signal.aborted) throw uploadError;
    try {
      return await verifyUploadedObject(descriptor, session, signal);
    } catch {
      throw uploadError;
    }
  }
  return verifyUploadedObject(descriptor, session, signal);
}

async function uploadMultipartFile(
  file: File,
  descriptor: StorageInputFile,
  session: StorageInputSession,
  plan: MultipartUploadPlan,
  onProgress: (loaded: number) => void,
  signal: AbortSignal,
): Promise<StorageUploadResult> {
  const completedParts: Array<{ part_number: number; etag: string }> = [];
  let completedBytes = 0;
  try {
    for (const part of plan.parts) {
      const partStart = completedBytes;
      const payload = file.slice(partStart, partStart + part.size);
      const result = await putWithRetry(
        () => requestMultipartPartUrl(
          descriptor,
          session,
          plan,
          part,
          signal,
        ),
        payload,
        {},
        (loaded) => onProgress(partStart + loaded),
        signal,
      );
      if (!result.etag) {
        throw new Error(
          'Cloudflare R2 không trả ETag cho một phần multipart. Kiểm tra CORS.',
        );
      }
      completedParts.push({
        part_number: part.part_number,
        etag: result.etag,
      });
      completedBytes = partStart + part.size;
      onProgress(completedBytes);
    }
    return await completeMultipartUpload(
      descriptor,
      session,
      plan,
      completedParts,
      signal,
    );
  } catch (uploadError) {
    if (signal.aborted) {
      await abortMultipartUpload(descriptor, session, plan);
      throw uploadError;
    }
    try {
      return await verifyUploadedObject(descriptor, session, signal);
    } catch {
      await abortMultipartUpload(descriptor, session, plan);
      throw uploadError;
    }
  }
}

export async function uploadFilesToStorage(
  files: File[],
  session: StorageInputSession,
  onProgress?: (percentage: number) => void,
): Promise<StorageUploadResult[]> {
  if (files.length === 0 || files.length !== session.files.length) {
    throw new Error('Danh sách file tải lên không hợp lệ.');
  }

  const uploadedBytes = new Array(files.length).fill(0);
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
  const results = new Array<StorageUploadResult>(files.length);
  let nextIndex = 0;
  const uploadController = new AbortController();

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
        throw new Error(
          'Thông tin file tải lên không khớp phiên Cloudflare R2.',
        );
      }

      const plan = await requestUploadPlan(
        descriptor,
        session,
        uploadController.signal,
      );
      const updateFileProgress = (loaded: number): void => {
        uploadedBytes[index] = Math.min(file.size, loaded);
        reportProgress();
      };
      results[index] = plan.mode === 'single'
        ? await uploadSingleFile(
          file,
          descriptor,
          session,
          plan,
          updateFileProgress,
          uploadController.signal,
        )
        : await uploadMultipartFile(
          file,
          descriptor,
          session,
          plan,
          updateFileProgress,
          uploadController.signal,
        );

      uploadedBytes[index] = file.size;
      reportProgress();
    }
  };

  const workerCount = Math.min(MAX_CONCURRENT_UPLOADS, files.length);
  const primaryFailures: unknown[] = [];
  const outcomes = await Promise.allSettled(
    Array.from({ length: workerCount }, async () => {
      try {
        await worker();
      } catch (error) {
        if (!uploadController.signal.aborted) {
          primaryFailures.push(error);
          uploadController.abort();
        }
        throw error;
      }
    }),
  );
  const failure = outcomes.find(
    (outcome): outcome is PromiseRejectedResult => outcome.status === 'rejected',
  );
  if (primaryFailures.length > 0) throw primaryFailures[0];
  if (failure) throw failure.reason;
  return results;
}

export async function parseStorageConversionResponse(
  response: Response,
): Promise<StorageConversionResult> {
  if (!response.ok) {
    throw await responseError(response, 'Có lỗi xảy ra khi xử lý file.');
  }

  const value: unknown = await response.json();
  if (
    !isRecord(value) ||
    value.status !== 'succeeded' ||
    typeof value.filename !== 'string' ||
    typeof value.output_pathname !== 'string'
  ) {
    throw new Error('Phản hồi chuyển đổi từ Cloudflare R2 không hợp lệ.');
  }
  return value as unknown as StorageConversionResult;
}

export async function requestSignedDownload(
  outputPathname: string,
): Promise<SignedDownloadResult> {
  const response = await fetch('/trace/api/storage/download-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pathname: outputPathname }),
  });
  if (!response.ok) {
    throw await responseError(response, 'Không thể tạo liên kết tải báo cáo.');
  }

  const value: unknown = await response.json();
  if (
    !isRecord(value) ||
    !isCloudflareR2Url(value.download_url) ||
    typeof value.valid_until !== 'number'
  ) {
    throw new Error('Phản hồi liên kết tải báo cáo không hợp lệ.');
  }
  return value as unknown as SignedDownloadResult;
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
