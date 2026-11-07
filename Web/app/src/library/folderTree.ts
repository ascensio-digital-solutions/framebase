import type { LibraryFolder } from "@framebase/web-contracts";

export interface FolderNode {
  folder: LibraryFolder;
  children: FolderNode[];
}

/**
 * Builds a forest from a flat folder list, keeping the incoming order. A folder whose parent is missing
 * becomes a root, and a cycle in malformed data is broken rather than looping forever.
 */
export function buildTree(folders: LibraryFolder[]): FolderNode[] {
  const nodes = new Map(
    folders.map((folder) => [folder.id, { folder, children: [] as FolderNode[] }]),
  );
  const roots: FolderNode[] = [];
  for (const node of nodes.values()) {
    const parent = node.folder.parentId ? nodes.get(node.folder.parentId) : undefined;
    if (parent && !isAncestor(nodes, node.folder.id, parent.folder.id)) parent.children.push(node);
    else roots.push(node);
  }
  return roots;
}

/** True if `candidate` is `id` itself or sits beneath it, which would make attaching `id` under it a cycle. */
function isAncestor(nodes: Map<string, FolderNode>, id: string, candidate: string): boolean {
  const seen = new Set<string>();
  for (let cur: string | null | undefined = candidate; cur && !seen.has(cur);) {
    if (cur === id) return true;
    seen.add(cur);
    cur = nodes.get(cur)?.folder.parentId;
  }
  return false;
}

/** "01_products / swiss-lace" style path for display. */
export function folderPath(folders: LibraryFolder[], id: string): string {
  const byId = new Map(folders.map((f) => [f.id, f]));
  const parts: string[] = [];
  const seen = new Set<string>();
  for (
    let cur = byId.get(id);
    cur && !seen.has(cur.id);
    cur = cur.parentId ? byId.get(cur.parentId) : undefined
  ) {
    seen.add(cur.id);
    parts.unshift(cur.name);
  }
  return parts.join(" / ");
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}
