import { Hono } from 'hono';
import { apiError } from '../lib/api.js';
import { requireAuth } from '../middleware/auth.js';
import type { AppEnv } from '../types.js';

export const derivativesRouter = new Hono<AppEnv>();

const VARIANTS = {
  'grid-256': { width: 256, height: 256, fit: 'scale-down', quality: 80 },
  'grid-512': { width: 512, height: 512, fit: 'scale-down', quality: 82 },
  'preview-1600': { width: 1600, height: 1600, fit: 'scale-down', quality: 85 },
  'shopify-product': { width: 2048, height: 2048, fit: 'contain', quality: 88 },
  'shopify-card': { width: 1000, height: 1000, fit: 'cover', quality: 85 },
  'email-hero': { width: 1200, height: 800, fit: 'scale-down', quality: 82 },
  'email-module': { width: 600, height: 600, fit: 'scale-down', quality: 80 },
  'social-square': { width: 1080, height: 1080, fit: 'cover', quality: 85 },
  'social-story': { width: 1080, height: 1920, fit: 'cover', quality: 85 }
} as const;
const IMAGES_INPUT_MAX_BYTES = 20 * 1024 * 1024;

derivativesRouter.get('/assets/:id/variants/:variant', requireAuth('library.read'), async (c) => {
  const assetID = c.req.param('id').toLowerCase();
  const variant = c.req.param('variant') as keyof typeof VARIANTS;
  const config = VARIANTS[variant];
  if (!config) return apiError(c, 404, 'DERIVATIVE_VARIANT_NOT_FOUND', 'Unknown derivative variant');
  if (!c.env.IMAGES) return apiError(c, 503, 'DERIVATIVE_SERVICE_UNAVAILABLE', 'Cloud image transformations are not configured');

  const asset = await c.env.DB.prepare(
    `SELECT blobs.sha256, blobs.r2_key, blobs.r2_key AS storage_key, blobs.byte_size, blobs.upload_state
     FROM assets JOIN blobs ON blobs.id = assets.blob_id WHERE assets.id = ?`
  ).bind(assetID).first<{ sha256: string; r2_key: string; storage_key: string; byte_size: number; upload_state: string }>();
  if (!asset || asset.upload_state !== 'verified') return apiError(c, 404, 'ASSET_NOT_FOUND', 'Verified asset was not found');
  if (asset.byte_size > IMAGES_INPUT_MAX_BYTES) {
    return apiError(c, 422, 'DERIVATIVE_SOURCE_TOO_LARGE', 'This original must be materialized locally before rendering a derivative');
  }

  const derivativeKey = `derivatives/sha256/${asset.sha256}/${variant}.webp`;
  const cached = await c.env.BLOBS.get(derivativeKey);
  if (cached?.body) return derivativeResponse(cached.body, 'HIT');

  let original = await c.env.BLOBS.get(asset.storage_key);
  if (!original?.body) {
    const legacyOrigin = (c.env as { LEGACY_ORIGIN?: R2Bucket }).LEGACY_ORIGIN;
    if (legacyOrigin) {
      original = await legacyOrigin.get(asset.storage_key);
    }
  }
  if (!original?.body) return apiError(c, 404, 'R2_OBJECT_MISSING', 'Verified original object is missing');
  try {
    const transformed = await c.env.IMAGES.input(original.body)
      .transform({ width: config.width, height: config.height, fit: config.fit })
      .output({ format: 'image/webp', quality: config.quality });
    // R2 rejects a stream of unknown length, and a stream can only be consumed once (cache write OR response),
    // so buffer the (small) derivative and use the bytes for both.
    const body = await new Response(transformed.image()).arrayBuffer();
    await c.env.BLOBS.put(derivativeKey, body, {
      httpMetadata: { contentType: 'image/webp', cacheControl: 'public, max-age=31536000, immutable' }
    });
    return derivativeResponse(body, 'MISS');
  } catch (error) {
    console.error('derivative generation failed:', error instanceof Error ? error.message : 'unknown error');
    return apiError(c, 422, 'DERIVATIVE_GENERATION_FAILED', 'Cloud image transformation failed');
  }
});

function derivativeResponse(body: ReadableStream<Uint8Array> | ArrayBuffer, cache: 'HIT' | 'MISS'): Response {
  return new Response(body, {
    headers: {
      'Content-Type': 'image/webp',
      'Cache-Control': 'public, max-age=31536000, immutable',
      'X-Framebase-Derivative-Cache': cache
    }
  });
}
