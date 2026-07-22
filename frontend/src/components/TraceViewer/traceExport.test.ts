import { upload } from '@vercel/blob/client';
import JSZip from 'jszip';

import {
  createBatchZip,
  parseBlobConversionResponse,
  requestBlobInput,
  requestSignedDownload,
  uploadBatchToBlob,
} from './traceExport';

jest.mock('@vercel/blob/client', () => ({ upload: jest.fn() }), { virtual: true });

const mockedUpload = upload as jest.MockedFunction<typeof upload>;
const uploadId = '123e4567-e89b-12d3-a456-426614174000';
const inputPath = `otdr/input/2026/07/22/${uploadId}/batch.zip`;

function mockJsonResponse(body: unknown, ok = true): Response {
  return {
    ok,
    json: jest.fn().mockResolvedValue(body),
  } as unknown as Response;
}

function readBlob(blob: Blob): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.readAsArrayBuffer(blob);
  });
}

beforeEach(() => {
  jest.restoreAllMocks();
  mockedUpload.mockReset();
  global.fetch = jest.fn();
});

it('creates a ZIP that preserves duplicate filenames as separate input files', async () => {
  const batch = await createBatchZip(
    [new File(['first'], 'same.sor'), new File(['second'], 'same.sor')],
    1024 * 1024,
  );
  const zip = await JSZip.loadAsync(await readBlob(batch));
  const entries = Object.values(zip.files).filter((entry) => !entry.dir);

  expect(entries.map((entry) => entry.name)).toEqual([
    '000001/same.sor',
    '000002/same.sor',
  ]);
  await expect(entries[0].async('string')).resolves.toBe('first');
  await expect(entries[1].async('string')).resolves.toBe('second');
  expect(batch.type).toBe('application/zip');
});

it('requests a server-generated input pathname', async () => {
  const fetchMock = global.fetch as jest.Mock;
  fetchMock.mockResolvedValue(
    mockJsonResponse({
      upload_id: uploadId,
      pathname: inputPath,
      maximum_size_in_bytes: 250 * 1024 * 1024,
    }),
  );

  await expect(requestBlobInput()).resolves.toEqual({
    upload_id: uploadId,
    pathname: inputPath,
    maximum_size_in_bytes: 250 * 1024 * 1024,
  });
  expect(fetchMock).toHaveBeenCalledWith('/trace/api/blob-input', {
    method: 'POST',
  });
});

it('uploads directly to the exact private Blob pathname before conversion', async () => {
  const batch = new Blob(['zip'], { type: 'application/zip' });
  mockedUpload.mockResolvedValue({
    pathname: inputPath,
    url: 'https://private.example/input',
    downloadUrl: 'https://private.example/input?download=1',
    contentType: 'application/zip',
    contentDisposition: 'attachment; filename="batch.zip"',
    etag: 'etag',
  });

  await uploadBatchToBlob(batch, {
    upload_id: uploadId,
    pathname: inputPath,
    maximum_size_in_bytes: 250 * 1024 * 1024,
  });

  expect(mockedUpload).toHaveBeenCalledTimes(1);
  expect(mockedUpload).toHaveBeenCalledWith(
    inputPath,
    batch,
    expect.objectContaining({
      access: 'private',
      handleUploadUrl: '/api/blob/upload',
      contentType: 'application/zip',
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
