import { useMemo, useState } from "react";
import { useLibrary } from "../library/LibraryContext";
import { ConfirmTrashDialog, MoveDialog, TagDialog } from "./Dialogs";

type Dialog = "trash" | "move" | "tag" | null;

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
  const close = () => setDialog(null);
  const plural = (n: number) => `${n} item${n === 1 ? "" : "s"}`;

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
          disabled={editing || ids.length === 0}
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
            disabled={editing || ids.length === 0}
            onClick={() => setDialog("move")}
          >
            Move…
          </button>
          <button
            type="button"
            disabled={editing || ids.length === 0}
            onClick={() => setDialog("tag")}
          >
            Tag…
          </button>
          <button
            type="button"
            className="danger"
            disabled={editing || ids.length === 0}
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
    </div>
  );
}
