import { getDownloadUrl, issueSignedToken, presignUrl } from '@vercel/blob';
import type { VercelRequest, VercelResponse } from '@vercel/node';

import {
  BlobRequestValidationError,
  SIGNED_DOWNLOAD_LIFETIME_MS,
  parseOutputPathname,
} from '../shared/blob-paths.js';

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
    const parsedPath = parseOutputPathname(request.body?.pathname);
    const validUntil = Date.now() + SIGNED_DOWNLOAD_LIFETIME_MS;
    const signedToken = await issueSignedToken({
      token,
      pathname: parsedPath.pathname,
      operations: ['get'],
      validUntil,
    });
    const { presignedUrl } = await presignUrl(signedToken, {
      access: 'private',
      operation: 'get',
      pathname: parsedPath.pathname,
      validUntil,
    });

    response.status(200).json({
      download_url: getDownloadUrl(presignedUrl),
      valid_until: validUntil,
    });
  } catch (error) {
    if (error instanceof BlobRequestValidationError) {
      response.status(400).json({ detail: error.message });
      return;
    }

    console.error('Vercel Blob signed download error:', error);
    response.status(502).json({ detail: 'Could not create the download URL.' });
  }
}
