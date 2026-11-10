import type { ReactNode } from "react";

interface Props {
  title: string;
  collapsed: boolean;
  onToggle: () => void;
  children: ReactNode;
}

/** A side panel that collapses to a slim rail. The body unmounts while collapsed. */
export function Panel({ title, collapsed, onToggle, children }: Props) {
  if (collapsed) {
    return (
      <aside className="panel panel--rail" aria-label={title}>
        <button
          type="button"
          className="icon-button"
          onClick={onToggle}
          aria-label={`Expand ${title}`}
        >
          ›
        </button>
        <span className="rail-title">{title}</span>
      </aside>
    );
  }
  return (
    <aside className="panel" aria-label={title}>
      <header className="panel-header">
        <h2>{title}</h2>
        <button
          type="button"
          className="icon-button"
          onClick={onToggle}
          aria-label={`Collapse ${title}`}
        >
          ‹
        </button>
      </header>
      <div className="panel-body">{children}</div>
    </aside>
  );
}
