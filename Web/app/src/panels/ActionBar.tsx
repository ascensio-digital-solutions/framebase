import { useMemo, useState } from "react";
import { useLibrary } from "../library/LibraryContext";
import { AlbumDialog, ConfirmTrashDialog, MoveDialog, RateDialog, TagDialog } from "./Dialogs";

type Dialog = "trash" | "move" | "tag" | "rate" | "album" | null;

/** Applies a tag by name, creating it first when it does not exist yet. */
export function useTagAction() {
  const { structure, act } = useLibrary();
  return async (assetIds: string[], name: string, mode: "add" | "remove") => {
    let tagId = structure?.tags.find((t) => t.name === name)?.id;
    if (!tagId) {
      if (mode === "remove") return undefined;
      const created = await act({ action: "createTag", name });
      tagId = created?.tag?.id;
      if (!tagId) return undefined;
    }
    return act(
      { action: "tag", assetIds, tagId, mode },
      {
        label: `${mode === "add" ? "Tagged" : "Removed tag from"} ${assetIds.length} item${assetIds.length === 1 ? "" : "s"}`,
      },
    );
  };
}

/** Bulk actions on the checked items (or the open item). Editing is hidden unless the server allows it. */
export function ActionBar() {
  const { canEdit, filter, assets, checked, selected, act, editing, clearChecked, checkAllLoaded } =
    useLibrary();
  const [dialog, setDialog] = useState<Dialog>(null);
  const tag = useTagAction();
  const inTrash = Boolean(filter.trashed);

  const targets = useMemo(
    () => (checked.size > 0 ? assets.filter((a) => checked.has(a.id)) : selected ? [selected] : []),
    [assets, checked, selected],
  );
  if (!canEdit) return null;

  const ids = targets.map((a) => a.id);
  const none = editing || ids.length === 0;
  const close = () => setDialog(null);
  const plural = (n: number) => `${n} item${n === 1 ? "" : "s"}`;
  const allFavorite = targets.length > 0 && targets.every((a) => a.favorite);

  const addToAlbum = async (target: { albumId: string } | { newName: string }) => {
    let albumId = "albumId" in target ? target.albumId : undefined;
    if (!albumId) {
      const created = await act({
        action: "createAlbum",
        name: (target as { newName: string }).newName,
      });
      albumId = created?.album?.id;
      if (!albumId) return;
    }
    await act(
      { action: "albumAdd", albumId, assetIds: ids },
      {
        label: `Added ${plural(ids.length)} to the album`,
        undo: { action: "albumRemove", albumId, assetIds: ids },
      },
    );
  };

  return (
    <div className="action-bar" role="toolbar" aria-label="Edit selection">
      {checked.size > 0 ? (
        <>
          <strong>{checked.size} selected</strong>
          <button type="button" className="link-button" onClick={clearChecked}>
            Clear
          </button>
        </>
      ) : (
        <button
          type="button"
          className="link-button"
          onClick={checkAllLoaded}
          disabled={assets.length === 0}
        >
          Select all loaded
        </button>
      )}
      <span className="spacer" />
      {inTrash ? (
        <button
          type="button"
          disabled={none}
          onClick={() =>
            void act(
              { action: "restore", assetIds: ids },
              {
                label: `Restored ${plural(ids.length)}`,
                undo: { action: "trash", assetIds: ids },
              },
            )
          }
        >
          Restore {ids.length > 0 ? `(${ids.length})` : ""}
        </button>
      ) : (
        <>
          <button
            type="button"
            disabled={none}
            aria-pressed={allFavorite}
            onClick={() => void act({ action: "favorite", assetIds: ids, favorite: !allFavorite })}
          >
            {allFavorite ? "★ Unfavorite" : "☆ Favorite"}
          </button>
          <button type="button" disabled={none} onClick={() => setDialog("rate")}>
            Rate…
          </button>
          <button type="button" disabled={none} onClick={() => setDialog("move")}>
            Move…
          </button>
          <button type="button" disabled={none} onClick={() => setDialog("album")}>
            Album…
          </button>
          {filter.albumId && (
            <button
              type="button"
              disabled={none}
              onClick={() =>
                void act(
                  { action: "albumRemove", albumId: filter.albumId as string, assetIds: ids },
                  {
                    label: `Removed ${plural(ids.length)} from this album`,
                    undo: { action: "albumAdd", albumId: filter.albumId as string, assetIds: ids },
                  },
                )
              }
            >
              Remove from album
            </button>
          )}
          <button type="button" disabled={none} onClick={() => setDialog("tag")}>
            Tag…
          </button>
          <button
            type="button"
            className="danger"
            disabled={none}
            onClick={() => setDialog("trash")}
          >
            Move to Trash
          </button>
        </>
      )}

      {dialog === "trash" && (
        <ConfirmTrashDialog
          names={targets.map((a) => a.displayName)}
          total={ids.length}
          busy={editing}
          onClose={close}
          onConfirm={() =>
            void act(
              { action: "trash", assetIds: ids },
              {
                label: `Moved ${plural(ids.length)} to Trash`,
                undo: { action: "restore", assetIds: ids },
              },
            ).then(close)
          }
        />
      )}
      {dialog === "move" && (
        <MoveDialog
          count={ids.length}
          currentFolderId={targets.length === 1 ? targets[0]?.folderId : undefined}
          busy={editing}
          onClose={close}
          onConfirm={(folderId) =>
            void act(
              { action: "move", assetIds: ids, folderId },
              { label: `Moved ${plural(ids.length)}` },
            ).then(close)
          }
        />
      )}
      {dialog === "tag" && (
        <TagDialog
          count={ids.length}
          busy={editing}
          onClose={close}
          onConfirm={(name, mode) => void tag(ids, name, mode).then(close)}
        />
      )}
      {dialog === "rate" && (
        <RateDialog
          count={ids.length}
          busy={editing}
          onClose={close}
          onConfirm={(rating) =>
            void act(
              { action: "rating", assetIds: ids, rating },
              {
                label: rating
                  ? `Rated ${plural(ids.length)}`
                  : `Cleared the rating on ${plural(ids.length)}`,
              },
            ).then(close)
          }
        />
      )}
      {dialog === "album" && (
        <AlbumDialog
          count={ids.length}
          busy={editing}
          onClose={close}
          onConfirm={(target) => void addToAlbum(target).then(close)}
        />
      )}
    </div>
  );
}
