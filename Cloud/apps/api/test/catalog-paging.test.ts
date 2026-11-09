import { beforeEach, describe, expect, it } from 'vitest';
import app from '../src/index.js';
import type { Bindings } from '../src/types.js';
import { enrollDevice } from './helpers.js';
import { createTestEnv } from './testEnv.js';

interface Page {
  watermarkRevision: number;
  entities: { entityType: string; entityId: string; revision: number; payload: Record<string, unknown> }[];
  nextCursor: string | null;
}

async function seed(env: Bindings) {
  const sha = (n: number) => String(n).repeat(64).slice(0, 64);
  for (const n of [1, 2, 3, 4, 5]) {
    await env.DB.prepare(
      "INSERT INTO blobs (id, sha256, byte_size, media_type, original_extension, r2_key, upload_state) VALUES (?, ?, 10, 'image/jpeg', 'jpg', ?, 'verified')"
    ).bind(sha(n), sha(n), `blobs/sha256/${n}${n}/${sha(n)}.jpg`).run();
    await env.DB.prepare(
      "INSERT INTO assets (id, blob_id, display_name, folder_id, asset_metadata, revision) VALUES (?, ?, ?, 'system-inbox', '{}', 1)"
    ).bind(`asset-${n}`, sha(n), `Photo ${n}`).run();
  }
  await env.DB.prepare("INSERT INTO albums (id, name, sort_order, revision) VALUES ('album-a', 'Album A', 1, 1), ('album-b', 'Album B', 2, 1)").run();
  await env.DB.prepare("INSERT INTO album_assets (album_id, asset_id, sort_order) VALUES ('album-a', 'asset-1', 1), ('album-a', 'asset-2', 2), ('album-b', 'asset-3', 1)").run();
  await env.DB.prepare("INSERT INTO tags (id, name, revision) VALUES ('tag-x', 'status:review', 1), ('tag-y', 'status:approved', 1), ('tag-z', 'topic:lace', 1)").run();
  await env.DB.prepare("INSERT INTO asset_tags (asset_id, tag_id) VALUES ('asset-1', 'tag-x'), ('asset-2', 'tag-x'), ('asset-5', 'tag-y')").run();
}

describe('catalog bootstrap paging', () => {
  let env: Bindings;
  let token: string;
  const get = async (query: string): Promise<Page> => {
    const res = await app.request(`/v1/catalog/bootstrap?${query}`, { headers: { Authorization: `Bearer ${token}` } }, env);
    expect(res.status).toBe(200);
    return res.json<Page>();
  };

  beforeEach(async () => {
    env = createTestEnv();
    await seed(env);
    token = await enrollDevice(env, 'device-paging', ['library.read']);
  });

  it('returns the same entities in the same order however it is paged', async () => {
    const whole = await get('limit=500');
    expect(whole.nextCursor).toBeNull();

    for (const size of [1, 2, 3, 7]) {
      const collected: Page['entities'] = [];
      let cursor: string | null = '0';
      let pages = 0;
      while (cursor !== null) {
        const page: Page = await get(`limit=${size}&cursor=${cursor}`);
        expect(page.entities.length).toBeLessThanOrEqual(size);
        collected.push(...page.entities);
        cursor = page.nextCursor;
        expect(++pages).toBeLessThan(200);
      }
      expect(collected, `page size ${size}`).toEqual(whole.entities);
    }
  });

  it('lists every entity type once, grouped by type and ordered by id', async () => {
    const { entities } = await get('limit=500');
    const types = [...new Set(entities.map((e) => e.entityType))];
    expect(types).toEqual([...types].sort());
    expect(types).toEqual(expect.arrayContaining(['album', 'asset', 'folder', 'tag']));
    for (const type of types) {
      const ids = entities.filter((e) => e.entityType === type).map((e) => e.entityId);
      expect(ids).toEqual([...ids].sort());
      expect(new Set(ids).size).toBe(ids.length);
    }
    expect(entities.filter((e) => e.entityType === 'asset')).toHaveLength(5);
  });

  it('attaches the right memberships to albums and tags', async () => {
    const { entities } = await get('limit=500');
    const payload = (type: string, id: string) => entities.find((e) => e.entityType === type && e.entityId === id)?.payload as { assetIds: string[] };
    expect(payload('album', 'album-a').assetIds).toEqual(['asset-1', 'asset-2']);
    expect(payload('album', 'album-b').assetIds).toEqual(['asset-3']);
    expect(payload('tag', 'tag-x').assetIds).toEqual(['asset-1', 'asset-2']);
    expect(payload('tag', 'tag-z').assetIds).toEqual([]);
  });

  it('keeps trash receipts on trashed assets', async () => {
    await env.DB.prepare("UPDATE assets SET status = 'trashed' WHERE id = 'asset-4'").run();
    await env.DB.prepare(
      "INSERT INTO asset_trash (asset_id, prior_folder_id, prior_album_ids_json, prior_tag_ids_json, trashed_at, scheduled_purge_at) VALUES ('asset-4', 'system-inbox', '[]', '[]', '2026-01-01T00:00:00Z', '2026-02-01T00:00:00Z')"
    ).run();
    const { entities } = await get('limit=2'); // trash lookup must also work on a small page
    let all = entities;
    let cursor = (await get('limit=2')).nextCursor;
    while (cursor) {
      const page = await get(`limit=2&cursor=${cursor}`);
      all = all.concat(page.entities);
      cursor = page.nextCursor;
    }
    const trashed = all.find((e) => e.entityId === 'asset-4')?.payload as { trash: { priorFolderId: string } | null };
    expect(trashed.trash?.priorFolderId).toBe('system-inbox');
    expect((all.find((e) => e.entityId === 'asset-1')?.payload as { trash: unknown }).trash).toBeNull();
  });

  it('accepts a cursor beyond the old 100,000 limit and rejects nonsense', async () => {
    const far = await get('limit=10&cursor=150000');
    expect(far.entities).toEqual([]);
    expect(far.nextCursor).toBeNull();
    for (const query of ['cursor=-1', 'cursor=abc', 'limit=0', 'limit=501', 'cursor=99999999']) {
      const res = await app.request(`/v1/catalog/bootstrap?${query}`, { headers: { Authorization: `Bearer ${token}` } }, env);
      expect(res.status, query).toBe(400);
    }
  });
});
