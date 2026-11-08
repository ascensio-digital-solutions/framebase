import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { buildTree, type FolderNode } from "../library/folderTree";
import { useLibrary } from "../library/LibraryContext";

/** The worker only accepts lowercase `namespace:value` tags, so check before sending. */
const TAG_NAME = /^[a-z][a-z0-9_-]{0,63}:[a-z0-9][a-z0-9._-]{0,127}$/;

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  return (
    <dialog ref={ref} className="modal" aria-labelledby={titleId} onClose={onClose}>
      <h2 id={titleId}>{title}</h2>
      {children}
    </dialog>
  );
}

export function ConfirmTrashDialog({
  names,
  total,
  busy,
  onConfirm,
  onClose,
}: {
  names: string[];
  total: number;
  busy: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal title={`Move ${total} item${total === 1 ? "" : "s"} to Trash?`} onClose={onClose}>
      <p>
        {names.slice(0, 3).join(", ")}
        {total > 3 ? ` and ${total - 3} more` : ""} will leave the library.
      </p>
      <p className="muted">
        Nothing is permanently deleted. Items stay in Trash, and restoring puts them back in their
        original folder with their albums and tags.
      </p>
      <div className="modal-actions">
        <button type="button" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="button" className="danger" onClick={onConfirm} disabled={busy}>
          {busy ? "Moving…" : "Move to Trash"}
        </button>
      </div>
    </Modal>
  );
}

function flatten(nodes: FolderNode[], depth = 0): { id: string; label: string }[] {
  return nodes.flatMap((n) => [
    { id: n.folder.id, label: `${"  ".repeat(depth)}${n.folder.name}` },
    ...flatten(n.children, depth + 1),
  ]);
}

export function MoveDialog({
  count,
  currentFolderId,
  busy,
  onConfirm,
  onClose,
}: {
  count: number;
  currentFolderId?: string;
  busy: boolean;
  onConfirm: (folderId: string) => void;
  onClose: () => void;
}) {
  const { structure } = useLibrary();
  const options = useMemo(() => flatten(buildTree(structure?.folders ?? [])), [structure]);
  const [folderId, setFolderId] = useState("");
  return (
    <Modal title={`Move ${count} item${count === 1 ? "" : "s"} to…`} onClose={onClose}>
      <label className="field">
        <span className="muted">Destination folder</span>
        <select value={folderId} onChange={(e) => setFolderId(e.target.value)}>
          <option value="">Choose a folder</option>
          {options.map((o) => (
            <option key={o.id} value={o.id} disabled={o.id === currentFolderId}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <div className="modal-actions">
        <button type="button" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="button" onClick={() => onConfirm(folderId)} disabled={busy || !folderId}>
          {busy ? "Moving…" : "Move"}
        </button>
      </div>
    </Modal>
  );
}

export function TagDialog({
  count,
  busy,
  onConfirm,
  onClose,
}: {
  count: number;
  busy: boolean;
  /** Resolves with the tag name and whether to add or remove it. */
  onConfirm: (name: string, mode: "add" | "remove") => void;
  onClose: () => void;
}) {
  const { structure } = useLibrary();
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"add" | "remove">("add");
  const listId = useId();
  const typed = name.trim();
  const existing = structure?.tags.some((t) => t.name === typed) ?? false;
  const valid = existing || (mode === "add" && TAG_NAME.test(typed));
  return (
    <Modal title={`Tag ${count} item${count === 1 ? "" : "s"}`} onClose={onClose}>
      <fieldset className="radio-row">
        <label>
          <input type="radio" checked={mode === "add"} onChange={() => setMode("add")} /> Add tag
        </label>
        <label>
          <input type="radio" checked={mode === "remove"} onChange={() => setMode("remove")} />{" "}
          Remove tag
        </label>
      </fieldset>
      <label className="field">
        <span className="muted">Tag, for example status:review</span>
        <input
          list={listId}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="namespace:value"
          autoFocus
        />
        <datalist id={listId}>
          {structure?.tags.map((t) => (
            <option key={t.id} value={t.name} />
          ))}
        </datalist>
      </label>
      {typed && !valid && (
        <p className="muted">
          {mode === "remove"
            ? "Choose an existing tag to remove."
            : "Use a lowercase name like status:review, or pick an existing tag."}
        </p>
      )}
      {mode === "add" && typed && valid && !existing && (
        <p className="muted">This creates the tag “{typed}”.</p>
      )}
      <div className="modal-actions">
        <button type="button" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="button" onClick={() => onConfirm(typed, mode)} disabled={busy || !valid}>
          {busy ? "Working…" : mode === "add" ? "Add tag" : "Remove tag"}
        </button>
      </div>
    </Modal>
  );
}
