import { Hono } from 'hono';
import { apiError, parseBoundedInteger } from '../lib/api.js';
import { requireAuth } from '../middleware/auth.js';
import type { AppEnv } from '../types.js';

export const catalogRouter = new Hono<AppEnv>();

interface SnapshotEntity {
  entityType: 'folder' | 'asset' | 'album' | 'tag' | 'saved_search' | 'export_receipt' | 'backup_manifest';
  entityId: string;
  revision: number;
  payload: Record<string, unknown>;
}

// The snapshot is the concatenation of these entity lists, in this order (alphabetical by type, then by id).
// A page reads only the rows it needs, so the cost of one page does not grow with the size of the library.
const TYPES = ['album', 'asset', 'backup_manifest', 'export_receipt', 'folder', 'saved_search', 'tag'] as const;
type EntityType = (typeof TYPES)[number];

const TABLE: Record<EntityType, string> = {
  album: 'albums',
  asset: 'assets',
  backup_manifest: 'backup_manifests',
  export_receipt: 'export_receipts',
  folder: 'folders',
  saved_search: 'saved_searches',
  tag: 'tags'
};

// Large enough for a few hundred thousand entities; the cursor is an offset into the concatenated list.
const MAX_CURSOR = 5_000_000;

async function loadPage(db: D1Database, type: EntityType, limit: number, offset: number): Promise<SnapshotEntity[]> {
  switch (type) {
    case 'folder': {
      const rows = await db.prepare(
        'SELECT id, name, parent_id, system_kind, sort_order, revision, created_at, updated_at FROM folders ORDER BY id LIMIT ? OFFSET ?'
      ).bind(limit, offset).all<{ id: string; name: string; parent_id: string | null; system_kind: string | null; sort_order: number; revision: number; created_at: string; updated_at: string }>();
      return rows.results.map((folder) => ({
        entityType: 'folder' as const,
        entityId: folder.id,
        revision: folder.revision,
        payload: {
          id: folder.id, name: folder.name, parentId: folder.parent_id, systemKind: folder.system_kind,
          sortOrder: folder.sort_order, createdAt: folder.created_at, updatedAt: folder.updated_at
        }
      }));
    }
    case 'asset': {
      const rows = await db.prepare(`SELECT assets.id, assets.blob_id, assets.display_name, assets.folder_id, assets.favorite, assets.rating,
        assets.status, assets.asset_metadata, assets.revision, assets.created_at, assets.updated_at,
        blobs.byte_size AS blob_byte_size, blobs.media_type AS blob_media_type, blobs.original_extension AS blob_original_extension
        FROM assets JOIN blobs ON blobs.id = assets.blob_id ORDER BY assets.id LIMIT ? OFFSET ?`).bind(limit, offset).all<{
        id: string; blob_id: string; display_name: string; folder_id: string; favorite: number; rating: number; status: string;
        asset_metadata: string; revision: number; created_at: string; updated_at: string; blob_byte_size: number; blob_media_type: string; blob_original_extension: string;
      }>();
      const ids = JSON.stringify(rows.results.map((row) => row.id));
      const trashRows = rows.results.length === 0 ? { results: [] } : await db.prepare(
        `SELECT asset_id, prior_folder_id, prior_album_ids_json, prior_tag_ids_json, trashed_at, scheduled_purge_at
         FROM asset_trash WHERE asset_id IN (SELECT value FROM json_each(?))`
      ).bind(ids).all<{ asset_id: string; prior_folder_id: string; prior_album_ids_json: string; prior_tag_ids_json: string; trashed_at: string; scheduled_purge_at: string }>();
      const trashByAssetID = new Map(trashRows.results.map((trash) => [trash.asset_id, trash]));
      return rows.results.map((asset) => {
        const trash = trashByAssetID.get(asset.id);
        return {
          entityType: 'asset' as const,
          entityId: asset.id,
          revision: asset.revision,
          payload: {
            id: asset.id, blobId: asset.blob_id, displayName: asset.display_name, folderId: asset.folder_id,
            favorite: Boolean(asset.favorite), rating: asset.rating, status: asset.status,
            assetMetadata: JSON.parse(asset.asset_metadata),
            blob: { sha256: asset.blob_id, byteSize: asset.blob_byte_size, mediaType: asset.blob_media_type, originalExtension: asset.blob_original_extension },
            createdAt: asset.created_at, updatedAt: asset.updated_at,
            trash: trash ? {
              priorFolderId: trash.prior_folder_id,
              priorAlbumIds: JSON.parse(trash.prior_album_ids_json),
              priorTagIds: JSON.parse(trash.prior_tag_ids_json),
              trashedAt: trash.trashed_at,
              scheduledPurgeAt: trash.scheduled_purge_at
            } : null
          }
        };
      });
    }
    case 'album': {
      const rows = await db.prepare('SELECT id, name, sort_order, revision, created_at, updated_at FROM albums ORDER BY id LIMIT ? OFFSET ?')
        .bind(limit, offset).all<{ id: string; name: string; sort_order: number; revision: number; created_at: string; updated_at: string }>();
      const members = rows.results.length === 0 ? { results: [] } : await db.prepare(
        'SELECT album_id, asset_id FROM album_assets WHERE album_id IN (SELECT value FROM json_each(?)) ORDER BY album_id, sort_order, asset_id'
      ).bind(JSON.stringify(rows.results.map((row) => row.id))).all<{ album_id: string; asset_id: string }>();
      const byAlbum = new Map<string, string[]>();
      for (const membership of members.results) {
        const list = byAlbum.get(membership.album_id) ?? [];
        list.push(membership.asset_id);
        byAlbum.set(membership.album_id, list);
      }
      return rows.results.map((album) => ({
        entityType: 'album' as const,
        entityId: album.id,
        revision: album.revision,
        payload: { id: album.id, name: album.name, sortOrder: album.sort_order, assetIds: byAlbum.get(album.id) ?? [], createdAt: album.created_at, updatedAt: album.updated_at }
      }));
    }
    case 'tag': {
      const rows = await db.prepare('SELECT id, name, revision, created_at, updated_at FROM tags ORDER BY id LIMIT ? OFFSET ?')
        .bind(limit, offset).all<{ id: string; name: string; revision: number; created_at: string; updated_at: string }>();
      const members = rows.results.length === 0 ? { results: [] } : await db.prepare(
        'SELECT tag_id, asset_id FROM asset_tags WHERE tag_id IN (SELECT value FROM json_each(?)) ORDER BY tag_id, asset_id'
      ).bind(JSON.stringify(rows.results.map((row) => row.id))).all<{ tag_id: string; asset_id: string }>();
      const byTag = new Map<string, string[]>();
      for (const membership of members.results) {
        const list = byTag.get(membership.tag_id) ?? [];
        list.push(membership.asset_id);
        byTag.set(membership.tag_id, list);
      }
      return rows.results.map((tag) => ({
        entityType: 'tag' as const,
        entityId: tag.id,
        revision: tag.revision,
        payload: { id: tag.id, name: tag.name, assetIds: byTag.get(tag.id) ?? [], createdAt: tag.created_at, updatedAt: tag.updated_at }
      }));
    }
    case 'saved_search': {
      const rows = await db.prepare('SELECT id, name, rules_json, sort_json, revision, created_at, updated_at FROM saved_searches ORDER BY id LIMIT ? OFFSET ?')
        .bind(limit, offset).all<{ id: string; name: string; rules_json: string; sort_json: string; revision: number; created_at: string; updated_at: string }>();
      return rows.results.map((savedSearch) => ({
        entityType: 'saved_search' as const,
        entityId: savedSearch.id,
        revision: savedSearch.revision,
        payload: { id: savedSearch.id, name: savedSearch.name, rules: JSON.parse(savedSearch.rules_json), sort: JSON.parse(savedSearch.sort_json), createdAt: savedSearch.created_at, updatedAt: savedSearch.updated_at }
      }));
    }
    case 'export_receipt': {
      const rows = await db.prepare('SELECT id, manifest_sha256, asset_ids_json, completed_at, revision FROM export_receipts ORDER BY id LIMIT ? OFFSET ?')
        .bind(limit, offset).all<{ id: string; manifest_sha256: string; asset_ids_json: string; completed_at: string; revision: number }>();
      return rows.results.map((receipt) => ({
        entityType: 'export_receipt' as const,
        entityId: receipt.id,
        revision: receipt.revision,
        payload: { id: receipt.id, manifestSHA256: receipt.manifest_sha256, assetIds: JSON.parse(receipt.asset_ids_json), completedAt: receipt.completed_at }
      }));
    }
    case 'backup_manifest': {
      const rows = await db.prepare('SELECT id, manifest_sha256, recorded_at, last_restore_drill_at, last_restore_drill_result, revision FROM backup_manifests ORDER BY id LIMIT ? OFFSET ?')
        .bind(limit, offset).all<{ id: string; manifest_sha256: string; recorded_at: string; last_restore_drill_at: string | null; last_restore_drill_result: string | null; revision: number }>();
      return rows.results.map((manifest) => ({
        entityType: 'backup_manifest' as const,
        entityId: manifest.id,
        revision: manifest.revision,
        payload: { id: manifest.id, manifestSHA256: manifest.manifest_sha256, recordedAt: manifest.recorded_at, lastRestoreDrillAt: manifest.last_restore_drill_at, lastRestoreDrillResult: manifest.last_restore_drill_result }
      }));
    }
  }
}

catalogRouter.get('/catalog/bootstrap', requireAuth('library.read'), async (c) => {
  const offset = parseBoundedInteger(c.req.query('cursor'), 0, MAX_CURSOR);
  const limit = parseBoundedInteger(c.req.query('limit'), 100, 500);
  if (offset === null || limit === null || limit === 0) {
    return apiError(c, 400, 'INVALID_CURSOR', 'cursor and limit must be bounded positive integers');
  }

  const [watermarkRow, ...counts] = await Promise.all([
    c.env.DB.prepare('SELECT COALESCE(MAX(revision), 0) AS revision FROM change_events').first<{ revision: number }>(),
    ...TYPES.map((type) => c.env.DB.prepare(`SELECT COUNT(*) AS n FROM ${TABLE[type]}`).first<{ n: number }>())
  ]);
  const sizes = counts.map((row) => row?.n ?? 0);
  const total = sizes.reduce((sum, n) => sum + n, 0);

  // Walk the concatenated list: read only the slice of each type that overlaps [offset, offset + limit).
  const entities: SnapshotEntity[] = [];
  let start = 0;
  for (const [index, type] of TYPES.entries()) {
    const size = sizes[index] ?? 0;
    const from = Math.max(offset, start);
    const to = Math.min(offset + limit, start + size);
    if (to > from) entities.push(...(await loadPage(c.env.DB, type, to - from, from - start)));
    start += size;
  }

  const nextOffset = offset + entities.length;
  return c.json({
    watermarkRevision: watermarkRow?.revision ?? 0,
    entities,
    nextCursor: nextOffset < total ? String(nextOffset) : null
  });
});
