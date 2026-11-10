import { describe, expect, it } from "vitest";
import {
  COLLAPSED_WIDTH,
  DEFAULT_LAYOUT,
  LIMITS,
  clampWidth,
  columnWidth,
  parseLayout,
  setWidth,
  toggleCollapsed,
} from "./layoutModel";

describe("layoutModel", () => {
  it("clamps widths to each panel's limits", () => {
    expect(clampWidth("create", 10)).toBe(LIMITS.create.min);
    expect(clampWidth("create", 9999)).toBe(LIMITS.create.max);
    expect(clampWidth("explorer", Number.NaN)).toBe(DEFAULT_LAYOUT.widths.explorer);
  });

  it("collapses to a rail without losing the stored width", () => {
    const resized = setWidth(DEFAULT_LAYOUT, "understand", 500);
    const collapsed = toggleCollapsed(resized, "understand");
    expect(columnWidth(collapsed, "understand")).toBe(COLLAPSED_WIDTH);
    expect(columnWidth(toggleCollapsed(collapsed, "understand"), "understand")).toBe(500);
  });

  it("restores valid saved state and ignores bad fields", () => {
    const restored = parseLayout(
      JSON.stringify({ widths: { create: 480, explorer: "wide" }, collapsed: { create: true } }),
    );
    expect(restored.widths.create).toBe(480);
    expect(restored.widths.explorer).toBe(DEFAULT_LAYOUT.widths.explorer);
    expect(restored.collapsed.create).toBe(true);
  });

  it("falls back to defaults for missing or corrupt storage", () => {
    expect(parseLayout(null)).toEqual(DEFAULT_LAYOUT);
    expect(parseLayout("{not json")).toEqual(DEFAULT_LAYOUT);
  });
});
