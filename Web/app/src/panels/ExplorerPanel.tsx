import { useMemo } from "react";
import { buildTree, type FolderNode } from "../library/folderTree";
import { useLibrary } from "../library/LibraryContext";

function FolderItem({ node, depth }: { node: FolderNode; depth: number }) {
  const { filter, scopeTo } = useLibrary();
  const active = filter.folderId === node.folder.id;
  return (
    <li>
      <button
        type="button"
        className={`tree-item${active ? " is-active" : ""}`}
        style={{ paddingLeft: 8 + depth * 14 }}
        aria-current={active ? "true" : undefined}
        onClick={() => scopeTo({ folderId: node.folder.id })}
      >
        <span className="tree-name">{node.folder.name}</span>
        <span className="tree-count">{node.folder.assetCount.toLocaleString()}</span>
      </button>
      {node.children.length > 0 && (
        <ul className="tree-list">
          {node.children.map((child) => (
            <FolderItem key={child.folder.id} node={child} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ExplorerPanel() {
  const { phase, message, summary, structure, filter, scopeTo, refresh } = useLibrary();
  const tree = useMemo(() => buildTree(structure?.folders ?? []), [structure]);

  if (phase === "loading") return <p className="muted">Loading library…</p>;
  if (phase !== "ready" || !structure) return <p className="muted">{message}</p>;

  const allActive = !filter.folderId && !filter.albumId && !filter.tagId;
  return (
    <nav aria-label="Library">
      <button
        type="button"
        className={`tree-item${allActive ? " is-active" : ""}`}
        onClick={() => scopeTo({})}
      >
        <span className="tree-name">All media</span>
        <span className="tree-count">{summary?.assetCount.toLocaleString()}</span>
      </button>

      <h3 className="tree-heading">Folders</h3>
      <ul className="tree-list">
        {tree.map((node) => (
          <FolderItem key={node.folder.id} node={node} depth={0} />
        ))}
      </ul>

      <details className="tree-group">
        <summary>Albums ({structure.albums.length})</summary>
        <ul className="tree-list">
          {structure.albums.map((album) => (
            <li key={album.id}>
              <button
                type="button"
                className={`tree-item${filter.albumId === album.id ? " is-active" : ""}`}
                onClick={() => scopeTo({ albumId: album.id })}
              >
                <span className="tree-name">{album.name}</span>
                <span className="tree-count">{album.assetCount.toLocaleString()}</span>
              </button>
            </li>
          ))}
        </ul>
      </details>

      <details className="tree-group">
        <summary>
          Tags ({structure.tagsTotal.toLocaleString()}
          {structure.tagsTotal > structure.tags.length ? `, top ${structure.tags.length}` : ""})
        </summary>
        <ul className="tree-list">
          {structure.tags.map((tag) => (
            <li key={tag.id}>
              <button
                type="button"
                className={`tree-item${filter.tagId === tag.id ? " is-active" : ""}`}
                onClick={() => scopeTo({ tagId: tag.id })}
              >
                <span className="tree-name">{tag.name}</span>
                <span className="tree-count">{tag.assetCount.toLocaleString()}</span>
              </button>
            </li>
          ))}
        </ul>
      </details>

      <p className="muted">
        Snapshot {summary ? new Date(summary.fetchedAt).toLocaleTimeString() : ""} ·{" "}
        <button type="button" className="link-button" onClick={refresh}>
          Refresh
        </button>
      </p>
    </nav>
  );
}
