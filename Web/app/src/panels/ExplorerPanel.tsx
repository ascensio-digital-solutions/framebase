import { useMemo, useState } from "react";
import { buildTree, type FolderNode } from "../library/folderTree";
import { useLibrary } from "../library/LibraryContext";
import { ConfirmDialog, NameDialog, ParentFolderDialog } from "./Dialogs";

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

type Dialog =
  | "newFolder"
  | "newSubfolder"
  | "renameFolder"
  | "moveFolder"
  | "newAlbum"
  | "renameAlbum"
  | "deleteAlbum"
  | null;

export function ExplorerPanel() {
  const {
    phase,
    message,
    summary,
    structure,
    filter,
    scopeTo,
    showTrash,
    canEdit,
    editing,
    act,
    refresh,
  } = useLibrary();
  const tree = useMemo(() => buildTree(structure?.folders ?? []), [structure]);
  const [dialog, setDialog] = useState<Dialog>(null);

  if (phase === "loading")
    return <p className="muted">Loading library… the first load can take up to a minute.</p>;
  if (phase !== "ready" || !structure) return <p className="muted">{message}</p>;

  const allActive = !filter.folderId && !filter.albumId && !filter.tagId && !filter.trashed;
  const folder = structure.folders.find((f) => f.id === filter.folderId);
  const album = structure.albums.find((a) => a.id === filter.albumId);
  const close = () => setDialog(null);

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

      <h3 className="tree-heading tree-heading--row">
        Folders
        {canEdit && (
          <button
            type="button"
            className="link-button"
            aria-label="New top-level folder"
            onClick={() => setDialog("newFolder")}
          >
            + New
          </button>
        )}
      </h3>
      <ul className="tree-list">
        {tree.map((node) => (
          <FolderItem key={node.folder.id} node={node} depth={0} />
        ))}
      </ul>
      {canEdit && folder && !folder.systemKind && (
        <div className="tree-tools" role="group" aria-label={`Folder ${folder.name}`}>
          <button
            type="button"
            className="link-button"
            disabled={editing}
            onClick={() => setDialog("newSubfolder")}
          >
            New subfolder
          </button>
          <button
            type="button"
            className="link-button"
            disabled={editing}
            onClick={() => setDialog("renameFolder")}
          >
            Rename
          </button>
          <button
            type="button"
            className="link-button"
            disabled={editing}
            onClick={() => setDialog("moveFolder")}
          >
            Move…
          </button>
        </div>
      )}

      <details className="tree-group" open={Boolean(album)}>
        <summary>Albums ({structure.albums.length})</summary>
        {canEdit && (
          <div className="tree-tools">
            <button type="button" className="link-button" onClick={() => setDialog("newAlbum")}>
              + New album
            </button>
          </div>
        )}
        <ul className="tree-list">
          {structure.albums.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                className={`tree-item${filter.albumId === a.id ? " is-active" : ""}`}
                onClick={() => scopeTo({ albumId: a.id })}
              >
                <span className="tree-name">{a.name}</span>
                <span className="tree-count">{a.assetCount.toLocaleString()}</span>
              </button>
            </li>
          ))}
        </ul>
        {canEdit && album && (
          <div className="tree-tools" role="group" aria-label={`Album ${album.name}`}>
            <button
              type="button"
              className="link-button"
              disabled={editing}
              onClick={() => setDialog("renameAlbum")}
            >
              Rename
            </button>
            <button
              type="button"
              className="link-button"
              disabled={editing}
              onClick={() => setDialog("deleteAlbum")}
            >
              Delete album
            </button>
          </div>
        )}
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

      {(canEdit || (summary?.trashedCount ?? 0) > 0) && (
        <>
          <h3 className="tree-heading">Trash</h3>
          <button
            type="button"
            className={`tree-item${filter.trashed ? " is-active" : ""}`}
            aria-current={filter.trashed ? "true" : undefined}
            onClick={showTrash}
          >
            <span className="tree-name">Trash</span>
            <span className="tree-count">{(summary?.trashedCount ?? 0).toLocaleString()}</span>
          </button>
        </>
      )}

      <p className="muted">
        Snapshot {summary ? new Date(summary.fetchedAt).toLocaleTimeString() : ""} ·{" "}
        <button type="button" className="link-button" onClick={refresh}>
          Refresh
        </button>
      </p>

      {dialog === "newFolder" && (
        <NameDialog
          title="New folder"
          label="Folder name"
          confirmLabel="Create"
          busy={editing}
          onClose={close}
          onConfirm={(name) =>
            void act(
              { action: "createFolder", name, parentId: null },
              { label: `Created folder “${name}”` },
            ).then(close)
          }
        />
      )}
      {dialog === "newSubfolder" && folder && (
        <NameDialog
          title={`New folder inside ${folder.name}`}
          label="Folder name"
          confirmLabel="Create"
          busy={editing}
          onClose={close}
          onConfirm={(name) =>
            void act(
              { action: "createFolder", name, parentId: folder.id },
              { label: `Created folder “${name}”` },
            ).then(close)
          }
        />
      )}
      {dialog === "renameFolder" && folder && (
        <NameDialog
          title="Rename folder"
          label="Folder name"
          initial={folder.name}
          confirmLabel="Rename"
          busy={editing}
          onClose={close}
          onConfirm={(name) =>
            void act(
              { action: "renameFolder", folderId: folder.id, name },
              { label: "Folder renamed" },
            ).then(close)
          }
        />
      )}
      {dialog === "moveFolder" && folder && (
        <ParentFolderDialog
          title={`Move ${folder.name}`}
          excludeId={folder.id}
          currentParentId={folder.parentId}
          busy={editing}
          onClose={close}
          onConfirm={(parentId) =>
            void act(
              { action: "moveFolder", folderId: folder.id, parentId },
              { label: "Folder moved" },
            ).then(close)
          }
        />
      )}
      {dialog === "newAlbum" && (
        <NameDialog
          title="New album"
          label="Album name"
          confirmLabel="Create"
          busy={editing}
          onClose={close}
          onConfirm={(name) =>
            void act({ action: "createAlbum", name }, { label: `Created album “${name}”` }).then(
              close,
            )
          }
        />
      )}
      {dialog === "renameAlbum" && album && (
        <NameDialog
          title="Rename album"
          label="Album name"
          initial={album.name}
          confirmLabel="Rename"
          busy={editing}
          onClose={close}
          onConfirm={(name) =>
            void act(
              { action: "renameAlbum", albumId: album.id, name },
              { label: "Album renamed" },
            ).then(close)
          }
        />
      )}
      {dialog === "deleteAlbum" && album && (
        <ConfirmDialog
          title={`Delete the album “${album.name}”?`}
          body="This removes the album only. The photos in it stay in your library, in their folders."
          confirmLabel="Delete album"
          danger
          busy={editing}
          onClose={close}
          onConfirm={() =>
            void act(
              { action: "deleteAlbum", albumId: album.id },
              { label: `Deleted the album “${album.name}”` },
            ).then(() => {
              scopeTo({});
              close();
            })
          }
        />
      )}
    </nav>
  );
}
