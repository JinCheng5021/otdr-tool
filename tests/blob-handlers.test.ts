import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { VercelRequest, VercelResponse } from '@vercel/node';

import signedGetHandler from '../api/blob-signed-get';
import uploadHandler from '../api/blob-upload';

interface CapturedResponse {
  statusCode?: number;
  body?: unknown;
  headers: Map<string, unknown>;
}

function responseDouble(): {
  response: VercelResponse;
  captured: CapturedResponse;
} {
  const captured: CapturedResponse = { headers: new Map() };
  const response = {
    setHeader(name: string, value: unknown) {
      captured.headers.set(name.toLowerCase(), value);
      return response;
    },
    status(code: number) {
      captured.statusCode = code;
      return response;
    },
    json(body: unknown) {
      captured.body = body;
      return response;
    },
  } as unknown as VercelResponse;
  return { response, captured };
}

function requestDouble(method: string, body?: unknown): VercelRequest {
  return { method, body } as VercelRequest;
}

async function withoutBlobToken(action: () => Promise<void>): Promise<void> {
  const previous = process.env.BLOB_READ_WRITE_TOKEN;
  delete process.env.BLOB_READ_WRITE_TOKEN;
  try {
    await action();
  } finally {
    if (previous === undefined) {
      delete process.env.BLOB_READ_WRITE_TOKEN;
    } else {
      process.env.BLOB_READ_WRITE_TOKEN = previous;
    }
  }
}

describe('Vercel Blob function guards', () => {
  for (const [name, handler] of [
    ['upload', uploadHandler],
    ['signed GET', signedGetHandler],
  ] as const) {
    it(`${name} rejects non-POST requests`, async () => {
      const { response, captured } = responseDouble();
      await handler(requestDouble('GET'), response);
      assert.equal(captured.statusCode, 405);
      assert.equal(captured.headers.get('allow'), 'POST');
      assert.equal(captured.headers.get('cache-control'), 'no-store');
    });

    it(`${name} reports missing Blob configuration`, async () => {
      const { response, captured } = responseDouble();
      await withoutBlobToken(() => handler(requestDouble('POST', {}), response));
      assert.equal(captured.statusCode, 503);
      assert.deepEqual(captured.body, {
        detail: 'Vercel Blob is not configured.',
      });
    });
  }

  it('signed GET rejects an unmanaged pathname before calling Blob', async () => {
    const previous = process.env.BLOB_READ_WRITE_TOKEN;
    process.env.BLOB_READ_WRITE_TOKEN = 'unused-test-token';
    try {
      const { response, captured } = responseDouble();
      await signedGetHandler(
        requestDouble('POST', { pathname: 'otdr/input/not-an-output' }),
        response,
      );
      assert.equal(captured.statusCode, 400);
    } finally {
      if (previous === undefined) {
        delete process.env.BLOB_READ_WRITE_TOKEN;
      } else {
        process.env.BLOB_READ_WRITE_TOKEN = previous;
      }
    }
  });
});
