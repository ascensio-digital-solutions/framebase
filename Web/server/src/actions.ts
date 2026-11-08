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

/**
 * Applies one edit through the Worker's mutation API, then mirrors it in the local index.
 * Every request carries the asset's current revision, so an edit made elsewhere in the meantime is rejected
 * (409) instead of silently overwritten, and the operation ID makes a retried request safe.
 */
export async function applyAction(
  cloud: CloudClient,
  index: CatalogIndex,
  action: LibraryAction,
): Promise<LibraryActionResult> {
  const send = (ops: Parameters<CloudClient["mutate"]>[0], key: string) => cloud.mutate(ops, key);
  const revisions = (res: Awaited<ReturnType<CloudClient["mutate"]>>) =>
    new Map(res.results.map((r) => [r.targetId, r.revision]));

  switch (action.action) {
    case "rename":
    case "favorite":
    case "rating": {
      const [asset] = require_(index, [action.assetId], "live") as [LibraryAsset];
      const op =
        action.action === "rename"
          ? { type: "rename_asset", payload: { displayName: action.displayName } }
          : action.action === "favorite"
            ? { type: "update_favorite", payload: { favorite: action.favorite } }
            : { type: "update_rating", payload: { rating: action.rating } };
      const res = await send(
        [{ ...op, targetId: asset.id, baseRevision: asset.revision }],
        action.operationId,
      );
      const revision = revisions(res).get(asset.id) ?? asset.revision + 1;
      const patch =
        action.action === "rename"
          ? { displayName: action.displayName.trim() }
          : action.action === "favorite"
            ? { favorite: action.favorite }
            : { rating: action.rating };
      return {
        status: "applied",
        assets: index.patchAssets([{ id: asset.id, patch: { ...patch, revision } }]),
      };
    }

    case "move": {
      if (!index.hasFolder(action.folderId)) {
        throw new ActionError(400, "invalid_folder", "The destination folder does not exist.");
      }
      const assets = require_(index, action.assetIds, "live");
      const changes: { id: string; patch: { folderId: string; revision: number } }[] = [];
      for (const [n, group] of chunk(assets, BATCH_SIZE).entries()) {
        const res = await send(
          group.map((a) => ({
            type: "move_asset",
            targetId: a.id,
            baseRevision: a.revision,
            payload: { folderId: action.folderId },
          })),
          `${action.operationId}-${n}`,
        );
        const rev = revisions(res);
        for (const a of group) {
          changes.push({
            id: a.id,
            patch: { folderId: action.folderId, revision: rev.get(a.id) ?? a.revision + 1 },
          });
        }
      }
      return { status: "applied", assets: index.patchAssets(changes) };
    }

    case "trash":
    case "restore": {
      const trashing = action.action === "trash";
      const assets = require_(index, action.assetIds, trashing ? "live" : "trashed");
      const done: { id: string; revision: number }[] = [];
      for (const [n, group] of chunk(assets, BATCH_SIZE).entries()) {
        const res = await send(
          group.map((a) => ({
            type: trashing ? "trash_asset" : "restore_asset",
            targetId: a.id,
            baseRevision: a.revision,
            payload: trashing ? { retentionDays: TRASH_RETENTION_DAYS } : {},
          })),
          `${action.operationId}-${n}`,
        );
        const rev = revisions(res);
        for (const a of group) done.push({ id: a.id, revision: rev.get(a.id) ?? a.revision + 1 });
      }
      const updated = trashing ? index.trash(done, new Date().toISOString()) : index.restore(done);
      return { status: "applied", assets: updated };
    }

    case "tag": {
      const tag = index.tag(action.tagId);
      if (!tag || tag.revision === undefined)
        throw new ActionError(404, "not_found", "That tag no longer exists.");
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
  }
}
