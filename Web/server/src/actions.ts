import type { LibraryAction, LibraryActionResult, LibraryAsset } from "@framebase/web-contracts";
import type { CatalogIndex } from "./cloud/catalogIndex";
import type { CloudClient } from "./cloud/client";

/** The Worker accepts at most 25 operations per mutation request. */
const BATCH_SIZE = 25;
const TRASH_RETENTION_DAYS = 30;

export class ActionError extends Error {
  constructor(
    readonly status: 400 | 404 | 409,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

const chunk = <T>(items: T[], size: number) =>
  Array.from({ length: Math.ceil(items.length / size) }, (_, i) =>
    items.slice(i * size, (i + 1) * size),
  );

function require_(index: CatalogIndex, ids: string[], where: "live" | "trashed"): LibraryAsset[] {
  const found = ids.map((id) => index.get(id));
  const wrong = found.findIndex((a) => !a || (where === "live") === Boolean(a.trashedAt));
  if (wrong !== -1) {
    throw new ActionError(
      404,
      "not_found",
      where === "live"
        ? "An item no longer exists or is already in Trash. Refresh and try again."
        : "An item is not in Trash.",
    );
  }
  return found as LibraryAsset[];
}

type Mutated = Awaited<ReturnType<CloudClient["mutate"]>>;
type Ops = Parameters<CloudClient["mutate"]>[0];

/**
 * Applies one edit through the Worker's mutation API, then mirrors it in the local index.
 * Every request carries the target's current revision, so an edit made elsewhere in the meantime is rejected
 * (409) instead of silently overwritten, and the operation ID makes a retried request safe.
 */
export async function applyAction(
  cloud: CloudClient,
  index: CatalogIndex,
  action: LibraryAction,
): Promise<LibraryActionResult> {
  const send = (ops: Ops, key: string): Promise<Mutated> => cloud.mutate(ops, key);
  const revisions = (res: Mutated) => new Map(res.results.map((r) => [r.targetId, r.revision]));
  const missing = (what: string) =>
    new ActionError(404, "not_found", `That ${what} no longer exists.`);

  /** One batch of per-asset operations (the same operation for every asset), split to the Worker's limit. */
  async function perAsset(
    assets: LibraryAsset[],
    make: (a: LibraryAsset) => { type: string; payload: Record<string, unknown> },
  ): Promise<Map<string, number>> {
    const out = new Map<string, number>();
    for (const [n, group] of chunk(assets, BATCH_SIZE).entries()) {
      const res = await send(
        group.map((a) => ({ ...make(a), targetId: a.id, baseRevision: a.revision })),
        `${action.operationId}-${n}`,
      );
      const rev = revisions(res);
      for (const a of group) out.set(a.id, rev.get(a.id) ?? a.revision + 1);
    }
    return out;
  }

  switch (action.action) {
    case "rename": {
      const [asset] = require_(index, [action.assetId], "live") as [LibraryAsset];
      const rev = await perAsset([asset], () => ({
        type: "rename_asset",
        payload: { displayName: action.displayName },
      }));
      return {
        status: "applied",
        assets: index.patchAssets([
          {
            id: asset.id,
            patch: { displayName: action.displayName.trim(), revision: rev.get(asset.id)! },
          },
        ]),
      };
    }

    case "favorite":
    case "rating": {
      const assets = require_(index, action.assetIds, "live");
      const favorite = action.action === "favorite";
      const rev = await perAsset(assets, () =>
        favorite
          ? { type: "update_favorite", payload: { favorite: action.favorite } }
          : { type: "update_rating", payload: { rating: action.rating } },
      );
      return {
        status: "applied",
        assets: index.patchAssets(
          assets.map((a) => ({
            id: a.id,
            patch: {
              ...(favorite ? { favorite: action.favorite } : { rating: action.rating }),
              revision: rev.get(a.id)!,
            },
          })),
        ),
      };
    }

    case "move": {
      if (!index.hasFolder(action.folderId)) {
        throw new ActionError(400, "invalid_folder", "The destination folder does not exist.");
      }
      const assets = require_(index, action.assetIds, "live");
      const rev = await perAsset(assets, () => ({
        type: "move_asset",
        payload: { folderId: action.folderId },
      }));
      return {
        status: "applied",
        assets: index.patchAssets(
          assets.map((a) => ({
            id: a.id,
            patch: { folderId: action.folderId, revision: rev.get(a.id)! },
          })),
        ),
      };
    }

    case "trash":
    case "restore": {
      const trashing = action.action === "trash";
      const assets = require_(index, action.assetIds, trashing ? "live" : "trashed");
      const rev = await perAsset(assets, () =>
        trashing
          ? { type: "trash_asset", payload: { retentionDays: TRASH_RETENTION_DAYS } }
          : { type: "restore_asset", payload: {} },
      );
      const done = assets.map((a) => ({ id: a.id, revision: rev.get(a.id)! }));
      const updated = trashing ? index.trash(done, new Date().toISOString()) : index.restore(done);
      return { status: "applied", assets: updated };
    }

    case "tag": {
      const tag = index.tag(action.tagId);
      if (!tag || tag.revision === undefined) throw missing("tag");
      require_(index, action.assetIds, "live");
      const res = await send(
        [
          {
            type: action.mode === "add" ? "add_tag_to_assets" : "remove_tag_from_assets",
            targetId: tag.id,
            baseRevision: tag.revision,
            payload: { assetIds: [...new Set(action.assetIds)] },
          },
        ],
        action.operationId,
      );
      const revision = revisions(res).get(tag.id) ?? tag.revision + 1;
      return {
        status: "applied",
        assets: index.setTagMembership(tag.id, action.assetIds, action.mode, revision),
      };
    }

    case "createTag": {
      const id = `tag-${action.operationId}`;
      await send(
        [{ type: "create_tag", targetId: id, payload: { name: action.name } }],
        action.operationId,
      );
      index.addTag({ id, name: action.name, revision: 1 });
      return {
        status: "applied",
        assets: [],
        tag: { id, name: action.name, assetCount: 0, revision: 1 },
      };
    }

    // ---- albums: an album is a collection; removing from it or deleting it never deletes a photo ----
    case "createAlbum": {
      const id = `album-${action.operationId}`;
      await send(
        [{ type: "create_album", targetId: id, payload: { name: action.name } }],
        action.operationId,
      );
      index.addAlbum({ id, name: action.name, revision: 1 });
      return {
        status: "applied",
        assets: [],
        album: { id, name: action.name, assetCount: 0, revision: 1 },
      };
    }

    case "renameAlbum": {
      const album = index.album(action.albumId);
      if (!album || album.revision === undefined) throw missing("album");
      const res = await send(
        [
          {
            type: "rename_album",
            targetId: album.id,
            baseRevision: album.revision,
            payload: { name: action.name },
          },
        ],
        action.operationId,
      );
      index.patchAlbum(album.id, {
        name: action.name,
        revision: revisions(res).get(album.id) ?? album.revision + 1,
      });
      return { status: "applied", assets: [] };
    }

    case "deleteAlbum": {
      const album = index.album(action.albumId);
      if (!album || album.revision === undefined) throw missing("album");
      await send(
        [{ type: "delete_album", targetId: album.id, baseRevision: album.revision, payload: {} }],
        action.operationId,
      );
      index.deleteAlbum(album.id);
      return { status: "applied", assets: [] };
    }

    case "albumAdd":
    case "albumRemove": {
      const album = index.album(action.albumId);
      if (!album || album.revision === undefined) throw missing("album");
      const assets = require_(index, action.assetIds, "live");
      const adding = action.action === "albumAdd";
      const res = await send(
        [
          {
            type: adding ? "add_assets_to_album" : "remove_assets_from_album",
            targetId: album.id,
            baseRevision: album.revision,
            payload: { assetIds: [...new Set(action.assetIds)] },
          },
        ],
        action.operationId,
      );
      index.setAlbumMembership(
        album.id,
        action.assetIds,
        adding ? "add" : "remove",
        revisions(res).get(album.id) ?? album.revision + 1,
      );
      return { status: "applied", assets };
    }

    // ---- folders: catalog relationships only; nothing is created or moved on any disk ----
    case "createFolder": {
      if (action.parentId && !index.hasFolder(action.parentId)) throw missing("parent folder");
      const id = `folder-${action.operationId}`;
      await send(
        [
          {
            type: "create_folder",
            targetId: id,
            payload: { name: action.name, parentId: action.parentId },
          },
        ],
        action.operationId,
      );
      index.addFolder({ id, name: action.name, parentId: action.parentId, revision: 1 });
      return {
        status: "applied",
        assets: [],
        folder: {
          id,
          name: action.name,
          parentId: action.parentId,
          systemKind: null,
          sortOrder: 0,
          assetCount: 0,
        },
      };
    }

    case "renameFolder": {
      const folder = index.folder(action.folderId);
      if (!folder) throw missing("folder");
      const res = await send(
        [
          {
            type: "rename_folder",
            targetId: folder.id,
            baseRevision: folder.revision,
            payload: { name: action.name },
          },
        ],
        action.operationId,
      );
      index.patchFolder(folder.id, {
        name: action.name,
        revision: revisions(res).get(folder.id) ?? folder.revision + 1,
      });
      return { status: "applied", assets: [] };
    }

    case "moveFolder": {
      const folder = index.folder(action.folderId);
      if (!folder) throw missing("folder");
      if (action.parentId && !index.hasFolder(action.parentId)) throw missing("destination folder");
      if (action.parentId && index.isWithinFolder(folder.id, action.parentId)) {
        throw new ActionError(
          400,
          "invalid_folder",
          "A folder cannot be moved into itself or one of its own subfolders.",
        );
      }
      const res = await send(
        [
          {
            type: "move_folder",
            targetId: folder.id,
            baseRevision: folder.revision,
            payload: { parentId: action.parentId },
          },
        ],
        action.operationId,
      );
      index.patchFolder(folder.id, {
        parentId: action.parentId,
        revision: revisions(res).get(folder.id) ?? folder.revision + 1,
      });
      return { status: "applied", assets: [] };
    }
  }
}
