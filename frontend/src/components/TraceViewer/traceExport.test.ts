import { upload } from '@vercel/blob/client';

import {
  downloadFromSignedUrl,
  parseBlobConversionResponse,
  requestBlobInput,
  requestSignedDownload,
  selectInputFiles,
  uploadFilesToBlob,
} from './traceExport';

jest.mock('@vercel/blob/client', () => ({ upload: jest.fn() }), { virtual: true });

const mockedUpload = upload as jest.MockedFunction<typeof upload>;
const uploadId = '123e4567-e89b-12d3-a456-426614174000';
const inputPath = `otdr/input/2026/07/22/${uploadId}/000001-first.sor`;

function mockJsonResponse(body: unknown, ok = true): Response {
  return {
    ok,
    json: jest.fn().mockResolvedValue(body),
  } as unknown as Response;
}

beforeEach(() => {
  jest.restoreAllMocks();
  mockedUpload.mockReset();
  global.fetch = jest.fn();
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
    }),
  );

  await expect(requestBlobInput([file])).resolves.toEqual({
    upload_id: uploadId,
    selected_extension: '.sor',
    files: [{
      original_name: file.name,
      pathname: inputPath,
      size: file.size,
    }],
    ignored_count: 0,
    maximum_total_size_in_bytes: 250 * 1024 * 1024,
  });
  expect(fetchMock).toHaveBeenCalledWith('/trace/api/blob-input', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      files: [{ name: file.name, size: file.size }],
    }),
  });
});

it('uploads each file directly to its exact private Blob pathname', async () => {
  const file = new File(['first'], 'first.sor');
  mockedUpload.mockResolvedValue({
    pathname: inputPath,
    url: 'https://private.example/input',
    downloadUrl: 'https://private.example/input?download=1',
    contentType: 'application/octet-stream',
    contentDisposition: 'attachment; filename="first.sor"',
    etag: 'etag',
  });

  await uploadFilesToBlob([file], {
    upload_id: uploadId,
    selected_extension: '.sor',
    files: [{
      original_name: file.name,
      pathname: inputPath,
      size: file.size,
    }],
    ignored_count: 0,
    maximum_total_size_in_bytes: 250 * 1024 * 1024,
  });

  expect(mockedUpload).toHaveBeenCalledTimes(1);
  expect(mockedUpload).toHaveBeenCalledWith(
    inputPath,
    file,
    expect.objectContaining({
      access: 'private',
      handleUploadUrl: '/api/blob/upload',
      contentType: 'application/octet-stream',
      clientPayload: JSON.stringify({ uploadId }),
      multipart: false,
    }),
  );
});

it('parses the small conversion response without reading an XLSX response body', async () => {
  const conversion = {
    upload_id: uploadId,
    status: 'succeeded',
    filename: 'FastReporter_test.xlsx',
    output_pathname: `otdr/output/2026/07/22/${uploadId}/FastReporter_test.xlsx`,
    content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    size: 123,
  };

  await expect(
    parseBlobConversionResponse(mockJsonResponse(conversion)),
  ).resolves.toEqual(conversion);
});

it('requests a signed direct-download URL for the converted output', async () => {
  const outputPath = `otdr/output/2026/07/22/${uploadId}/FastReporter_test.xlsx`;
  const fetchMock = global.fetch as jest.Mock;
  fetchMock.mockResolvedValue(
    mockJsonResponse({
      download_url: 'https://private.example/signed-output',
      valid_until: 123456789,
    }),
  );

  await expect(requestSignedDownload(outputPath)).resolves.toEqual({
    download_url: 'https://private.example/signed-output',
    valid_until: 123456789,
  });
  expect(fetchMock).toHaveBeenCalledWith('/api/blob/signed-get', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pathname: outputPath }),
  });
});

it('sends the signed URL to the browser download anchor', () => {
  const click = jest
    .spyOn(HTMLAnchorElement.prototype, 'click')
    .mockImplementation(() => undefined);

  downloadFromSignedUrl(
    'https://private.example/signed-output',
    'FastReporter_test.xlsx',
  );

  expect(click).toHaveBeenCalledTimes(1);
  expect(
    document.querySelector('a[href="https://private.example/signed-output"]'),
  ).toBeNull();
});
