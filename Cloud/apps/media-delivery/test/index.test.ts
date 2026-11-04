import { describe, it, expect, vi } from 'vitest';
import worker, {
  isSensitiveKey,
  verifySignature,
  hmacHex,
  VARIANTS,
  type Env
} from '../src/index.js';

function mockR2Object(bodyContent: string, contentType = 'image/jpeg'): R2ObjectBody {
  const encoder = new TextEncoder();
  const bytes = encoder.encode(bodyContent);
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(bytes);
      controller.close();
    }
  });

  return {
    key: 'test-key',
    version: 'v1',
    size: bytes.byteLength,
    etag: '"etag123"',
    httpEtag: '"etag123"',
    checksums: {},
    uploaded: new Date(),
    httpMetadata: { contentType },
    customMetadata: {},
    body: stream as unknown as ReadableStream<Uint8Array>,
    bodyUsed: false,
    arrayBuffer: async () => bytes.buffer,
    text: async () => bodyContent,
    json: async () => JSON.parse(bodyContent),
    blob: async () => new Blob([bytes], { type: contentType }),
    writeHttpMetadata: () => {}
  } as unknown as R2ObjectBody;
}

function createMockEnv(overrides?: {
  mediaOriginStore?: Record<string, string>;
  blobsStore?: Record<string, string>;
  secret?: string;
}): Env {
  const mediaOrigin = overrides?.mediaOriginStore ?? {};
  const blobs = overrides?.blobsStore ?? {};

  const mockBucket = (store: Record<string, string>): R2Bucket =>
    ({
      async get(key: string) {
        if (key in store) {
          return mockR2Object(store[key]);
        }
        return null;
      },
      async list(options?: { prefix?: string }) {
        const prefix = options?.prefix ?? '';
        const objects = Object.keys(store)
          .filter((k) => k.startsWith(prefix))
          .map((k) => ({ key: k, size: store[k].length }));
        return { objects, truncated: false };
      },
      async put() {},
      async delete() {},
      async head(key: string) {
        if (key in store) {
          return mockR2Object(store[key]);
        }
        return null;
      }
    } as unknown as R2Bucket);

  const mockImages = {
    input(stream: any) {
      return {
        transform(opts: any) {
          return {
            output(outOpts: any) {
              return {
                async response() {
                  return new Response(new Uint8Array([1, 2, 3]), {
                    status: 200,
                    headers: {
                      'content-type': outOpts.format ?? 'image/avif',
                      'x-transformed-width': String(opts.width)
                    }
                  });
                },
                image() {
                  return new ReadableStream({
                    start(controller) {
                      controller.enqueue(new Uint8Array([1, 2, 3]));
                      controller.close();
                    }
                  });
                }
              };
            }
          };
        }
      };
    }
  };

  return {
    IMAGES: mockImages as any,
    MEDIA_ORIGIN: mockBucket(mediaOrigin),
    BLOBS: mockBucket(blobs),
    DELIVERY_SIGNING_SECRET: overrides?.secret ?? 'test-secret-key-12345'
  };
}

describe('hsc-media-delivery', () => {
  describe('Health Route', () => {
    it('returns 200 OK for /health', async () => {
      const env = createMockEnv();
      const res = await worker.fetch(new Request('https://assets.hairsolutions.co/health'), env);
      expect(res.status).toBe(200);
      const data = await res.json();
      expect(data).toEqual({ status: 'ok', service: 'hsc-media-delivery' });
    });

    it('returns 200 OK for /v1/health', async () => {
      const env = createMockEnv();
      const res = await worker.fetch(new Request('https://assets.hairsolutions.co/v1/health'), env);
      expect(res.status).toBe(200);
      const data = await res.json();
      expect(data).toEqual({ status: 'ok', service: 'hsc-media-delivery' });
    });

    it('handles HEAD /health', async () => {
      const env = createMockEnv();
      const res = await worker.fetch(
        new Request('https://assets.hairsolutions.co/health', { method: 'HEAD' }),
        env
      );
      expect(res.status).toBe(200);
    });
  });

  describe('Sensitive Prefix Guardrail', () => {
    it('identifies sensitive keys accurately', () => {
      expect(isSensitiveKey('approved/brand/people/before-after/case1/0123456789abcdef.jpg')).toBe(true);
      expect(isSensitiveKey('approved/brand/people/founder/bio/0123456789abcdef.jpg')).toBe(true);
      expect(isSensitiveKey('approved/brand/people_founder/0123456789abcdef.jpg')).toBe(true);
      expect(isSensitiveKey('approved/marketing/needs-review/0123456789abcdef.jpg')).toBe(true);
      expect(isSensitiveKey('approved/products/oil/0123456789abcdef.jpg')).toBe(false);
      expect(isSensitiveKey('approved/storefront/hero/0123456789abcdef.jpg')).toBe(false);
    });

    it('blocks sensitive before-after request with 403 Forbidden when unsigned', async () => {
      const env = createMockEnv({
        mediaOriginStore: {
          'approved/brand/people/before-after/case1/0123456789abcdef.jpg': 'binary-data'
        }
      });

      const res = await worker.fetch(
        new Request(
          'https://assets.hairsolutions.co/v1/public/approved/brand/people/before-after/case1/0123456789abcdef.jpg'
        ),
        env
      );

      expect(res.status).toBe(403);
      const body = await res.json();
      expect(body).toEqual({
        error: 'SENSITIVE_ASSET_SIGNATURE_REQUIRED',
        message: 'Access to sensitive assets requires a valid unexpired HMAC signature'
      });
    });

    it('blocks sensitive founder request with 403 Forbidden when unsigned', async () => {
      const env = createMockEnv();
      const res = await worker.fetch(
        new Request(
          'https://assets.hairsolutions.co/v1/public/approved/brand/people/founder/0123456789abcdef.jpg'
        ),
        env
      );
      expect(res.status).toBe(403);
    });

    it('blocks key containing needs-review with 403 Forbidden', async () => {
      const env = createMockEnv();
      const res = await worker.fetch(
        new Request(
          'https://assets.hairsolutions.co/v1/public/approved/marketing/item-needs-review/0123456789abcdef.jpg'
        ),
        env
      );
      expect(res.status).toBe(403);
    });

    it('blocks request when signature is expired', async () => {
      const env = createMockEnv();
      const key = 'approved/brand/people/before-after/case1/0123456789abcdef.jpg';
      const expiredTs = Math.floor(Date.now() / 1000) - 3600; // 1 hour ago
      const sig = await hmacHex(env.DELIVERY_SIGNING_SECRET!, `${key}:${expiredTs}`);

      const res = await worker.fetch(
        new Request(
          `https://assets.hairsolutions.co/v1/public/${key}?exp=${expiredTs}&sig=${sig}`
        ),
        env
      );

      expect(res.status).toBe(403);
    });

    it('blocks request when signature is invalid/tampered', async () => {
      const env = createMockEnv();
      const key = 'approved/brand/people/before-after/case1/0123456789abcdef.jpg';
      const futureTs = Math.floor(Date.now() / 1000) + 3600;
      const invalidSig = '00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff';

      const res = await worker.fetch(
        new Request(
          `https://assets.hairsolutions.co/v1/public/${key}?exp=${futureTs}&sig=${invalidSig}`
        ),
        env
      );

      expect(res.status).toBe(403);
    });

    it('allows sensitive asset request when signed with valid HMAC and unexpired', async () => {
      const key = 'approved/brand/people/before-after/case1/0123456789abcdef.jpg';
      const secret = 'test-secret-key-12345';
      const env = createMockEnv({
        secret,
        mediaOriginStore: {
          [key]: 'sensitive-image-bytes'
        }
      });

      const futureTs = Math.floor(Date.now() / 1000) + 3600;
      const sig = await hmacHex(secret, `${key}:${futureTs}`);

      const res = await worker.fetch(
        new Request(
          `https://assets.hairsolutions.co/v1/public/${key}?exp=${futureTs}&sig=${sig}`
        ),
        env
      );

      expect(res.status).toBe(200);
      expect(await res.text()).toBe('sensitive-image-bytes');
      expect(res.headers.get('cache-control')).toBe('public, max-age=31536000, immutable');
    });
  });

  describe('Dual-Bucket Support', () => {
    it('serves asset from MEDIA_ORIGIN when present', async () => {
      const key = 'approved/products/scalp-oil/0123456789abcdef.jpg';
      const env = createMockEnv({
        mediaOriginStore: { [key]: 'origin-bytes' },
        blobsStore: { [key]: 'blobs-bytes' }
      });

      const res = await worker.fetch(
        new Request(`https://assets.hairsolutions.co/v1/public/${key}`),
        env
      );

      expect(res.status).toBe(200);
      expect(await res.text()).toBe('origin-bytes');
    });

    it('falls back to BLOBS (framebase-blobs-prod) when not in MEDIA_ORIGIN', async () => {
      const key = 'approved/products/scalp-oil/0123456789abcdef.jpg';
      const env = createMockEnv({
        mediaOriginStore: {},
        blobsStore: { [key]: 'fallback-blobs-bytes' }
      });

      const res = await worker.fetch(
        new Request(`https://assets.hairsolutions.co/v1/public/${key}`),
        env
      );

      expect(res.status).toBe(200);
      expect(await res.text()).toBe('fallback-blobs-bytes');
    });

    it('returns 404 when asset missing from both buckets', async () => {
      const env = createMockEnv();
      const res = await worker.fetch(
        new Request('https://assets.hairsolutions.co/v1/public/approved/products/oil/0123456789abcdef.jpg'),
        env
      );
      expect(res.status).toBe(404);
    });

    it('supports dynamic variant transformation on public route', async () => {
      const key = 'approved/products/scalp-oil/0123456789abcdef.jpg';
      const env = createMockEnv({
        mediaOriginStore: { [key]: 'image-bytes' }
      });

      const res = await worker.fetch(
        new Request(`https://assets.hairsolutions.co/v1/public/${key}?variant=thumbnail`),
        env
      );

      expect(res.status).toBe(200);
      expect(res.headers.get('content-type')).toBe('image/avif');
      expect(res.headers.get('cache-control')).toBe('public, max-age=31536000, immutable');
    });
  });

  describe('/blobs/sha256/:prefix/:file Route', () => {
    it('serves blob from BLOBS bucket', async () => {
      const prefix = 'ab';
      const file = 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789.jpg';
      const key = `blobs/sha256/${prefix}/${file}`;
      const env = createMockEnv({
        blobsStore: { [key]: 'blob-content' }
      });

      const res = await worker.fetch(
        new Request(`https://assets.hairsolutions.co/blobs/sha256/${prefix}/${file}`),
        env
      );

      expect(res.status).toBe(200);
      expect(await res.text()).toBe('blob-content');
      expect(res.headers.get('cache-control')).toBe('public, max-age=31536000, immutable');
    });

    it('transforms blob dynamically when variant specified', async () => {
      const prefix = 'cd';
      const file = 'cdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789.png';
      const key = `blobs/sha256/${prefix}/${file}`;
      const env = createMockEnv({
        blobsStore: { [key]: 'png-bytes' }
      });

      const res = await worker.fetch(
        new Request(`https://assets.hairsolutions.co/blobs/sha256/${prefix}/${file}?variant=grid-256`),
        env
      );

      expect(res.status).toBe(200);
      expect(res.headers.get('cache-control')).toBe('public, max-age=31536000, immutable');
    });
  });

  describe('/assets/:id/variants/:variant Route', () => {
    it('serves pre-cached derivative if available', async () => {
      const id = 'asset-uuid-1234';
      const variant = 'grid-512';
      const derivativeKey = `derivatives/assets/${id}/${variant}.webp`;
      const env = createMockEnv({
        blobsStore: { [derivativeKey]: 'cached-derivative-bytes' }
      });

      const res = await worker.fetch(
        new Request(`https://assets.hairsolutions.co/assets/${id}/variants/${variant}`),
        env
      );

      expect(res.status).toBe(200);
      expect(await res.text()).toBe('cached-derivative-bytes');
    });

    it('dynamically generates variant from original blob by sha256', async () => {
      const sha256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';
      const key = `blobs/sha256/${sha256.slice(0, 2)}/${sha256}.jpg`;
      const env = createMockEnv({
        blobsStore: { [key]: 'original-jpeg-bytes' }
      });

      const res = await worker.fetch(
        new Request(`https://assets.hairsolutions.co/assets/${sha256}/variants/preview-1600`),
        env
      );

      expect(res.status).toBe(200);
      expect(res.headers.get('cache-control')).toBe('public, max-age=31536000, immutable');
    });

    it('returns 404 for unknown variant', async () => {
      const env = createMockEnv();
      const res = await worker.fetch(
        new Request('https://assets.hairsolutions.co/assets/123/variants/unknown-variant-xyz'),
        env
      );
      expect(res.status).toBe(404);
    });
  });

  describe('/v1/transform/* Route', () => {
    it('supports /v1/transform/:variant/:key', async () => {
      const key = 'approved/products/brush/0123456789abcdef.jpg';
      const env = createMockEnv({
        mediaOriginStore: { [key]: 'brush-bytes' }
      });

      const res = await worker.fetch(
        new Request(`https://assets.hairsolutions.co/v1/transform/thumbnail/${key}`),
        env
      );

      expect(res.status).toBe(200);
      expect(res.headers.get('cache-control')).toBe('public, max-age=31536000, immutable');
    });

    it('supports /v1/transform/:key?variant=:variant', async () => {
      const key = 'approved/products/brush/0123456789abcdef.jpg';
      const env = createMockEnv({
        mediaOriginStore: { [key]: 'brush-bytes' }
      });

      const res = await worker.fetch(
        new Request(`https://assets.hairsolutions.co/v1/transform/${key}?variant=card`),
        env
      );

      expect(res.status).toBe(200);
    });

    it('enforces sensitive guard on /v1/transform', async () => {
      const key = 'approved/brand/people/before-after/sample/0123456789abcdef.jpg';
      const env = createMockEnv({
        mediaOriginStore: { [key]: 'before-after-bytes' }
      });

      const res = await worker.fetch(
        new Request(`https://assets.hairsolutions.co/v1/transform/hero/${key}`),
        env
      );

      expect(res.status).toBe(403);
    });
  });
});
