import { useEffect, useState } from "react";
import { imageUrl } from "../library/api";
import { folderPath, formatBytes } from "../library/folderTree";
import { useLibrary } from "../library/LibraryContext";
import { ActionBar } from "./ActionBar";
import { GridView, ListView } from "./AssetViews";
import { PreviewEditor } from "./PreviewEditor";

const VIEWS = [
  { id: "grid", label: "Grid" },
  { id: "list", label: "List" },
  { id: "board", label: "Board" },
] as const;

type ViewId = (typeof VIEWS)[number]["id"];

function SearchBox() {
  const { filter, setFilter } = useLibrary();
  const [text, setText] = useState(filter.q);
  // Debounce so typing does not fire a request per keystroke.
  useEffect(() => {
    const id = setTimeout(() => setFilter({ q: text }), 250);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);
  return (
    <input
      className="search"
      type="search"
      placeholder="Search names…"
      aria-label="Search names"
      value={text}
      onChange={(e) => setText(e.target.value)}
    />
  );
}

function NoticeBar() {
  const { notice, dismissNotice } = useLibrary();
  if (!notice) return null;
  return (
    <div
      className={`notice notice--${notice.kind}`}
      role={notice.kind === "error" ? "alert" : "status"}
    >
      <span>{notice.text}</span>
      {notice.undo && (
        <button
          type="button"
          className="link-button"
          onClick={() => {
            notice.undo?.();
            dismissNotice();
          }}
        >
          Undo
        </button>
      )}
      <button type="button" className="icon-button" aria-label="Dismiss" onClick={dismissNotice}>
        ×
      </button>
    </div>
  );
}

function Preview() {
  const { selected, structure, canEdit } = useLibrary();
  if (!selected)
    return (
      <p className="muted">Select an item to open it here. Generated results appear here too.</p>
    );
  const editable = canEdit && !selected.trashedAt;
  return (
    <div className="preview-body">
      <img
        className="preview-image"
        src={imageUrl(selected.id, "preview-1600")}
        alt={selected.displayName}
      />
      <div>
        {editable && <PreviewEditor asset={selected} />}
        <dl className="meta">
          {!editable && (
            <>
              <dt>Name</dt>
              <dd>{selected.displayName}</dd>
            </>
          )}
          {selected.trashedAt ? (
            <>
              <dt>Status</dt>
              <dd>In Trash since {new Date(selected.trashedAt).toLocaleDateString()}</dd>
            </>
          ) : (
            <>
              <dt>Folder</dt>
              <dd>{folderPath(structure?.folders ?? [], selected.folderId)}</dd>
            </>
          )}
          <dt>Type</dt>
          <dd>
            {selected.mediaType} · {formatBytes(selected.byteSize)}
          </dd>
          <dt>Added</dt>
          <dd>{new Date(selected.createdAt).toLocaleDateString()}</dd>
          {!editable && (
            <>
              <dt>Tags</dt>
              <dd>{selected.tags.length ? selected.tags.join(", ") : "None"}</dd>
            </>
          )}
        </dl>
      </div>
    </div>
  );
}

function Collection({ view }: { view: ViewId }) {
  const { phase, message, assets, total, loadingAssets, filter } = useLibrary();
  if (phase === "loading")
    return <p className="muted">Loading library… the first load can take up to a minute.</p>;
  if (phase !== "ready") return <p className="muted">{message}</p>;
  if (view === "board")
    return (
      <p className="muted">The board arrives with the board milestone. Use Grid or List for now.</p>
    );
  if (!loadingAssets && assets.length === 0)
    return (
      <p className="muted">{filter.trashed ? "Trash is empty." : "Nothing matches this view."}</p>
    );
  return (
    <>
      <p className="muted count">
        {filter.trashed ? "Trash · " : ""}
        {total.toLocaleString()} item{total === 1 ? "" : "s"}
        {filter.trashed ? ". Restore puts items back in their original folder." : ""}
      </p>
      {view === "grid" ? <GridView /> : <ListView />}
    </>
  );
}

/** Central workspace: one collection, three views, plus a separate preview/output area. */
export function Workspace() {
  const [view, setView] = useState<ViewId>("grid");
  return (
    <main className="workspace">
      <div className="view-tabs">
        <div role="tablist" aria-label="Collection view" className="tablist">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              role="tab"
              id={`tab-${v.id}`}
              aria-selected={view === v.id}
              aria-controls="view-panel"
              className="tab"
              onClick={() => setView(v.id)}
            >
              {v.label}
            </button>
          ))}
        </div>
        <SearchBox />
      </div>
      <ActionBar />
      <NoticeBar />
      <div className="workspace-split">
        <section id="view-panel" role="tabpanel" aria-labelledby={`tab-${view}`} className="view">
          <Collection view={view} />
        </section>
        <section className="preview" aria-label="Preview and output">
          <h2>Preview</h2>
          <Preview />
        </section>
      </div>
    </main>
  );
}
