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

export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  danger,
  busy,
  onConfirm,
  onClose,
}: {
  title: string;
  body: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  busy: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal title={title} onClose={onClose}>
      <p>{body}</p>
      <div className="modal-actions">
        <button type="button" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button
          type="button"
          className={danger ? "danger" : undefined}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy ? "Working…" : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}

export function NameDialog({
  title,
  label,
  initial = "",
  confirmLabel,
  busy,
  onConfirm,
  onClose,
}: {
  title: string;
  label: string;
  initial?: string;
  confirmLabel: string;
  busy: boolean;
  onConfirm: (name: string) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(initial);
  const trimmed = name.trim();
  return (
    <Modal title={title} onClose={onClose}>
      <label className="field">
        <span className="muted">{label}</span>
        <input
          value={name}
          maxLength={160}
          autoFocus
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && trimmed && !busy) onConfirm(trimmed);
          }}
        />
      </label>
      <div className="modal-actions">
        <button type="button" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="button" onClick={() => onConfirm(trimmed)} disabled={busy || !trimmed}>
          {busy ? "Working…" : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}

export function RateDialog({
  count,
  busy,
  onConfirm,
  onClose,
}: {
  count: number;
  busy: boolean;
  onConfirm: (rating: number) => void;
  onClose: () => void;
}) {
  return (
    <Modal title={`Rate ${count} item${count === 1 ? "" : "s"}`} onClose={onClose}>
      <div className="stars stars--large" role="group" aria-label="Rating">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            aria-label={`${n} star${n === 1 ? "" : "s"}`}
            disabled={busy}
            onClick={() => onConfirm(n)}
          >
            ★
          </button>
        ))}
      </div>
      <div className="modal-actions">
        <button type="button" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="button" onClick={() => onConfirm(0)} disabled={busy}>
          Clear rating
        </button>
      </div>
    </Modal>
  );
}

export function AlbumDialog({
  count,
  busy,
  onConfirm,
  onClose,
}: {
  count: number;
  busy: boolean;
  onConfirm: (target: { albumId: string } | { newName: string }) => void;
  onClose: () => void;
}) {
  const { structure } = useLibrary();
  const [albumId, setAlbumId] = useState("");
  const [newName, setNewName] = useState("");
  const typed = newName.trim();
  return (
    <Modal title={`Add ${count} item${count === 1 ? "" : "s"} to an album`} onClose={onClose}>
      <label className="field">
        <span className="muted">Existing album</span>
        <select
          value={albumId}
          onChange={(e) => {
            setAlbumId(e.target.value);
            setNewName("");
          }}
        >
          <option value="">Choose an album</option>
          {structure?.albums.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span className="muted">…or create a new album</span>
        <input
          value={newName}
          maxLength={160}
          placeholder="New album name"
          onChange={(e) => {
            setNewName(e.target.value);
            setAlbumId("");
          }}
        />
      </label>
      <div className="modal-actions">
        <button type="button" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button
          type="button"
          disabled={busy || (!albumId && !typed)}
          onClick={() => onConfirm(albumId ? { albumId } : { newName: typed })}
        >
          {busy ? "Working…" : "Add to album"}
        </button>
      </div>
    </Modal>
  );
}

function withoutSubtree(nodes: FolderNode[], excludeId?: string): FolderNode[] {
  return nodes
    .filter((n) => n.folder.id !== excludeId)
    .map((n) => ({ ...n, children: withoutSubtree(n.children, excludeId) }));
}

/** Picks a parent folder (or the top level) for a new or moved folder. */
export function ParentFolderDialog({
  title,
  excludeId,
  currentParentId,
  busy,
  onConfirm,
  onClose,
}: {
  title: string;
  /** A folder being moved: it and everything beneath it are not valid destinations. */
  excludeId?: string;
  currentParentId?: string | null;
  busy: boolean;
  onConfirm: (parentId: string | null) => void;
  onClose: () => void;
}) {
  const { structure } = useLibrary();
  const options = useMemo(
    () => flatten(withoutSubtree(buildTree(structure?.folders ?? []), excludeId)),
    [structure, excludeId],
  );
  const [choice, setChoice] = useState<string | undefined>(undefined);
  return (
    <Modal title={title} onClose={onClose}>
      <label className="field">
        <span className="muted">Place it inside</span>
        <select value={choice ?? ""} onChange={(e) => setChoice(e.target.value)}>
          <option value="" disabled>
            Choose a location
          </option>
          <option value="__top__" disabled={currentParentId === null}>
            Top level
          </option>
          {options.map((o) => (
            <option key={o.id} value={o.id} disabled={o.id === currentParentId}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <div className="modal-actions">
        <button type="button" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button
          type="button"
          disabled={busy || choice === undefined || choice === ""}
          onClick={() => onConfirm(choice === "__top__" ? null : (choice as string))}
        >
          {busy ? "Working…" : "Choose"}
        </button>
      </div>
    </Modal>
  );
}
