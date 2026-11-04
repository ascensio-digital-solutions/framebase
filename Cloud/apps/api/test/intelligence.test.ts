import { Hono } from 'hono';
import { Jwt } from 'hono/utils/jwt';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GoogleAiStudioService } from '../src/services/googleAiStudio.js';
import { intelligenceRouter } from '../src/routes/intelligence.js';
import { derivativesRouter } from '../src/routes/derivatives.js';
import type { AppEnv, Bindings } from '../src/types.js';
import { enrollDevice } from './helpers.js';
import { createTestEnv } from './testEnv.js';
import { createFakeR2 } from './fakes/r2.js';

async function createDeviceWithScopes(env: Bindings, deviceId: string, scopes: string[]): Promise<string> {
  await env.DB.prepare(
    "INSERT OR REPLACE INTO devices (id, device_name, public_key, scopes, status) VALUES (?, ?, ?, ?, 'active')"
  ).bind(deviceId, `Device ${deviceId}`, 'test-key', JSON.stringify(scopes)).run();

  return await Jwt.sign(
    { sub: deviceId, scopes, iat: Math.floor(Date.now() / 1000), exp: Math.floor(Date.now() / 1000) + 3600 },
    env.JWT_SECRET as string,
    'HS256'
  );
}

describe('GoogleAiStudioService', () => {
  it('calls AI Gateway when configured and parses image vision analysis', async () => {
    let capturedUrl = '';
    const mockFetcher = vi.fn(async (url: string | URL | Request) => {
      capturedUrl = url.toString();
      return new Response(JSON.stringify({
        candidates: [{
          content: {
            parts: [{
              text: JSON.stringify({
                topFolder: 'Products',
                subfolder: 'Swiss Lace',
                proposedTags: ['lace', 'hairpiece', 'breathable'],
                caption: 'Premium Swiss lace hair replacement unit',
                ocrText: 'HSC-PRO',
                hairlineRealismScore: 9.8,
                baseMaterial: 'Swiss lace',
                confidence: 0.97
              })
            }]
          }
        }]
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    const service = new GoogleAiStudioService({
      apiKey: 'test-key-123',
      aiGatewayAccountId: 'test-account',
      aiGatewayName: 'test-gateway',
      fetcher: mockFetcher as unknown as typeof fetch
    });

    const result = await service.analyzeImageVision({
      imageBytes: new Uint8Array([1, 2, 3, 4]),
      mimeType: 'image/jpeg',
      librarySpace: 'hsc',
      filename: 'lace-front.jpg',
      ocrHint: 'HSC'
    });

    expect(capturedUrl).toContain('gateway.ai.cloudflare.com/v1/test-account/test-gateway/google-ai-studio/v1beta/models/gemini-3.8-flash:generateContent');
    expect(result.topFolder).toBe('Products');
    expect(result.subfolder).toBe('Swiss Lace');
    expect(result.proposedTags).toEqual(['lace', 'hairpiece', 'breathable']);
    expect(result.hairlineRealismScore).toBe(9.8);
    expect(result.baseMaterial).toBe('Swiss lace');
    expect(result.confidence).toBe(0.97);
  });

  it('falls back to direct Google AI Studio if AI Gateway fails', async () => {
    const urlsCalled: string[] = [];
    const fallbackFetcher = vi.fn(async (url: string | URL | Request) => {
      const u = url.toString();
      urlsCalled.push(u);
      if (u.includes('gateway.ai.cloudflare.com')) {
        return new Response('Gateway Bad Gateway', { status: 502 });
      }
      return new Response(JSON.stringify({
        candidates: [{
          content: {
            parts: [{
              text: JSON.stringify({
                topFolder: 'Transformations',
                subfolder: 'Before & After',
                proposedTags: ['transformation'],
                caption: 'Direct fallback caption',
                ocrText: '',
                confidence: 0.91
              })
            }]
          }
        }]
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    const service = new GoogleAiStudioService({
      apiKey: 'fallback-key',
      aiGatewayAccountId: 'test-account',
      aiGatewayName: 'test-gateway',
      fetcher: fallbackFetcher as unknown as typeof fetch
    });

    const result = await service.analyzeImageVision({
      imageBytes: new Uint8Array([10, 20]),
      mimeType: 'image/png',
      librarySpace: 'hsc'
    });

    expect(urlsCalled.length).toBe(2);
    expect(urlsCalled[0]).toContain('gateway.ai.cloudflare.com');
    expect(urlsCalled[1]).toContain('generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent');
    expect(result.topFolder).toBe('Transformations');
    expect(result.caption).toBe('Direct fallback caption');
  });

  it('generates 1024-dimensional multimodal embeddings', async () => {
    let requestBody: any = null;
    const mockFetcher = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      requestBody = JSON.parse(init?.body as string);
      return new Response(JSON.stringify({
        embedding: {
          values: new Array(1024).fill(0.05)
        }
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    const service = new GoogleAiStudioService({
      apiKey: 'embed-key',
      fetcher: mockFetcher as unknown as typeof fetch
    });

    const embedding = await service.embedMultimodal({
      text: 'search query for thin skin toupee',
      outputDimensionality: 1024
    });

    expect(embedding.length).toBe(1024);
    expect(embedding[0]).toBe(0.05);
    expect(requestBody.outputDimensionality).toBe(1024);
    expect(requestBody.content.parts[0].text).toBe('search query for thin skin toupee');
  });

  it('analyzes video summary with gemini-omni-1.1-flash', async () => {
    let capturedUrl = '';
    const mockFetcher = vi.fn(async (url: string | URL | Request) => {
      capturedUrl = url.toString();
      return new Response(JSON.stringify({
        candidates: [{
          content: {
            parts: [{
              text: JSON.stringify({
                scenes: [
                  { timestamp: '00:00 - 00:20', description: 'Scalp preparation' },
                  { timestamp: '00:20 - 01:00', description: 'Attaching the lace unit' }
                ],
                transcriptSummary: 'Detailed tutorial on preparing skin and installing lace unit.'
              })
            }]
          }
        }]
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    const service = new GoogleAiStudioService({
      apiKey: 'omni-key',
      fetcher: mockFetcher as unknown as typeof fetch
    });

    const summary = await service.analyzeVideoSummary({
      videoBytes: new Uint8Array([5, 6, 7, 8]),
      mimeType: 'video/mp4'
    });

    expect(capturedUrl).toContain('gemini-omni-1.1-flash:generateContent');
    expect(summary.scenes.length).toBe(2);
    expect(summary.scenes[0].description).toBe('Scalp preparation');
    expect(summary.transcriptSummary).toContain('Detailed tutorial');
  });
});

describe('intelligenceRouter', () => {
  let env: Bindings;
  let testApp: Hono<AppEnv>;

  beforeEach(async () => {
    env = createTestEnv();

    testApp = new Hono<AppEnv>();
    testApp.use('*', async (c, next) => {
      c.set('requestId', 'test-req-id');
      await next();
    });
    testApp.route('/v1', intelligenceRouter);
    testApp.route('/v1', derivativesRouter);

    // Insert test asset into D1
    await env.DB.prepare(
      `INSERT INTO blobs (id, sha256, byte_size, media_type, original_extension, r2_key, upload_state)
       VALUES (?, ?, ?, ?, ?, ?, 'verified')`
    ).bind('blob-100', 'sha256-photo-100', 4096, 'image/jpeg', 'jpg', 'originals/sha256-photo-100.jpg').run();

    await env.DB.prepare(
      `INSERT INTO assets (id, blob_id, display_name, folder_id, status)
       VALUES (?, ?, ?, 'system-inbox', 'active')`
    ).bind('asset-100', 'blob-100', 'toupee-front.jpg').run();
  });

  it('requires library.write auth for analyze endpoint', async () => {
    // No token -> 401
    const resNoAuth = await testApp.request('/v1/intelligence/analyze/asset-100', { method: 'POST' }, env);
    expect(resNoAuth.status).toBe(401);

    // Token with only library.read -> 403
    const readToken = await enrollDevice(env, 'read-only-device', ['library.read']);
    const resForbidden = await testApp.request('/v1/intelligence/analyze/asset-100', {
      method: 'POST',
      headers: { Authorization: `Bearer ${readToken}` }
    }, env);
    expect(resForbidden.status).toBe(403);
  });

  it('analyzes asset, generates embeddings, and indexes in VECTORIZE when bound', async () => {
    const writeToken = await createDeviceWithScopes(env, 'writer-device', ['library.write', 'library.read']);

    // Place grid-512 derivative in BLOBS
    await env.BLOBS.put('derivatives/v1/sha256-photo-100/grid-512.webp', new Uint8Array([1, 2, 3, 4]));

    const mockFetcher = vi.fn(async (url: string | URL | Request) => {
      const u = url.toString();
      if (u.includes('generateContent')) {
        return new Response(JSON.stringify({
          candidates: [{
            content: {
              parts: [{
                text: JSON.stringify({
                  topFolder: 'Products',
                  subfolder: 'Skin Units',
                  proposedTags: ['skin', 'poly', '0.03mm'],
                  caption: 'Ultra-thin skin unit with natural front contour',
                  ocrText: '',
                  hairlineRealismScore: 9.2,
                  baseMaterial: 'polyurethane',
                  confidence: 0.94
                })
              }]
            }
          }]
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      if (u.includes('embedContent')) {
        return new Response(JSON.stringify({
          embedding: {
            values: new Array(1024).fill(0.123)
          }
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      return new Response('Not found', { status: 404 });
    });

    const vectorizeUpserts: any[] = [];
    const mockVectorize = {
      async upsert(records: any[]) {
        vectorizeUpserts.push(...(Array.isArray(records) ? records : [records]));
        return { count: 1, ids: ['asset-100'] };
      }
    };

    const workersAiRuns: any[] = [];
    const mockWorkersAI = {
      async run(model: string, input: any) {
        workersAiRuns.push({ model, input });
        return { description: 'Workers AI visual summary' };
      }
    };

    const customEnv: Bindings & {
      AI_FETCHER: typeof fetch;
      VECTORIZE: typeof mockVectorize;
      AI: typeof mockWorkersAI;
    } = {
      ...env,
      AI_FETCHER: mockFetcher as unknown as typeof fetch,
      VECTORIZE: mockVectorize,
      AI: mockWorkersAI
    };

    const res = await testApp.request('/v1/intelligence/analyze/asset-100', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${writeToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ librarySpace: 'hsc' })
    }, customEnv);

    expect(res.status).toBe(200);
    const body = await res.json<{
      status: string;
      assetId: string;
      analysis: any;
      vectorIndexed: boolean;
    }>();

    expect(body.status).toBe('ok');
    expect(body.assetId).toBe('asset-100');
    expect(body.analysis.topFolder).toBe('Products');
    expect(body.analysis.hairlineRealismScore).toBe(9.2);
    expect(body.vectorIndexed).toBe(true);

    // Verify Workers AI tier-1 was called
    expect(workersAiRuns.length).toBe(1);

    // Verify Vectorize upsert
    expect(vectorizeUpserts.length).toBe(1);
    expect(vectorizeUpserts[0].id).toBe('asset-100');
    expect(vectorizeUpserts[0].metadata.catalog_id).toBe('framebase-dev-library');
    expect(vectorizeUpserts[0].metadata.top_folder).toBe('Products');
    expect(vectorizeUpserts[0].values.length).toBe(1024);
  });

  it('performs semantic search against VECTORIZE and joins asset rows', async () => {
    const readToken = await enrollDevice(env, 'search-device', ['library.read']);

    const mockFetcher = vi.fn(async (url: string | URL | Request) => {
      const u = url.toString();
      if (u.includes('embedContent')) {
        return new Response(JSON.stringify({
          embedding: {
            values: new Array(1024).fill(0.777)
          }
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response('Not found', { status: 404 });
    });

    const mockVectorize = {
      async query(_vector: number[], _options: any) {
        return {
          matches: [
            {
              id: 'asset-100',
              score: 0.98,
              metadata: {
                catalog_id: 'framebase-dev-library',
                asset_id: 'asset-100',
                top_folder: 'Products'
              }
            },
            {
              id: 'foreign-asset',
              score: 0.99,
              metadata: {
                catalog_id: 'different-library',
                asset_id: 'foreign-asset',
                top_folder: 'Unknown'
              }
            }
          ]
        };
      }
    };

    const customEnv: Bindings & {
      AI_FETCHER: typeof fetch;
      VECTORIZE: typeof mockVectorize;
    } = {
      ...env,
      AI_FETCHER: mockFetcher as unknown as typeof fetch,
      VECTORIZE: mockVectorize
    };

    const res = await testApp.request('/v1/search/semantic', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${readToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        query: 'natural hairpiece with thin skin base',
        limit: 10
      })
    }, customEnv);

    expect(res.status).toBe(200);
    const body = await res.json<{ matches: any[] }>();

    // Foreign catalog match was filtered out
    expect(body.matches.length).toBe(1);
    expect(body.matches[0].id).toBe('asset-100');
    expect(body.matches[0].score).toBe(0.98);
    expect(body.matches[0].asset.displayName).toBe('toupee-front.jpg');
    expect(body.matches[0].asset.sha256).toBe('sha256-photo-100');
  });

  it('returns 503 for semantic search when Vectorize is unconfigured', async () => {
    const readToken = await enrollDevice(env, 'search-device-2', ['library.read']);
    const res = await testApp.request('/v1/search/semantic', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${readToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ query: 'hello' })
    }, env);

    expect(res.status).toBe(503);
    const body = await res.json<{ error: { code: string } }>();
    expect(body.error.code).toBe('VECTOR_SEARCH_UNAVAILABLE');
  });

  it('supports all 9 derivative presets and falls back to LEGACY_ORIGIN if BLOBS is missing the original', async () => {
    const readToken = await enrollDevice(env, 'deriv-device', ['library.read']);

    // Check all 9 presets are recognized (none return 404 DERIVATIVE_VARIANT_NOT_FOUND)
    const variants = [
      'grid-256',
      'grid-512',
      'preview-1600',
      'shopify-product',
      'shopify-card',
      'email-hero',
      'email-module',
      'social-square',
      'social-story'
    ];

    // Mock IMAGES binding
    const mockImages = {
      input: () => ({
        transform: () => ({
          output: () => ({
            image: () => new ReadableStream({
              start(controller) {
                controller.enqueue(new Uint8Array([10, 20, 30]));
                controller.close();
              }
            })
          })
        })
      })
    };

    const legacyBucket = createFakeR2();
    // Put original in legacy bucket only (NOT in BLOBS)
    await legacyBucket.put('originals/sha256-photo-100.jpg', new Uint8Array([99, 98, 97]));

    const customEnv: Bindings & {
      IMAGES: typeof mockImages;
      LEGACY_ORIGIN: typeof legacyBucket;
    } = {
      ...env,
      IMAGES: mockImages as any,
      LEGACY_ORIGIN: legacyBucket
    };

    for (const v of variants) {
      const res = await testApp.request(`/v1/assets/asset-100/variants/${v}`, {
        method: 'GET',
        headers: { Authorization: `Bearer ${readToken}` }
      }, customEnv);

      expect(res.status).toBe(200);
      expect(res.headers.get('Content-Type')).toBe('image/webp');
      expect(res.headers.get('X-Framebase-Derivative-Cache')).toBe('MISS');
    }
  });
});
