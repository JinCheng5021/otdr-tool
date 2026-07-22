const UUID_PATTERN =
  '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';

const MANAGED_PATH_PATTERN = new RegExp(
  `^(?<kind>input|output)/(?<year>\\d{4})/(?<month>\\d{2})/(?<day>\\d{2})/` +
    `(?<uploadId>${UUID_PATTERN})/(?<filename>[A-Za-z0-9._-]+)$`,
);

export const MAXIMUM_BLOB_SIZE_IN_BYTES = 250 * 1024 * 1024;
export const CLIENT_UPLOAD_TOKEN_LIFETIME_MS = 15 * 60 * 1000;
export const SIGNED_DOWNLOAD_LIFETIME_MS = 5 * 60 * 1000;

export class BlobRequestValidationError extends Error {}

export interface ManagedBlobPath {
  pathname: string;
  kind: 'input' | 'output';
  uploadId: string;
  filename: string;
}

function parseManagedPath(pathname: unknown): ManagedBlobPath {
  if (typeof pathname !== 'string' || pathname !== pathname.trim()) {
    throw new BlobRequestValidationError('Invalid Blob pathname.');
  }

  const prefix = 'otdr/';
  if (!pathname.startsWith(prefix)) {
    throw new BlobRequestValidationError('Invalid managed Blob pathname.');
  }

  const match = MANAGED_PATH_PATTERN.exec(pathname.slice(prefix.length));
  const groups = match?.groups;
  if (!groups) {
    throw new BlobRequestValidationError('Invalid managed Blob pathname.');
  }

  const year = Number(groups.year);
  const month = Number(groups.month);
  const day = Number(groups.day);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    year < 1 ||
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    throw new BlobRequestValidationError('Invalid date in Blob pathname.');
  }

  return {
    pathname,
    kind: groups.kind as 'input' | 'output',
    uploadId: groups.uploadId,
    filename: groups.filename,
  };
}

export function parseInputPathname(pathname: unknown): ManagedBlobPath {
  const parsed = parseManagedPath(pathname);
  if (parsed.kind !== 'input' || parsed.filename !== 'batch.zip') {
    throw new BlobRequestValidationError(
      'Input pathname must point to a managed batch.zip.',
    );
  }
  return parsed;
}

export function parseOutputPathname(pathname: unknown): ManagedBlobPath {
  const parsed = parseManagedPath(pathname);
  if (parsed.kind !== 'output' || !parsed.filename.toLowerCase().endsWith('.xlsx')) {
    throw new BlobRequestValidationError(
      'Output pathname must point to a managed XLSX file.',
    );
  }
  return parsed;
}

export function parseUploadClientPayload(clientPayload: string | null): string {
  if (clientPayload === null) {
    throw new BlobRequestValidationError('Missing upload client payload.');
  }

  let value: unknown;
  try {
    value = JSON.parse(clientPayload);
  } catch {
    throw new BlobRequestValidationError('Invalid upload client payload.');
  }

  if (
    typeof value !== 'object' ||
    value === null ||
    Array.isArray(value) ||
    typeof (value as { uploadId?: unknown }).uploadId !== 'string'
  ) {
    throw new BlobRequestValidationError('Invalid upload client payload.');
  }

  return (value as { uploadId: string }).uploadId;
}
