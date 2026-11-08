import { z } from "zod";
import type {
  LibraryAsset,
  LibraryAssetPage,
  LibraryNamedCount,
  LibraryStructure,
  LibrarySummary,
} from "@framebase/web-contracts";
import type { BootstrapEntity } from "./client";

// Only the fields the web studio reads. Unknown fields are ignored; malformed entities are skipped.
const folderPayload = z.object({
  id: z.string(),
  name: z.string(),
  parentId: z.string().nullable(),
  systemKind: z.string().nullable().optional(),
  sortOrder: z.number(),
});
const trashPayload = z.object({
  priorFolderId: z.string(),
  trashedAt: z.string(),
  scheduledPurgeAt: z.string(),
});
const assetPayload = z.object({
  id: z.string(),
  displayName: z.string(),
  folderId: z.string(),
  favorite: z.boolean(),
  rating: z.number(),
  blob: z.object({ byteSize: z.number(), mediaType: z.string() }),
  createdAt: z.string(),
  trash: trashPayload.nullable().optional(),
});
const membershipPayload = z.object({
  id: z.string(),
  name: z.string(),
  assetIds: z.array(z.string()),
});

const MAX_TAGS_RETURNED = 300;
export const DEFAULT_PAGE_SIZE = 100;
export const MAX_PAGE_SIZE = 300;
/** Where the Worker puts a restored asset whose previous folder no longer exists. */
const INBOX_FOLDER = "system-inbox";

export interface AssetFilter {
  folderId?: string;
  albumId?: string;
  tagId?: string;
  q?: string;
  /** List items in Trash instead of the live library. */
  trashed?: boolean;
  cursor?: number;
  limit?: number;
}

type Folder = z.infer<typeof folderPayload> & { revision: number };
type Member = z.infer<typeof membershipPayload> & { revision: number };
type AssetPatch = Partial<
  Pick<LibraryAsset, "displayName" | "favorite" | "rating" | "folderId" | "revision">
>;

const sortedTags = (tags: { id: string; name: string }[] = []) =>
  [...tags].sort((a, b) => a.name.localeCompare(b.name));

const byName = (a: { name: string; id: string }, b: { name: string; id: string }) =>
  a.name.localeCompare(b.name) || a.id.localeCompare(b.id);

/**
 * An in-memory index of one catalog snapshot, with helpers to apply edits locally after the Worker has
 * accepted them (so the UI updates immediately; a later refresh brings the snapshot back to the truth).
 */
export class CatalogIndex {
  readonly #assets = new Map<string, LibraryAsset>(); // live library
  readonly #trashed = new Map<string, LibraryAsset>(); // items in Trash
  readonly #priorFolder = new Map<string, string>();
  #sortedIds: string[] = [];
  #sortedTrashedIds: string[] = [];
  readonly #folders: Folder[] = [];
  readonly #albums: Member[] = [];
  readonly #tags: Member[] = [];
  readonly #childrenByFolder = new Map<string, string[]>();
  #directCounts = new Map<string, number>();
  skipped = 0;

  constructor(
    entities: BootstrapEntity[],
    readonly watermarkRevision: number,
    readonly fetchedAt: string,
  ) {
    const rawAssets: { data: z.infer<typeof assetPayload>; revision: number }[] = [];
    for (const entity of entities) {
      switch (entity.entityType) {
        case "folder": {
          const p = folderPayload.safeParse(entity.payload);
          if (p.success) this.#folders.push({ ...p.data, revision: entity.revision });
          else this.skipped++;
          break;
        }
        case "asset": {
          const p = assetPayload.safeParse(entity.payload);
          if (p.success) rawAssets.push({ data: p.data, revision: entity.revision });
          else this.skipped++;
          break;
        }
        case "album":
        case "tag": {
          const p = membershipPayload.safeParse(entity.payload);
          if (!p.success) this.skipped++;
          else
            (entity.entityType === "album" ? this.#albums : this.#tags).push({
              ...p.data,
              revision: entity.revision,
            });
          break;
        }
        default:
          break; // saved searches, receipts and backup manifests are not browsed here
      }
    }

    const tagsByAsset = new Map<string, { id: string; name: string }[]>();
    for (const tag of this.#tags) {
      for (const assetId of tag.assetIds) {
        const list = tagsByAsset.get(assetId) ?? [];
        list.push({ id: tag.id, name: tag.name });
        tagsByAsset.set(assetId, list);
      }
    }
    for (const { data: a, revision } of rawAssets) {
      const dto: LibraryAsset = {
        id: a.id,
        displayName: a.displayName,
        folderId: a.folderId,
        favorite: a.favorite,
        rating: Math.trunc(a.rating),
        mediaType: a.blob.mediaType,
        byteSize: Math.max(0, Math.trunc(a.blob.byteSize)),
        createdAt: a.createdAt,
        tags: sortedTags(tagsByAsset.get(a.id)).map((t) => t.name),
        tagIds: sortedTags(tagsByAsset.get(a.id)).map((t) => t.id),
        revision,
      };
      if (a.trash) {
        this.#trashed.set(a.id, {
          ...dto,
          trashedAt: a.trash.trashedAt,
          scheduledPurgeAt: a.trash.scheduledPurgeAt,
        });
        this.#priorFolder.set(a.id, a.trash.priorFolderId);
      } else {
        this.#assets.set(a.id, dto);
      }
    }
    this.#rebuildChildren();
    this.#reindex();
  }

  #rebuildChildren() {
    this.#childrenByFolder.clear();
    for (const folder of this.#folders) {
      if (folder.parentId) {
        const kids = this.#childrenByFolder.get(folder.parentId) ?? [];
        kids.push(folder.id);
        this.#childrenByFolder.set(folder.parentId, kids);
      }
    }
  }

  /** Recomputes the sort orders and per-folder counts after any change to the asset maps. */
  #reindex() {
    this.#sortedIds = [...this.#assets.values()]
      .sort(
        (x, y) =>
          x.displayName.toLowerCase().localeCompare(y.displayName.toLowerCase()) ||
          x.id.localeCompare(y.id),
      )
      .map((a) => a.id);
    this.#sortedTrashedIds = [...this.#trashed.values()]
      .sort(
        (x, y) => (y.trashedAt ?? "").localeCompare(x.trashedAt ?? "") || x.id.localeCompare(y.id),
      )
      .map((a) => a.id);
    this.#directCounts = new Map();
    for (const a of this.#assets.values()) {
      this.#directCounts.set(a.folderId, (this.#directCounts.get(a.folderId) ?? 0) + 1);
    }
  }

  get(id: string): LibraryAsset | undefined {
    return this.#assets.get(id) ?? this.#trashed.get(id);
  }

  hasFolder(id: string): boolean {
    return this.#folders.some((f) => f.id === id);
  }

  tag(id: string): LibraryNamedCount | undefined {
    const t = this.#tags.find((x) => x.id === id);
    return t && { id: t.id, name: t.name, assetCount: this.#liveCount(t), revision: t.revision };
  }

  #liveCount(m: Member) {
    return m.assetIds.filter((id) => this.#assets.has(id)).length;
  }

  // --- local edits, applied after the Worker accepted them -------------------------------------

  patchAssets(changes: { id: string; patch: AssetPatch }[]): LibraryAsset[] {
    const out: LibraryAsset[] = [];
    for (const { id, patch } of changes) {
      const current = this.#assets.get(id);
      if (!current) continue;
      const next = { ...current, ...patch };
      this.#assets.set(id, next);
      out.push(next);
    }
    this.#reindex();
    return out;
  }

  trash(items: { id: string; revision: number }[], trashedAt: string): LibraryAsset[] {
    const scheduledPurgeAt = new Date(Date.parse(trashedAt) + 30 * 86_400_000).toISOString();
    const out: LibraryAsset[] = [];
    for (const { id, revision } of items) {
      const current = this.#assets.get(id);
      if (!current) continue;
      this.#priorFolder.set(id, current.folderId);
      const moved = { ...current, revision, trashedAt, scheduledPurgeAt, tags: [], tagIds: [] };
      this.#assets.delete(id);
      this.#trashed.set(id, moved);
      out.push(moved);
      // The Worker drops tag and album memberships on trash and restores them on restore.
      for (const m of [...this.#tags, ...this.#albums])
        m.assetIds = m.assetIds.filter((x) => x !== id);
    }
    this.#reindex();
    return out;
  }

  restore(items: { id: string; revision: number }[]): LibraryAsset[] {
    const out: LibraryAsset[] = [];
    for (const { id, revision } of items) {
      const current = this.#trashed.get(id);
      if (!current) continue;
      const prior = this.#priorFolder.get(id);
      const folderId = prior && this.hasFolder(prior) ? prior : INBOX_FOLDER;
      const { trashedAt: _t, scheduledPurgeAt: _s, ...rest } = current;
      void _t;
      void _s;
      const live: LibraryAsset = { ...rest, folderId, revision };
      this.#trashed.delete(id);
      this.#priorFolder.delete(id);
      this.#assets.set(id, live);
      out.push(live);
    }
    this.#reindex();
    return out;
  }

  addTag(tag: { id: string; name: string; revision: number }) {
    this.#tags.push({ id: tag.id, name: tag.name, assetIds: [], revision: tag.revision });
  }

  setTagMembership(tagId: string, assetIds: string[], mode: "add" | "remove", revision: number) {
    const tag = this.#tags.find((t) => t.id === tagId);
    if (!tag) return [];
    const ids = new Set(assetIds);
    tag.revision = revision;
    tag.assetIds =
      mode === "add"
        ? [...new Set([...tag.assetIds, ...assetIds])]
        : tag.assetIds.filter((id) => !ids.has(id));
    const out: LibraryAsset[] = [];
    for (const id of assetIds) {
      const a = this.#assets.get(id);
      if (!a) continue;
      const kept = a.tags
        .map((name, i) => ({ id: a.tagIds[i] as string, name }))
        .filter((t) => t.id !== tag.id);
      const all = mode === "add" ? [...kept, { id: tag.id, name: tag.name }] : kept;
      const next = {
        ...a,
        tags: sortedTags(all).map((t) => t.name),
        tagIds: sortedTags(all).map((t) => t.id),
      };
      this.#assets.set(id, next);
      out.push(next);
    }
    return out;
  }

  // --- folders and albums ----------------------------------------------------------------------

  folder(id: string) {
    const f = this.#folders.find((x) => x.id === id);
    return f && { id: f.id, name: f.name, parentId: f.parentId, revision: f.revision };
  }

  /** True when `candidateId` is `folderId` itself or sits beneath it (so moving `folderId` there would be a cycle). */
  isWithinFolder(folderId: string, candidateId: string): boolean {
    return this.#subtree(folderId).has(candidateId);
  }

  addFolder(f: { id: string; name: string; parentId: string | null; revision: number }) {
    this.#folders.push({ ...f, systemKind: null, sortOrder: 0 });
    this.#rebuildChildren();
    this.#reindex();
  }

  patchFolder(id: string, patch: { name?: string; parentId?: string | null; revision: number }) {
    const f = this.#folders.find((x) => x.id === id);
    if (!f) return;
    if (patch.name !== undefined) f.name = patch.name;
    if (patch.parentId !== undefined) f.parentId = patch.parentId;
    f.revision = patch.revision;
    this.#rebuildChildren();
    this.#reindex();
  }

  album(id: string) {
    const a = this.#albums.find((x) => x.id === id);
    return a && { id: a.id, name: a.name, assetCount: this.#liveCount(a), revision: a.revision };
  }

  addAlbum(a: { id: string; name: string; revision: number }) {
    this.#albums.push({ id: a.id, name: a.name, assetIds: [], revision: a.revision });
  }

  patchAlbum(id: string, patch: { name?: string; revision: number }) {
    const a = this.#albums.find((x) => x.id === id);
    if (!a) return;
    if (patch.name !== undefined) a.name = patch.name;
    a.revision = patch.revision;
  }

  deleteAlbum(id: string) {
    const i = this.#albums.findIndex((x) => x.id === id);
    if (i !== -1) this.#albums.splice(i, 1);
  }

  setAlbumMembership(
    albumId: string,
    assetIds: string[],
    mode: "add" | "remove",
    revision: number,
  ) {
    const album = this.#albums.find((x) => x.id === albumId);
    if (!album) return;
    const ids = new Set(assetIds);
    album.revision = revision;
    album.assetIds =
      mode === "add"
        ? [...new Set([...album.assetIds, ...assetIds])]
        : album.assetIds.filter((id) => !ids.has(id));
  }

  // --- views -----------------------------------------------------------------------------------

  summary(): LibrarySummary {
    return {
      assetCount: this.#assets.size,
      folderCount: this.#folders.length,
      albumCount: this.#albums.length,
      tagCount: this.#tags.length,
      trashedCount: this.#trashed.size,
      watermarkRevision: this.watermarkRevision,
      fetchedAt: this.fetchedAt,
    };
  }

  /** A folder and every folder beneath it. Guards against cycles in malformed data. */
  #subtree(folderId: string): Set<string> {
    const seen = new Set<string>();
    const stack = [folderId];
    while (stack.length) {
      const id = stack.pop() as string;
      if (seen.has(id)) continue;
      seen.add(id);
      stack.push(...(this.#childrenByFolder.get(id) ?? []));
    }
    return seen;
  }

  structure(): LibraryStructure {
    const totals = new Map<string, number>();
    const total = (id: string): number => {
      const cached = totals.get(id);
      if (cached !== undefined) return cached;
      let sum = 0;
      for (const folderId of this.#subtree(id)) sum += this.#directCounts.get(folderId) ?? 0;
      totals.set(id, sum);
      return sum;
    };
    const tags = this.#tags
      .map((t) => ({
        id: t.id,
        name: t.name,
        assetCount: this.#liveCount(t),
        revision: t.revision,
      }))
      .sort((a, b) => b.assetCount - a.assetCount || byName(a, b));
    return {
      folders: [...this.#folders]
        .sort((a, b) => a.sortOrder - b.sortOrder || byName(a, b))
        .map((f) => ({
          id: f.id,
          name: f.name,
          parentId: f.parentId,
          systemKind: f.systemKind ?? null,
          sortOrder: f.sortOrder,
          assetCount: total(f.id),
        })),
      albums: this.#albums
        .map((a) => ({
          id: a.id,
          name: a.name,
          assetCount: this.#liveCount(a),
          revision: a.revision,
        }))
        .sort(byName),
      tags: tags.slice(0, MAX_TAGS_RETURNED),
      tagsTotal: tags.length,
    };
  }

  query(filter: AssetFilter): LibraryAssetPage {
    const source = filter.trashed ? this.#trashed : this.#assets;
    let ids = filter.trashed ? this.#sortedTrashedIds : this.#sortedIds;
    if (!filter.trashed) {
      if (filter.folderId) {
        const folders = this.#subtree(filter.folderId);
        ids = ids.filter((id) => folders.has((source.get(id) as LibraryAsset).folderId));
      }
      const member = (list: Member[], id: string) =>
        new Set(list.find((m) => m.id === id)?.assetIds ?? []);
      if (filter.albumId) {
        const inAlbum = member(this.#albums, filter.albumId);
        ids = ids.filter((id) => inAlbum.has(id));
      }
      if (filter.tagId) {
        const tagged = member(this.#tags, filter.tagId);
        ids = ids.filter((id) => tagged.has(id));
      }
    }
    const q = filter.q?.trim().toLowerCase();
    if (q) {
      ids = ids.filter((id) =>
        (source.get(id) as LibraryAsset).displayName.toLowerCase().includes(q),
      );
    }
    const offset = Math.max(0, filter.cursor ?? 0);
    const limit = Math.min(MAX_PAGE_SIZE, Math.max(1, filter.limit ?? DEFAULT_PAGE_SIZE));
    const page = ids.slice(offset, offset + limit).map((id) => source.get(id) as LibraryAsset);
    const next = offset + page.length;
    return { assets: page, total: ids.length, nextCursor: next < ids.length ? String(next) : null };
  }
}

export interface CatalogStoreOptions {
  load: () => Promise<{ entities: BootstrapEntity[]; watermarkRevision: number }>;
  now?: () => number;
  /** Snapshot lifetime. A bootstrap reads every table once per page, so this is deliberately long. */
  ttlMs?: number;
  /** Minimum gap between forced refreshes. */
  minRefreshIntervalMs?: number;
}

/** Caches one snapshot, shares in-flight loads, and serves a stale snapshot if a refresh fails. */
export class CatalogStore {
  #index?: CatalogIndex;
  #loadedAt = 0;
  #inflight?: Promise<CatalogIndex>;
  readonly #now: () => number;
  readonly #ttl: number;
  readonly #minRefresh: number;

  constructor(private readonly opts: CatalogStoreOptions) {
    this.#now = opts.now ?? Date.now;
    this.#ttl = opts.ttlMs ?? 15 * 60_000;
    this.#minRefresh = opts.minRefreshIntervalMs ?? 30_000;
  }

  #load(): Promise<CatalogIndex> {
    this.#inflight ??= this.opts
      .load()
      .then(({ entities, watermarkRevision }) => {
        this.#index = new CatalogIndex(
          entities,
          watermarkRevision,
          new Date(this.#now()).toISOString(),
        );
        this.#loadedAt = this.#now();
        return this.#index;
      })
      .finally(() => {
        this.#inflight = undefined;
      });
    return this.#inflight;
  }

  async get(): Promise<CatalogIndex> {
    if (this.#index && this.#now() - this.#loadedAt < this.#ttl) return this.#index;
    try {
      return await this.#load();
    } catch (error) {
      if (this.#index) return this.#index; // stale beats unavailable
      throw error;
    }
  }

  /** Forces a reload unless one happened very recently. Returns the resulting snapshot. */
  async refresh(): Promise<CatalogIndex> {
    if (this.#index && this.#now() - this.#loadedAt < this.#minRefresh) return this.#index;
    return this.#load();
  }

  /** Reloads in the background after an edit so the snapshot converges on the Worker's state. */
  refreshSoon(delayMs = 5_000): void {
    setTimeout(() => {
      this.#loadedAt = 0; // bypass the minimum interval: an edit just happened
      this.#load().catch(() => undefined);
    }, delayMs).unref?.();
  }
}
