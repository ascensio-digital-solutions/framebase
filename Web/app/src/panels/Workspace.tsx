import { useEffect, useState } from "react";
import { imageUrl } from "../library/api";
import { folderPath, formatBytes } from "../library/folderTree";
import { useLibrary } from "../library/LibraryContext";
import { GridView, ListView } from "./AssetViews";

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

function Preview() {
  const { selected, structure } = useLibrary();
  if (!selected)
    return (
      <p className="muted">Select an item to open it here. Generated results appear here too.</p>
    );
  return (
    <div className="preview-body">
      <img
        className="preview-image"
        src={imageUrl(selected.id, "preview-1600")}
        alt={selected.displayName}
      />
      <dl className="meta">
        <dt>Name</dt>
        <dd>{selected.displayName}</dd>
        <dt>Folder</dt>
        <dd>{folderPath(structure?.folders ?? [], selected.folderId)}</dd>
        <dt>Type</dt>
        <dd>
          {selected.mediaType} · {formatBytes(selected.byteSize)}
        </dd>
        <dt>Added</dt>
        <dd>{new Date(selected.createdAt).toLocaleDateString()}</dd>
        <dt>Tags</dt>
        <dd>{selected.tags.length ? selected.tags.join(", ") : "None"}</dd>
      </dl>
    </div>
  );
}

function Collection({ view }: { view: ViewId }) {
  const { phase, message, assets, total, loadingAssets } = useLibrary();
  if (phase === "loading") return <p className="muted">Loading library…</p>;
  if (phase !== "ready") return <p className="muted">{message}</p>;
  if (view === "board")
    return (
      <p className="muted">The board arrives with the board milestone. Use Grid or List for now.</p>
    );
  if (!loadingAssets && assets.length === 0)
    return <p className="muted">Nothing matches this view.</p>;
  return (
    <>
      <p className="muted count">
        {total.toLocaleString()} item{total === 1 ? "" : "s"}
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
