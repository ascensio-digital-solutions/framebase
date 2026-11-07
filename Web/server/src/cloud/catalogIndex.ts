import { z } from "zod";
import type {
  LibraryAsset,
  LibraryAssetPage,
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
const assetPayload = z.object({
  id: z.string(),
  displayName: z.string(),
  folderId: z.string(),
  favorite: z.boolean(),
  rating: z.number(),
  blob: z.object({ byteSize: z.number(), mediaType: z.string() }),
  createdAt: z.string(),
  trash: z.unknown().nullable().optional(),
});
const membershipPayload = z.object({
  id: z.string(),
  name: z.string(),
  assetIds: z.array(z.string()),
});

const MAX_TAGS_RETURNED = 300;
export const DEFAULT_PAGE_SIZE = 100;
export const MAX_PAGE_SIZE = 300;

export interface AssetFilter {
  folderId?: string;
  albumId?: string;
  tagId?: string;
  q?: string;
  cursor?: number;
  limit?: number;
}

type Folder = z.infer<typeof folderPayload>;
type Membership = z.infer<typeof membershipPayload>;

const byName = (a: { name: string; id: string }, b: { name: string; id: string }) =>
  a.name.localeCompare(b.name) || a.id.localeCompare(b.id);

/** An in-memory, read-only index of one catalog snapshot. Trashed assets are excluded everywhere. */
export class CatalogIndex {
  readonly #assets = new Map<string, LibraryAsset>();
  readonly #sortedIds: string[];
  readonly #folders: Folder[] = [];
  readonly #albums: Membership[] = [];
  readonly #tags: Membership[] = [];
  readonly #childrenByFolder = new Map<string, string[]>();
  readonly #directCounts = new Map<string, number>();
  skipped = 0;

  constructor(
    entities: BootstrapEntity[],
    readonly watermarkRevision: number,
    readonly fetchedAt: string,
  ) {
    const rawAssets: z.infer<typeof assetPayload>[] = [];
    for (const entity of entities) {
      switch (entity.entityType) {
        case "folder": {
          const p = folderPayload.safeParse(entity.payload);
          if (p.success) this.#folders.push(p.data);
          else this.skipped++;
          break;
        }
        case "asset": {
          const p = assetPayload.safeParse(entity.payload);
          if (p.success) rawAssets.push(p.data);
          else this.skipped++;
          break;
        }
        case "album":
        case "tag": {
          const p = membershipPayload.safeParse(entity.payload);
          if (!p.success) this.skipped++;
          else (entity.entityType === "album" ? this.#albums : this.#tags).push(p.data);
          break;
        }
        default:
          break; // saved searches, receipts and backup manifests are not browsed here
      }
    }

    const live = rawAssets.filter((a) => !a.trash);
    const tagNames = new Map<string, string[]>();
    for (const tag of this.#tags) {
      for (const assetId of tag.assetIds) {
        const names = tagNames.get(assetId) ?? [];
        names.push(tag.name);
        tagNames.set(assetId, names);
      }
    }
    for (const a of live) {
      this.#assets.set(a.id, {
        id: a.id,
        displayName: a.displayName,
        folderId: a.folderId,
        favorite: a.favorite,
        rating: Math.trunc(a.rating),
        mediaType: a.blob.mediaType,
        byteSize: Math.max(0, Math.trunc(a.blob.byteSize)),
        createdAt: a.createdAt,
        tags: (tagNames.get(a.id) ?? []).sort(),
      });
      this.#directCounts.set(a.folderId, (this.#directCounts.get(a.folderId) ?? 0) + 1);
    }
    this.#sortedIds = [...this.#assets.values()]
      .sort(
        (x, y) =>
          x.displayName.toLowerCase().localeCompare(y.displayName.toLowerCase()) ||
          x.id.localeCompare(y.id),
      )
      .map((a) => a.id);

    for (const folder of this.#folders) {
      if (folder.parentId) {
        const kids = this.#childrenByFolder.get(folder.parentId) ?? [];
        kids.push(folder.id);
        this.#childrenByFolder.set(folder.parentId, kids);
      }
    }
  }

  get(id: string): LibraryAsset | undefined {
    return this.#assets.get(id);
  }

  summary(): LibrarySummary {
    return {
      assetCount: this.#assets.size,
      folderCount: this.#folders.length,
      albumCount: this.#albums.length,
      tagCount: this.#tags.length,
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
    const liveCount = (m: Membership) => m.assetIds.filter((id) => this.#assets.has(id)).length;
    const tags = this.#tags
      .map((t) => ({ id: t.id, name: t.name, assetCount: liveCount(t) }))
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
        .map((a) => ({ id: a.id, name: a.name, assetCount: liveCount(a) }))
        .sort(byName),
      tags: tags.slice(0, MAX_TAGS_RETURNED),
      tagsTotal: tags.length,
    };
  }

  query(filter: AssetFilter): LibraryAssetPage {
    let ids = this.#sortedIds;
    if (filter.folderId) {
      const folders = this.#subtree(filter.folderId);
      ids = ids.filter((id) => folders.has((this.#assets.get(id) as LibraryAsset).folderId));
    }
    const member = (list: Membership[], id: string) =>
      new Set(list.find((m) => m.id === id)?.assetIds ?? []);
    if (filter.albumId) {
      const inAlbum = member(this.#albums, filter.albumId);
      ids = ids.filter((id) => inAlbum.has(id));
    }
    if (filter.tagId) {
      const tagged = member(this.#tags, filter.tagId);
      ids = ids.filter((id) => tagged.has(id));
    }
    const q = filter.q?.trim().toLowerCase();
    if (q) {
      ids = ids.filter((id) =>
        (this.#assets.get(id) as LibraryAsset).displayName.toLowerCase().includes(q),
      );
    }
    const offset = Math.max(0, filter.cursor ?? 0);
    const limit = Math.min(MAX_PAGE_SIZE, Math.max(1, filter.limit ?? DEFAULT_PAGE_SIZE));
    const page = ids
      .slice(offset, offset + limit)
      .map((id) => this.#assets.get(id) as LibraryAsset);
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
}
