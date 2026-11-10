import { beforeEach, describe, expect, it } from 'vitest';
import app from '../src/index.js';
import type { Bindings } from '../src/types.js';
import { enrollDevice } from './helpers.js';
import { createTestEnv } from './testEnv.js';

describe('fixed cloud derivatives', () => {
  let env: Bindings;

  beforeEach(() => { env = createTestEnv(); });

  it('fails closed when the paid Images binding is not configured', async () => {
    const token = await enrollDevice(env, 'device-derivative', ['library.read']);
    const response = await app.request('/v1/assets/missing/variants/grid-256', {
      headers: { Authorization: `Bearer ${token}` }
    }, env);
    expect(response.status).toBe(503);
    expect((await response.json<{ error: { code: string } }>()).error.code).toBe('DERIVATIVE_SERVICE_UNAVAILABLE');
  });

  it('renders a derivative, caches its bytes, and serves the cache next time', async () => {
    // Real R2 rejects a stream of unknown length; the default fake accepts anything, so make it strict.
    const inner = env.BLOBS;
    const strictBlobs = {
      ...inner,
      put: (key: string, value: unknown, options?: unknown) => {
        if (value instanceof ReadableStream) {
          throw new TypeError('Provided readable stream must have a known length');
        }
        return (inner as unknown as { put: (...a: unknown[]) => Promise<unknown> }).put(key, value, options);
      },
      get: (key: string) => (inner as unknown as { get: (k: string) => Promise<unknown> }).get(key)
    };
    const images = {
      input: () => ({
        transform: () => ({
          output: () => ({
            image: () =>
              new ReadableStream({
                start(controller) {
                  controller.enqueue(new Uint8Array([10, 20, 30]));
                  controller.close();
                }
              })
          })
        })
      })
    };
    const customEnv = { ...env, BLOBS: strictBlobs, IMAGES: images } as unknown as Bindings;

    const digest = 'b'.repeat(64);
    await env.DB.prepare(
      "INSERT INTO blobs (id, sha256, byte_size, media_type, original_extension, r2_key, upload_state) VALUES (?, ?, 3, 'image/jpeg', 'jpg', 'blobs/photo.jpg', 'verified')"
    ).bind(digest, digest).run();
    await env.DB.prepare(
      "INSERT INTO assets (id, blob_id, display_name, folder_id, asset_metadata, revision) VALUES ('asset-derivative', ?, 'Derivative Fixture', 'system-inbox', '{}', 1)"
    ).bind(digest).run();
    await inner.put('blobs/photo.jpg', new Uint8Array([1, 2, 3]));
    const token = await enrollDevice(env, 'device-derivative-render', ['library.read']);
    const request = () =>
      app.request('/v1/assets/asset-derivative/variants/grid-256', { headers: { Authorization: `Bearer ${token}` } }, customEnv);

    const first = await request();
    expect(first.status).toBe(200);
    expect(first.headers.get('X-Framebase-Derivative-Cache')).toBe('MISS');
    expect([...new Uint8Array(await first.arrayBuffer())]).toEqual([10, 20, 30]);

    const second = await request();
    expect(second.status).toBe(200);
    expect(second.headers.get('X-Framebase-Derivative-Cache')).toBe('HIT');
    expect([...new Uint8Array(await second.arrayBuffer())]).toEqual([10, 20, 30]);
  });

  it('rejects arbitrary variants before any source lookup', async () => {
    const token = await enrollDevice(env, 'device-derivative-variant', ['library.read']);
    const response = await app.request('/v1/assets/missing/variants/anything', {
      headers: { Authorization: `Bearer ${token}` }
    }, env);
    expect(response.status).toBe(404);
  });
});
