import { useState } from "react";

const VIEWS = [
  { id: "grid", label: "Grid" },
  { id: "list", label: "List" },
  { id: "board", label: "Board" },
] as const;

type ViewId = (typeof VIEWS)[number]["id"];

/** Central workspace: one collection, three views, plus a separate preview/output area. */
export function Workspace() {
  const [view, setView] = useState<ViewId>("grid");
  return (
    <main className="workspace">
      <div className="view-tabs" role="tablist" aria-label="Collection view">
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
      <div className="workspace-split">
        <section id="view-panel" role="tabpanel" aria-labelledby={`tab-${view}`} className="view">
          <p className="muted">
            {VIEWS.find((v) => v.id === view)?.label} view shows the active collection once the
            library workspace is connected to the catalog.
          </p>
        </section>
        <section className="preview" aria-label="Preview and output">
          <h2>Preview</h2>
          <p className="muted">
            Select an item to open it here. Generated results appear here too.
          </p>
        </section>
      </div>
    </main>
  );
}
