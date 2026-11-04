import { beforeEach, describe, expect, it } from 'vitest';
import app from '../src/index.js';
import type { AssistantChatResponse } from '../src/routes/assistant.js';
import type { Bindings } from '../src/types.js';
import { createTestEnv } from './testEnv.js';

describe('POST /v1/assistant/chat', () => {
  let env: Bindings;

  beforeEach(async () => {
    env = createTestEnv();

    // Seed folders, blobs, assets, and tags into D1
    await env.DB.prepare(
      `INSERT INTO folders (id, name, system_kind, revision)
       VALUES ('folder-models-alex', '03_people/models/alex', NULL, 1),
              ('folder-knowledge-crm', '02_saas_&_crm', NULL, 1)`
    ).run();

    await env.DB.prepare(
      `INSERT INTO blobs (id, sha256, byte_size, media_type, original_extension, r2_key, upload_state)
       VALUES ('blob-blonde-1', 'sha-blonde-1', 2048, 'image/jpeg', 'jpg', 'originals/blonde-1.jpg', 'verified'),
              ('blob-model-1', 'sha-model-1', 2048, 'image/jpeg', 'jpg', 'originals/alex-headshot.jpg', 'verified'),
              ('blob-crm-1', 'sha-crm-1', 2048, 'image/png', 'png', 'originals/twenty-crm-repo.png', 'verified')`
    ).run();

    await env.DB.prepare(
      `INSERT INTO assets (id, blob_id, display_name, folder_id, status, asset_metadata)
       VALUES ('asset-blonde-hairline-1', 'blob-blonde-1', 'blonde-lace-hairline.jpg', 'system-inbox', 'active', '{"hairColor":"blonde","hairline":"clearly-visible"}'),
              ('asset-alex-headshot-1', 'blob-model-1', 'alex-headshot-studio.jpg', 'folder-models-alex', 'active', '{"subject_count":"single_person"}'),
              ('asset-crm-screenshot-1', 'blob-crm-1', 'twenty-open-source-crm-github.png', 'folder-knowledge-crm', 'active', '{"repo":"twentyhq/twenty","topic":"crm"}')`
    ).run();

    await env.DB.prepare(
      `INSERT INTO tags (id, name, revision)
       VALUES ('tag-hairline', 'hairline:clearly-visible', 1),
              ('tag-blonde', 'color:22', 1),
              ('tag-crm', 'topic:crm', 1)`
    ).run();

    await env.DB.prepare(
      `INSERT INTO asset_tags (asset_id, tag_id)
       VALUES ('asset-blonde-hairline-1', 'tag-hairline'),
              ('asset-blonde-hairline-1', 'tag-blonde'),
              ('asset-crm-screenshot-1', 'tag-crm')`
    ).run();
  });

  it('1. plans create_album_from_query and search_library for blonde hairline photos and returns matched assets', async () => {
    const customEnv: Bindings = {
      ...env,
      VECTORIZE_INDEX: {
        async upsert() {
          return {};
        },
        async query() {
          return {
            matches: [
              { id: 'asset-blonde-hairline-vec-2', score: 0.94, metadata: { hairColor: 'blonde' } }
            ]
          };
        }
      }
    };

    const res = await app.request(
      '/v1/assistant/chat',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          librarySpace: 'hsc',
          message: 'Create an album for me with all the hairline photos with color blonde hair',
          catalogContext: {
            topTags: ['hairline:clearly-visible', 'color:22', 'base:swiss-lace']
          }
        })
      },
      customEnv
    );

    expect(res.status).toBe(200);
    const body = await res.json<AssistantChatResponse>();

    expect(body.reply).toContain('Blonde Hairlines');
    expect(body.toolCalls.length).toBeGreaterThanOrEqual(1);

    const createAlbumCall = body.toolCalls.find((tc) => tc.tool === 'create_album_from_query');
    expect(createAlbumCall).toBeDefined();
    expect(createAlbumCall?.arguments.albumName).toBe('Blonde Hairlines');
    expect(createAlbumCall?.arguments.hairColor).toBe('blonde');
    expect(createAlbumCall?.arguments.hairlinePresentation).toBe('clearly-visible');
    expect(createAlbumCall?.arguments.tags).toEqual(
      expect.arrayContaining(['hairline:clearly-visible', 'color:22'])
    );

    const searchCall = body.toolCalls.find((tc) => tc.tool === 'search_library');
    expect(searchCall).toBeDefined();
    expect(searchCall?.arguments.hairColor).toBe('blonde');
    expect(searchCall?.arguments.hairlinePresentation).toBe('clearly-visible');

    expect(body.matchedAssetIds).toEqual(
      expect.arrayContaining(['asset-blonde-hairline-1', 'asset-blonde-hairline-vec-2'])
    );
  });

  it('2. plans organize_into_subfolders when asked to split a model folder into headshots, editorial, before-after', async () => {
    const res = await app.request(
      '/v1/assistant/chat',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          librarySpace: 'hsc',
          message: 'Split the model folder 03_people/models/alex into headshots, editorial, and before-after subfolders',
          catalogContext: {
            folders: [{ id: 'folder-models-alex', path: '03_people/models/alex', assetCount: 24 }]
          }
        })
      },
      env
    );

    expect(res.status).toBe(200);
    const body = await res.json<AssistantChatResponse>();

    const organizeCall = body.toolCalls.find((tc) => tc.tool === 'organize_into_subfolders');
    expect(organizeCall).toBeDefined();
    expect(organizeCall?.arguments.folderPath).toBe('03_people/models/alex');
    expect(organizeCall?.arguments.subfolders).toEqual(['headshots', 'editorial', 'before-after']);
    expect(organizeCall?.arguments.tags).toEqual(expect.arrayContaining(['subject_count:single_person']));
    expect(body.matchedAssetIds).toContain('asset-alex-headshot-1');
  });

  it('3. plans find_knowledge_repos when searching screenshots for open-source CRM repos', async () => {
    const customEnv: Bindings = {
      ...env,
      AI_GATEWAY_ID: 'framebase-vision-dev',
      CF_ACCOUNT_ID: '938d6ab84fe239647496cc1540ffa21f',
      AI: {
        async run() {
          return {
            response: 'Found open-source CRM repositories in your Knowledge Library screenshots, including twentyhq/twenty.'
          };
        }
      }
    };

    const res = await app.request(
      '/v1/assistant/chat',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          librarySpace: 'knowledge',
          message: 'Find all open-source CRM repos in my screenshots',
          catalogContext: {
            folders: [{ id: 'folder-knowledge-crm', path: '02_saas_&_crm', assetCount: 12 }]
          }
        })
      },
      customEnv
    );

    expect(res.status).toBe(200);
    const body = await res.json<AssistantChatResponse>();

    const repoCall = body.toolCalls.find((tc) => tc.tool === 'find_knowledge_repos');
    expect(repoCall).toBeDefined();
    expect(repoCall?.arguments.topic).toBe('crm');
    expect(repoCall?.arguments.tags).toEqual(
      expect.arrayContaining(['source:screenshot', 'category:open-source', 'topic:crm'])
    );
    expect(body.matchedAssetIds).toContain('asset-crm-screenshot-1');
    expect(body.provider).toBe('cloudflare-ai-gateway:framebase-vision-dev');
    expect(body.reply).toContain('twentyhq/twenty');
  });
});
