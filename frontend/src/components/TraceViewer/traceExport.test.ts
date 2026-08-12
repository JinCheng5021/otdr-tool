import {
  downloadFromSignedUrl,
  parseStorageConversionResponse,
  requestSignedDownload,
  requestStorageInput,
  selectInputFiles,
  uploadFilesToStorage,
} from './traceExport';

const uploadId = '123e4567-e89b-12d3-a456-426614174000';
const uploadAuthorization = 'signed-session-token';
const inputPath = `otdr/input/2026/07/22/${uploadId}/000001-first.sor`;
const r2Base = 'https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com';

function mockJsonResponse(body: unknown, ok = true): Response {
  return {
    ok,
    json: jest.fn().mockResolvedValue(body),
  } as unknown as Response;
}

function storageSession(files: File[]) {
  return {
    upload_id: uploadId,
    selected_extension: '.sor' as const,
    files: files.map((file, index) => ({
      original_name: file.name,
      pathname: `otdr/input/2026/07/22/${uploadId}/${String(index + 1).padStart(6, '0')}-${file.name}`,
      size: file.size,
    })),
    ignored_count: 0,
    maximum_total_size_in_bytes: 250 * 1024 * 1024,
    upload_authorization: uploadAuthorization,
    authorization_valid_until: Date.now() + 60 * 60 * 1000,
  };
}

interface QueuedXhrResponse {
  status?: number;
  etag?: string;
  event?: 'load' | 'error' | 'timeout' | 'pending';
}

class FakeXMLHttpRequest {
  static queued: QueuedXhrResponse[] = [];
  static instances: FakeXMLHttpRequest[] = [];

  method = '';
  url = '';
  status = 0;
  timeout = 0;
  headers: Record<string, string> = {};
  sentPayload: Blob | null = null;
  responseEtag: string | null = null;
  aborted = false;
  upload = { onprogress: null as ((event: ProgressEvent) => void) | null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  onabort: (() => void) | null = null;

  constructor() {
    FakeXMLHttpRequest.instances.push(this);
  }

  open(method: string, url: string): void {
    this.method = method;
    this.url = url;
  }

  setRequestHeader(name: string, value: string): void {
    this.headers[name] = value;
  }

  getResponseHeader(name: string): string | null {
    return name.toLowerCase() === 'etag' ? this.responseEtag : null;
  }

  send(payload: Blob): void {
    this.sentPayload = payload;
    const queued = FakeXMLHttpRequest.queued.shift();
    if (!queued) throw new Error('Missing fake XHR response.');
    this.status = queued.status ?? 0;
    this.responseEtag = queued.etag ?? null;
    this.upload.onprogress?.({ loaded: payload.size } as ProgressEvent);
    if (queued.event === 'pending') return;
    if (queued.event === 'error') {
      this.onerror?.();
      return;
    }
    if (queued.event === 'timeout') {
      this.ontimeout?.();
      return;
    }
    this.onload?.();
  }

  abort(): void {
    this.aborted = true;
    this.onabort?.();
  }
}

beforeEach(() => {
  jest.restoreAllMocks();
  global.fetch = jest.fn();
  FakeXMLHttpRequest.queued = [];
  FakeXMLHttpRequest.instances = [];
  (global as unknown as { XMLHttpRequest: typeof XMLHttpRequest }).XMLHttpRequest =
    FakeXMLHttpRequest as unknown as typeof XMLHttpRequest;
});

it('selects exactly one supported type using the stable priority', () => {
  const sor = new File(['sor'], 'first.sor');
  const msor = new File(['msor'], 'second.msor');
  const pdf = new File(['pdf'], 'document.pdf');

  expect(selectInputFiles([pdf, msor, sor])).toEqual({
    selectedExtension: '.sor',
    selectedFiles: [sor],
    ignoredFiles: [pdf, msor],
  });
  expect(() => selectInputFiles([pdf])).toThrow(
    'Không có file .sor, .msor hoặc .trc hợp lệ.',
  );
});

it('requests a server-generated input pathname', async () => {
  const file = new File(['first'], 'first.sor');
  const fetchMock = global.fetch as jest.Mock;
  fetchMock.mockResolvedValue(
    mockJsonResponse({
      upload_id: uploadId,
      selected_extension: '.sor',
      files: [{
        original_name: file.name,
        pathname: inputPath,
        size: file.size,
      }],
      ignored_count: 0,
      maximum_total_size_in_bytes: 250 * 1024 * 1024,
      upload_authorization: uploadAuthorization,
      authorization_valid_until: Date.now() + 60 * 60 * 1000,
    }),
  );

  await expect(requestStorageInput([file])).resolves.toMatchObject({
    upload_id: uploadId,
    selected_extension: '.sor',
    files: [{ pathname: inputPath }],
  });
  expect(fetchMock).toHaveBeenCalledWith('/trace/api/blob-input', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      files: [{ name: file.name, size: file.size }],
    }),
  });
});

it('uploads a small file directly to its exact private R2 pathname', async () => {
  const file = new File(['first'], 'first.sor');
  const session = {
    upload_id: uploadId,
    selected_extension: '.sor' as const,
    files: [{ original_name: file.name, pathname: inputPath, size: file.size }],
    ignored_count: 0,
    maximum_total_size_in_bytes: 250 * 1024 * 1024,
    upload_authorization: uploadAuthorization,
    authorization_valid_until: Date.now() + 60 * 60 * 1000,
  };
  const fetchMock = global.fetch as jest.Mock;
  fetchMock.mockResolvedValueOnce(mockJsonResponse({
    mode: 'single',
    pathname: inputPath,
    size: file.size,
    upload_url: `${r2Base}/bucket/${inputPath}?signature=test`,
    valid_until: Date.now() + 60_000,
    required_headers: {
      'Content-Type': 'application/octet-stream',
      'If-None-Match': '*',
    },
  }));
  FakeXMLHttpRequest.queued.push({ status: 200, etag: '"etag"' });

  await expect(uploadFilesToStorage([file], session)).resolves.toEqual([{
    pathname: inputPath,
    size: file.size,
    content_type: 'application/octet-stream',
  }]);

  const xhr = FakeXMLHttpRequest.instances[0];
  expect(xhr.method).toBe('PUT');
  expect(xhr.headers).toEqual({
    'Content-Type': 'application/octet-stream',
    'If-None-Match': '*',
  });
  expect(xhr.sentPayload).toBe(file);
  expect(fetchMock).toHaveBeenCalledWith(
    '/trace/api/storage/prepare-upload',
    expect.objectContaining({ method: 'POST' }),
  );
});

it('requests a fresh signed URL before retrying an expired single upload', async () => {
  const file = new File(['first'], 'first.sor');
  const session = storageSession([file]);
  const fetchMock = global.fetch as jest.Mock;
  const uploadPlan = (suffix: string) => mockJsonResponse({
    mode: 'single',
    pathname: session.files[0].pathname,
    size: file.size,
    upload_url: `${r2Base}/${suffix}`,
    valid_until: Date.now() + 60_000,
    required_headers: {
      'Content-Type': 'application/octet-stream',
      'If-None-Match': '*',
    },
  });
  fetchMock
    .mockResolvedValueOnce(uploadPlan('expired'))
    .mockResolvedValueOnce(uploadPlan('refreshed'));
  FakeXMLHttpRequest.queued.push(
    { status: 403 },
    { status: 200, etag: '"etag"' },
  );

  await expect(uploadFilesToStorage([file], session)).resolves.toHaveLength(1);

  expect(FakeXMLHttpRequest.instances.map((xhr) => xhr.url)).toEqual([
    `${r2Base}/expired`,
    `${r2Base}/refreshed`,
  ]);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it('cancels other active XHR uploads after one worker fails', async () => {
  const files = [
    new File(['first'], 'first.sor'),
    new File(['second'], 'second.sor'),
  ];
  const session = storageSession(files);
  const fetchMock = global.fetch as jest.Mock;
  fetchMock.mockImplementation((url: string, options: RequestInit) => {
    const body = JSON.parse(options.body as string);
    if (url.endsWith('/prepare-upload')) {
      return Promise.resolve(mockJsonResponse({
        mode: 'single',
        pathname: body.pathname,
        size: body.size,
        upload_url: `${r2Base}/${body.pathname}`,
        valid_until: Date.now() + 60_000,
        required_headers: {
          'Content-Type': 'application/octet-stream',
          'If-None-Match': '*',
        },
      }));
    }
    return Promise.resolve(mockJsonResponse({ detail: 'not found' }, false));
  });
  FakeXMLHttpRequest.queued.push(
    { event: 'pending' },
    { status: 401 },
  );

  await expect(uploadFilesToStorage(files, session)).rejects.toThrow(
    'Cloudflare R2 từ chối tải file',
  );

  expect(FakeXMLHttpRequest.instances).toHaveLength(2);
  expect(FakeXMLHttpRequest.instances[0].aborted).toBe(true);
});

it('uploads a large file as ordered R2 multipart parts and completes it', async () => {
  const file = new File(['abcdef'], 'first.sor');
  const session = {
    upload_id: uploadId,
    selected_extension: '.sor' as const,
    files: [{ original_name: file.name, pathname: inputPath, size: file.size }],
    ignored_count: 0,
    maximum_total_size_in_bytes: 250 * 1024 * 1024,
    upload_authorization: uploadAuthorization,
    authorization_valid_until: Date.now() + 60 * 60 * 1000,
  };
  const fetchMock = global.fetch as jest.Mock;
  fetchMock
    .mockResolvedValueOnce(mockJsonResponse({
      mode: 'multipart',
      pathname: inputPath,
      size: file.size,
      multipart_upload_id: 'multipart-id',
      part_size: 3,
      valid_until: Date.now() + 60_000,
      parts: [
        { part_number: 1, size: 3 },
        { part_number: 2, size: 3 },
      ],
    }))
    .mockResolvedValueOnce(mockJsonResponse({
      pathname: inputPath,
      size: file.size,
      multipart_upload_id: 'multipart-id',
      part_number: 1,
      part_size: 3,
      upload_url: `${r2Base}/part-1`,
      valid_until: Date.now() + 60_000,
    }))
    .mockResolvedValueOnce(mockJsonResponse({
      pathname: inputPath,
      size: file.size,
      multipart_upload_id: 'multipart-id',
      part_number: 2,
      part_size: 3,
      upload_url: `${r2Base}/part-2`,
      valid_until: Date.now() + 60_000,
    }))
    .mockResolvedValueOnce(mockJsonResponse({
      pathname: inputPath,
      size: file.size,
      content_type: 'application/octet-stream',
    }));
  FakeXMLHttpRequest.queued.push(
    { status: 200, etag: '"part-1"' },
    { status: 200, etag: '"part-2"' },
  );

  await uploadFilesToStorage([file], session);

  expect(FakeXMLHttpRequest.instances.map((xhr) => xhr.sentPayload?.size)).toEqual([3, 3]);
  const completion = fetchMock.mock.calls[3];
  expect(completion[0]).toBe('/trace/api/storage/complete-multipart');
  expect(JSON.parse(completion[1].body)).toMatchObject({
    pathname: inputPath,
    multipart_upload_id: 'multipart-id',
    parts: [
      { part_number: 1, etag: '"part-1"' },
      { part_number: 2, etag: '"part-2"' },
    ],
  });
});

it('aborts an incomplete multipart upload when R2 does not expose ETag', async () => {
  const file = new File(['abcdef'], 'first.sor');
  const session = storageSession([file]);
  const descriptor = session.files[0];
  const fetchMock = global.fetch as jest.Mock;
  fetchMock
    .mockResolvedValueOnce(mockJsonResponse({
      mode: 'multipart',
      pathname: descriptor.pathname,
      size: file.size,
      multipart_upload_id: 'multipart-id',
      part_size: file.size,
      valid_until: Date.now() + 60_000,
      parts: [{ part_number: 1, size: file.size }],
    }))
    .mockResolvedValueOnce(mockJsonResponse({
      pathname: descriptor.pathname,
      size: file.size,
      multipart_upload_id: 'multipart-id',
      part_number: 1,
      part_size: file.size,
      upload_url: `${r2Base}/part-1`,
      valid_until: Date.now() + 60_000,
    }))
    .mockResolvedValueOnce(mockJsonResponse({ detail: 'not found' }, false))
    .mockResolvedValueOnce(mockJsonResponse({ status: 'aborted' }));
  FakeXMLHttpRequest.queued.push({ status: 200 });

  await expect(uploadFilesToStorage([file], session)).rejects.toThrow('ETag');

  expect(fetchMock.mock.calls.map((call) => call[0])).toContain(
    '/trace/api/storage/abort-multipart',
  );
});

it('parses the small conversion response without reading an XLSX body', async () => {
  const conversion = {
    upload_id: uploadId,
    status: 'succeeded',
    filename: 'FastReporter_test.xlsx',
    output_pathname: `otdr/output/2026/07/22/${uploadId}/FastReporter_test.xlsx`,
    content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    size: 123,
  };

  await expect(
    parseStorageConversionResponse(mockJsonResponse(conversion)),
  ).resolves.toEqual(conversion);
});

it('requests an R2 signed direct-download URL for the converted output', async () => {
  const outputPath = `otdr/output/2026/07/22/${uploadId}/FastReporter_test.xlsx`;
  const fetchMock = global.fetch as jest.Mock;
  fetchMock.mockResolvedValue(mockJsonResponse({
    download_url: `${r2Base}/bucket/${outputPath}?signature=test`,
    valid_until: Date.now() + 60_000,
  }));

  await expect(requestSignedDownload(outputPath)).resolves.toMatchObject({
    download_url: expect.stringContaining('r2.cloudflarestorage.com'),
  });
  expect(fetchMock).toHaveBeenCalledWith('/trace/api/storage/download-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pathname: outputPath }),
  });
});

it('sends the signed URL to the browser download anchor', () => {
  const click = jest
    .spyOn(HTMLAnchorElement.prototype, 'click')
    .mockImplementation(() => undefined);
  const url = `${r2Base}/signed-output`;

  downloadFromSignedUrl(url, 'FastReporter_test.xlsx');

  expect(click).toHaveBeenCalledTimes(1);
  expect(document.querySelector(`a[href="${url}"]`)).toBeNull();
});
