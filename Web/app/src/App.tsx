import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { LIMITS, columnWidth } from "./layout/layoutModel";
import { ResizeHandle } from "./layout/ResizeHandle";
import { usePanelLayout } from "./layout/usePanelLayout";
import { libraryApi, type LibraryInfo } from "./library/api";
import { LibraryProvider } from "./library/LibraryContext";
import { ChatPanel } from "./panels/ChatPanel";
import { ExplorerPanel } from "./panels/ExplorerPanel";
import { Panel } from "./panels/Panel";
import { Workspace } from "./panels/Workspace";
import { useApiStatus } from "./useApiStatus";

const STATUS_LABEL = {
  checking: "Checking API…",
  ok: "API connected",
  unreachable: "API unreachable",
};

const STORED_LIBRARY = "framebase.library.v1";

function useLibraries() {
  const [libraries, setLibraries] = useState<LibraryInfo[]>([]);
  const [libraryId, setLibraryId] = useState<string | undefined>();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    libraryApi
      .config()
      .then((c) => {
        const list = c.libraries ?? [];
        let saved: string | null = null;
        try {
          saved = localStorage.getItem(STORED_LIBRARY);
        } catch {
          /* storage can be blocked */
        }
        setLibraries(list);
        setLibraryId(list.find((l) => l.id === saved)?.id ?? list[0]?.id);
      })
      .catch(() => undefined)
      .finally(() => setReady(true));
  }, []);
  const choose = (id: string) => {
    setLibraryId(id);
    try {
      localStorage.setItem(STORED_LIBRARY, id);
    } catch {
      /* per-viewer convenience only */
    }
  };
  return { libraries, libraryId, choose, ready };
}

export function App() {
  const { libraries, libraryId, choose, ready } = useLibraries();
  // Wait for the library list so the first request goes to the right library; a switch remounts everything.
  if (!ready) return null;
  return (
    <LibraryProvider key={libraryId ?? "default"} libraryId={libraryId}>
      <Shell libraries={libraries} libraryId={libraryId} onChooseLibrary={choose} />
    </LibraryProvider>
  );
}

function Shell({
  libraries,
  libraryId,
  onChooseLibrary,
}: {
  libraries: LibraryInfo[];
  libraryId?: string;
  onChooseLibrary: (id: string) => void;
}) {
  const { layout, resize, toggle, reset } = usePanelLayout();
  const status = useApiStatus();

  // explorer | create chat | workspace | understand chat, with a drag handle between each pair.
  const columns = [
    `${columnWidth(layout, "explorer")}px`,
    "6px",
    `${columnWidth(layout, "create")}px`,
    "6px",
    "minmax(240px, 1fr)",
    "6px",
    `${columnWidth(layout, "understand")}px`,
  ].join(" ");

  return (
    <>
      <div className="shell">
        <header className="topbar">
          <h1>Framebase</h1>
          {libraries.length > 1 && (
            <select
              className="library-switch"
              aria-label="Library"
              value={libraryId}
              onChange={(e) => onChooseLibrary(e.target.value)}
            >
              {libraries.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.label}
                </option>
              ))}
            </select>
          )}
          <span className={`status status--${status}`}>{STATUS_LABEL[status]}</span>
          <button type="button" className="link-button" onClick={reset}>
            Reset layout
          </button>
        </header>
        <div className="panes" style={{ gridTemplateColumns: columns } as CSSProperties}>
          <Panel
            title="Explorer"
            collapsed={layout.collapsed.explorer}
            onToggle={() => toggle("explorer")}
          >
            <ExplorerPanel />
          </Panel>
          <ResizeHandle
            label="Explorer"
            value={layout.widths.explorer}
            {...LIMITS.explorer}
            direction={1}
            disabled={layout.collapsed.explorer}
            onChange={(w) => resize("explorer", w)}
          />
          <Panel
            title="Create"
            collapsed={layout.collapsed.create}
            onToggle={() => toggle("create")}
          >
            <ChatPanel kind="create" />
          </Panel>
          <ResizeHandle
            label="Create chat"
            value={layout.widths.create}
            {...LIMITS.create}
            direction={1}
            disabled={layout.collapsed.create}
            onChange={(w) => resize("create", w)}
          />
          <Workspace />
          <ResizeHandle
            label="Understand chat"
            value={layout.widths.understand}
            {...LIMITS.understand}
            direction={-1}
            disabled={layout.collapsed.understand}
            onChange={(w) => resize("understand", w)}
          />
          <Panel
            title="Understand"
            collapsed={layout.collapsed.understand}
            onToggle={() => toggle("understand")}
          >
            <ChatPanel kind="understand" />
          </Panel>
        </div>
      </div>
    </>
  );
}
