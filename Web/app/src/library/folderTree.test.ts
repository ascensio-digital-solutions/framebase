import { describe, expect, it } from "vitest";
import type { LibraryFolder } from "@framebase/web-contracts";
import { buildTree, folderPath, formatBytes } from "./folderTree";

const f = (id: string, parentId: string | null, name = id): LibraryFolder => ({
  id,
  name,
  parentId,
  systemKind: null,
  sortOrder: 0,
  assetCount: 0,
});

describe("buildTree", () => {
  it("nests children under parents and keeps order", () => {
    const tree = buildTree([f("a", null), f("b", "a"), f("c", "a"), f("d", null)]);
    expect(tree.map((n) => n.folder.id)).toEqual(["a", "d"]);
    expect(tree[0]?.children.map((n) => n.folder.id)).toEqual(["b", "c"]);
  });

  it("treats a folder with a missing parent as a root", () => {
    expect(buildTree([f("a", "ghost")]).map((n) => n.folder.id)).toEqual(["a"]);
  });

  it("breaks cycles instead of looping", () => {
    const tree = buildTree([f("a", "b"), f("b", "a")]);
    const visit = (nodes: typeof tree): number =>
      nodes.reduce((n, x) => n + 1 + visit(x.children), 0);
    expect(visit(tree)).toBe(2); // both folders appear exactly once
  });
});

describe("folderPath", () => {
  it("joins names from the root down", () => {
    const folders = [f("a", null, "01_products"), f("b", "a", "swiss-lace")];
    expect(folderPath(folders, "b")).toBe("01_products / swiss-lace");
  });
  it("is empty for an unknown folder", () => {
    expect(folderPath([], "x")).toBe("");
  });
});

describe("formatBytes", () => {
  it("scales units", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});
