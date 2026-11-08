import { useState } from "react";
import type { LibraryAsset } from "@framebase/web-contracts";
import { useLibrary } from "../library/LibraryContext";
import { TagDialog } from "./Dialogs";
import { useTagAction } from "./ActionBar";

/** Edit controls for the open item: name, favorite, rating and tags. Rendered only when editing is allowed. */
export function PreviewEditor({ asset }: { asset: LibraryAsset }) {
  const { act, editing } = useLibrary();
  const tag = useTagAction();
  const [name, setName] = useState(asset.displayName);
  const [editedFor, setEditedFor] = useState(`${asset.id}:${asset.revision}`);
  const [addingTag, setAddingTag] = useState(false);

  // Follow the asset when a different one is opened or the server changed it.
  const key = `${asset.id}:${asset.revision}`;
  if (key !== editedFor) {
    setEditedFor(key);
    setName(asset.displayName);
  }

  const commitName = () => {
    const next = name.trim();
    if (!next || next === asset.displayName) {
      setName(asset.displayName);
      return;
    }
    void act({ action: "rename", assetId: asset.id, displayName: next });
  };

  return (
    <div className="editor">
      <label className="field">
        <span className="muted">Name</span>
        <input
          value={name}
          maxLength={160}
          disabled={editing}
          onChange={(e) => setName(e.target.value)}
          onBlur={commitName}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
            if (e.key === "Escape") setName(asset.displayName);
          }}
        />
      </label>

      <div className="editor-row">
        <button
          type="button"
          className={`toggle${asset.favorite ? " is-on" : ""}`}
          aria-pressed={asset.favorite}
          disabled={editing}
          onClick={() =>
            void act({ action: "favorite", assetId: asset.id, favorite: !asset.favorite })
          }
        >
          {asset.favorite ? "★ Favorite" : "☆ Favorite"}
        </button>
        <div className="stars" role="group" aria-label="Rating">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              className={n <= asset.rating ? "is-on" : undefined}
              aria-label={`${n} star${n === 1 ? "" : "s"}`}
              aria-pressed={n <= asset.rating}
              disabled={editing}
              // Clicking the current rating clears it.
              onClick={() =>
                void act({
                  action: "rating",
                  assetId: asset.id,
                  rating: n === asset.rating ? 0 : n,
                })
              }
            >
              ★
            </button>
          ))}
        </div>
      </div>

      <div className="chips" aria-label="Tags">
        {asset.tags.map((t, i) => (
          <span key={asset.tagIds[i] ?? t} className="chip">
            {t}
            <button
              type="button"
              aria-label={`Remove tag ${t}`}
              disabled={editing}
              onClick={() =>
                void act(
                  {
                    action: "tag",
                    assetIds: [asset.id],
                    tagId: asset.tagIds[i] as string,
                    mode: "remove",
                  },
                  { label: `Removed tag ${t}` },
                )
              }
            >
              ×
            </button>
          </span>
        ))}
        <button
          type="button"
          className="link-button"
          disabled={editing}
          onClick={() => setAddingTag(true)}
        >
          + Tag
        </button>
      </div>

      {addingTag && (
        <TagDialog
          count={1}
          busy={editing}
          onClose={() => setAddingTag(false)}
          onConfirm={(tagName, mode) =>
            void tag([asset.id], tagName, mode).then(() => setAddingTag(false))
          }
        />
      )}
    </div>
  );
}
