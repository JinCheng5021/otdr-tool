import type { VercelRequest, VercelResponse } from '@vercel/node';
import {
  handleUpload,
  type HandleUploadBody,
} from '@vercel/blob/client';

import {
  BlobRequestValidationError,
  CLIENT_UPLOAD_TOKEN_LIFETIME_MS,
  MAXIMUM_BLOB_SIZE_IN_BYTES,
  parseInputPathname,
  parseUploadClientPayload,
} from '../shared/blob-paths';

export default async function handler(
  request: VercelRequest,
  response: VercelResponse,
): Promise<void> {
  response.setHeader('Cache-Control', 'no-store');

  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST');
    response.status(405).json({ detail: 'Method not allowed.' });
    return;
  }

  const token = process.env.BLOB_READ_WRITE_TOKEN;
  if (!token) {
    response.status(503).json({ detail: 'Vercel Blob is not configured.' });
    return;
  }

  try {
    const result = await handleUpload({
      token,
      request,
      body: request.body as HandleUploadBody,
      onBeforeGenerateToken: async (pathname, clientPayload) => {
        const parsedPath = parseInputPathname(pathname);
        const uploadId = parseUploadClientPayload(clientPayload);
        if (uploadId !== parsedPath.uploadId) {
          throw new BlobRequestValidationError(
            'uploadId does not match the input Blob pathname.',
          );
        }

        return {
          allowedContentTypes: ['application/zip'],
          maximumSizeInBytes: MAXIMUM_BLOB_SIZE_IN_BYTES,
          validUntil: Date.now() + CLIENT_UPLOAD_TOKEN_LIFETIME_MS,
          addRandomSuffix: false,
          allowOverwrite: false,
          tokenPayload: clientPayload,
        };
      },
    });

    response.status(200).json(result);
  } catch (error) {
    if (error instanceof BlobRequestValidationError) {
      response.status(400).json({ detail: error.message });
      return;
    }

    console.error('Vercel Blob upload token error:', error);
    response.status(502).json({ detail: 'Could not authorize the Blob upload.' });
  }
}
