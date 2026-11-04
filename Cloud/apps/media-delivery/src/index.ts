export interface VariantConfig {
  width: number;
  height: number;
  fit: 'cover' | 'scale-down' | 'contain' | 'crop' | 'pad';
  quality: number;
}

export const VARIANTS: Record<string, VariantConfig> = {
  // HSC Media Delivery presets
  thumbnail: { width: 320, height: 320, fit: 'cover', quality: 72 },
  card: { width: 720, height: 720, fit: 'scale-down', quality: 78 },
  product: { width: 1440, height: 1440, fit: 'scale-down', quality: 82 },
  hero: { width: 2400, height: 1600, fit: 'scale-down', quality: 84 },

  // Framebase & Edge presets
  'grid-256': { width: 256, height: 256, fit: 'scale-down', quality: 80 },
  'grid-512': { width: 512, height: 512, fit: 'scale-down', quality: 82 },
  'preview-1600': { width: 1600, height: 1600, fit: 'scale-down', quality: 85 },
  'shopify-product': { width: 1000, height: 1000, fit: 'contain', quality: 85 },
  'shopify-card': { width: 720, height: 720, fit: 'scale-down', quality: 78 },
  'email-hero': { width: 1200, height: 800, fit: 'scale-down', quality: 80 },
  'email-module': { width: 600, height: 600, fit: 'scale-down', quality: 80 },
  'social-square': { width: 1080, height: 1080, fit: 'cover', quality: 85 },
  'social-story': { width: 1080, height: 1920, fit: 'cover', quality: 85 }
};

export interface Env {
  IMAGES: {
    input(stream: ReadableStream | ArrayBuffer): {
      transform(options: { width?: number; height?: number; fit?: string; quality?: number }): {
        output(options: { format: string; quality?: number }): {
          response(): Promise<Response>;
          image?(): ReadableStream<Uint8Array>;
        };
      };
    };
  };
  MEDIA_ORIGIN: R2Bucket;
  BLOBS: R2Bucket;
  DELIVERY_SIGNING_SECRET?: string;
}

const PUBLIC_PREFIX = '/v1/public/';
const VERSIONED_PUBLIC_KEY = /^approved\/(products|storefront|marketing|brand)\/[a-z0-9][a-z0-9/_-]*\/[a-f0-9]{16,}\.(avif|gif|jpe?g|png|webp)$/;

const SENSITIVE_PREFIXES = [
  'approved/brand/people/before-after/',
  'approved/brand/people/founder/',
  'approved/brand/people_founder/'
];

export function isSensitiveKey(key: string): boolean {
  const normalized = key.startsWith('/') ? key.slice(1) : key;
  for (const prefix of SENSITIVE_PREFIXES) {
    if (normalized.startsWith(prefix) || normalized.includes(`/${prefix}`)) {
      return true;
    }
  }
  if (normalized.includes('needs-review')) {
    return true;
  }
  return false;
}

const encoder = new TextEncoder();

export function toHex(buffer: ArrayBuffer): string {
  return [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export function timingSafeEqual(left: string, right: string): boolean {
  if (left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i++) {
    diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  }
  return diff === 0;
}

export async function hmacHex(secret: string, value: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  return toHex(await crypto.subtle.sign('HMAC', key, encoder.encode(value)));
}

export async function verifySignature(
  url: URL,
  key: string,
  secret: string | undefined
): Promise<boolean> {
  if (!secret) return false;

  const expParam = url.searchParams.get('exp');
  const sigParam = url.searchParams.get('sig');
  if (!expParam || !sigParam) return false;

  const exp = Number(expParam);
  if (!Number.isFinite(exp)) return false;

  // Support both unix timestamp in seconds and milliseconds
  const expMs = exp < 1e12 ? exp * 1000 : exp;
  if (Date.now() > expMs) return false;

  const targetSig = sigParam.toLowerCase();

  // Accept candidate canonical representations
  const candidates = [
    `${key}:${expParam}`,
    `${url.pathname}:${expParam}`,
    `${key}?exp=${expParam}`,
    `${url.pathname}?exp=${expParam}`,
    `${expParam}:${key}`,
    key,
    url.pathname
  ];

  for (const candidate of candidates) {
    const expected = await hmacHex(secret, candidate);
    if (timingSafeEqual(expected.toLowerCase(), targetSig)) {
      return true;
    }
  }

  return false;
}

export function decodePublicKey(value: string): string | null {
  try {
    const key = decodeURIComponent(value);
    if (!key || key.includes('..') || key.startsWith('/') || key.includes('\\')) return null;
    return key;
  } catch {
    return null;
  }
}

export async function getObject(
  env: Env,
  key: string
): Promise<{ object: R2ObjectBody; bucket: 'media-origin' | 'blobs' } | null> {
  // Check MEDIA_ORIGIN first
  if (env.MEDIA_ORIGIN) {
    try {
      const obj = await env.MEDIA_ORIGIN.get(key);
      if (obj) return { object: obj, bucket: 'media-origin' };
    } catch {
      // Fallback
    }
  }

  // Fallback to BLOBS
  if (env.BLOBS) {
    try {
      const obj = await env.BLOBS.get(key);
      if (obj) return { object: obj, bucket: 'blobs' };
    } catch {
      // Not found
    }
  }

  return null;
}

export function notFound(): Response {
  return new Response('Not found', { status: 404, headers: { 'cache-control': 'no-store' } });
}

export function forbidden(code = 'SENSITIVE_ASSET_SIGNATURE_REQUIRED'): Response {
  return Response.json(
    {
      error: code,
      message: 'Access to sensitive assets requires a valid unexpired HMAC signature'
    },
    {
      status: 403,
      headers: {
        'cache-control': 'no-store',
        'content-type': 'application/json'
      }
    }
  );
}

export function serveObject(request: Request, object: R2ObjectBody): Response {
  const headers = new Headers({
    'cache-control': 'public, max-age=31536000, immutable',
    'content-type': object.httpMetadata?.contentType ?? 'application/octet-stream',
    etag: object.httpEtag,
    'x-content-type-options': 'nosniff'
  });
  if (object.size) headers.set('content-length', String(object.size));
  return new Response(request.method === 'HEAD' ? null : object.body, { headers });
}

export async function transformed(
  env: Env,
  object: R2ObjectBody,
  variantName: string,
  acceptHeader?: string | null
): Promise<Response> {
  const variant = VARIANTS[variantName];
  if (!variant || !object.body) return notFound();

  let outputFormat = 'image/avif';
  if (acceptHeader?.includes('image/webp') && !acceptHeader?.includes('image/avif')) {
    outputFormat = 'image/webp';
  }

  try {
    const transformBuilder = env.IMAGES.input(object.body)
      .transform({ width: variant.width, height: variant.height, fit: variant.fit })
      .output({ format: outputFormat, quality: variant.quality });

    const result = await transformBuilder;
    if (result && 'response' in result && typeof result.response === 'function') {
      const res = await result.response();
      const headers = new Headers(res.headers);
      headers.set('cache-control', 'public, max-age=31536000, immutable');
      headers.set('x-content-type-options', 'nosniff');
      return new Response(res.body, { status: res.status, headers });
    } else if (result && 'image' in result && typeof (result as any).image === 'function') {
      const body = (result as any).image();
      const headers = new Headers({
        'content-type': outputFormat,
        'cache-control': 'public, max-age=31536000, immutable',
        'x-content-type-options': 'nosniff'
      });
      return new Response(body, { status: 200, headers });
    }
    return notFound();
  } catch {
    return notFound();
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return notFound();
    }

    const url = new URL(request.url);
    const pathname = url.pathname;

    // Route: /health, /v1/health
    if (pathname === '/health' || pathname === '/v1/health') {
      return Response.json(
        { status: 'ok', service: 'hsc-media-delivery' },
        { status: 200, headers: { 'cache-control': 'no-store' } }
      );
    }

    // Route: /v1/public/*
    if (pathname.startsWith(PUBLIC_PREFIX)) {
      const rawKey = pathname.slice(PUBLIC_PREFIX.length);
      const key = decodePublicKey(rawKey);
      if (!key) return notFound();

      if (isSensitiveKey(key)) {
        const valid = await verifySignature(url, key, env.DELIVERY_SIGNING_SECRET);
        if (!valid) return forbidden();
      }

      if (!VERSIONED_PUBLIC_KEY.test(key)) return notFound();

      const item = await getObject(env, key);
      if (!item) return notFound();

      const variant = url.searchParams.get('variant');
      if (variant) {
        return transformed(env, item.object, variant, request.headers.get('accept'));
      }

      return serveObject(request, item.object);
    }

    // Route: /v1/transform/*
    if (pathname.startsWith('/v1/transform/')) {
      const remainder = pathname.slice('/v1/transform/'.length);
      const slashIdx = remainder.indexOf('/');
      let variantName = url.searchParams.get('variant');
      let rawKey = remainder;

      if (slashIdx !== -1) {
        const potentialVariant = remainder.slice(0, slashIdx);
        if (potentialVariant in VARIANTS) {
          variantName = potentialVariant;
          rawKey = remainder.slice(slashIdx + 1);
        }
      }

      if (!variantName || !(variantName in VARIANTS)) {
        return notFound();
      }

      const key = decodePublicKey(rawKey);
      if (!key) return notFound();

      if (isSensitiveKey(key)) {
        const valid = await verifySignature(url, key, env.DELIVERY_SIGNING_SECRET);
        if (!valid) return forbidden();
      }

      const item = await getObject(env, key);
      if (!item) return notFound();

      return transformed(env, item.object, variantName, request.headers.get('accept'));
    }

    // Route: /blobs/sha256/:prefix/:file and /v1/blobs/sha256/:prefix/:file
    const blobsMatch = pathname.match(/^(?:\/v1)?\/blobs\/sha256\/([^/]+)\/([^/]+)$/);
    if (blobsMatch) {
      const prefix = blobsMatch[1];
      const file = blobsMatch[2];
      if (!prefix || !file || prefix.includes('..') || file.includes('..')) {
        return notFound();
      }

      const key = `blobs/sha256/${prefix}/${file}`;
      if (isSensitiveKey(key)) {
        const valid = await verifySignature(url, key, env.DELIVERY_SIGNING_SECRET);
        if (!valid) return forbidden();
      }

      const item = await getObject(env, key);
      if (!item) return notFound();

      const variant = url.searchParams.get('variant');
      if (variant) {
        return transformed(env, item.object, variant, request.headers.get('accept'));
      }

      return serveObject(request, item.object);
    }

    // Route: /assets/:id/variants/:variant and /v1/assets/:id/variants/:variant
    const assetVariantMatch = pathname.match(/^(?:\/v1)?\/assets\/([^/]+)\/variants\/([^/]+)$/);
    if (assetVariantMatch) {
      const assetId = decodeURIComponent(assetVariantMatch[1]);
      const variantName = assetVariantMatch[2];
      if (!assetId || !variantName || assetId.includes('..')) {
        return notFound();
      }

      if (!(variantName in VARIANTS)) {
        return notFound();
      }

      if (isSensitiveKey(assetId) || isSensitiveKey(pathname)) {
        const valid = await verifySignature(url, assetId, env.DELIVERY_SIGNING_SECRET);
        if (!valid) return forbidden();
      }

      // 1. Check for cached derivatives in both buckets
      const cachedCandidates = [
        `derivatives/sha256/${assetId}/${variantName}.webp`,
        `derivatives/sha256/${assetId}/${variantName}.avif`,
        `derivatives/assets/${assetId}/${variantName}.webp`,
        `derivatives/assets/${assetId}/${variantName}.avif`,
        `assets/${assetId}/variants/${variantName}`
      ];

      for (const candidateKey of cachedCandidates) {
        const cached = await getObject(env, candidateKey);
        if (cached) {
          return serveObject(request, cached.object);
        }
      }

      // 2. Locate original asset across MEDIA_ORIGIN and BLOBS
      let originalResult: { object: R2ObjectBody; bucket: 'media-origin' | 'blobs' } | null = null;
      if (/^[a-f0-9]{64}$/i.test(assetId)) {
        const shaPrefix = assetId.slice(0, 2);
        const extensions = ['jpg', 'jpeg', 'png', 'webp', 'avif', 'gif'];
        for (const ext of extensions) {
          const candidateKey = `blobs/sha256/${shaPrefix}/${assetId}.${ext}`;
          const found = await getObject(env, candidateKey);
          if (found) {
            originalResult = found;
            break;
          }
        }

        if (!originalResult && env.BLOBS) {
          try {
            const list = await env.BLOBS.list({ prefix: `blobs/sha256/${shaPrefix}/${assetId}` });
            if (list.objects.length > 0) {
              const found = await env.BLOBS.get(list.objects[0].key);
              if (found) originalResult = { object: found, bucket: 'blobs' };
            }
          } catch {
            // Ignore list error
          }
        }
      }

      if (!originalResult) {
        const directKeys = [
          assetId,
          `assets/${assetId}`,
          `blobs/${assetId}`,
          `approved/${assetId}`
        ];
        for (const k of directKeys) {
          const found = await getObject(env, k);
          if (found) {
            originalResult = found;
            break;
          }
        }
      }

      if (!originalResult) return notFound();

      return transformed(env, originalResult.object, variantName, request.headers.get('accept'));
    }

    // Route: /assets/:id and /v1/assets/:id
    const assetMatch = pathname.match(/^(?:\/v1)?\/assets\/([^/]+)$/);
    if (assetMatch) {
      const assetId = decodeURIComponent(assetMatch[1]);
      if (!assetId || assetId.includes('..')) return notFound();

      if (isSensitiveKey(assetId) || isSensitiveKey(pathname)) {
        const valid = await verifySignature(url, assetId, env.DELIVERY_SIGNING_SECRET);
        if (!valid) return forbidden();
      }

      let originalResult: { object: R2ObjectBody; bucket: 'media-origin' | 'blobs' } | null = null;
      if (/^[a-f0-9]{64}$/i.test(assetId)) {
        const shaPrefix = assetId.slice(0, 2);
        const extensions = ['jpg', 'jpeg', 'png', 'webp', 'avif', 'gif'];
        for (const ext of extensions) {
          const candidateKey = `blobs/sha256/${shaPrefix}/${assetId}.${ext}`;
          const found = await getObject(env, candidateKey);
          if (found) {
            originalResult = found;
            break;
          }
        }
      }

      if (!originalResult) {
        const directKeys = [assetId, `assets/${assetId}`, `blobs/${assetId}`];
        for (const k of directKeys) {
          const found = await getObject(env, k);
          if (found) {
            originalResult = found;
            break;
          }
        }
      }

      if (!originalResult) return notFound();

      const variant = url.searchParams.get('variant');
      if (variant && variant in VARIANTS) {
        return transformed(env, originalResult.object, variant, request.headers.get('accept'));
      }

      return serveObject(request, originalResult.object);
    }

    return notFound();
  }
};
