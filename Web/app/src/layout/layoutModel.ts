/** Pure layout state for the resizable, collapsible side panels. No DOM access, so it is unit-testable. */

export type PanelId = "explorer" | "create" | "understand";

export interface LayoutState {
  widths: Record<PanelId, number>;
  collapsed: Record<PanelId, boolean>;
}

export const COLLAPSED_WIDTH = 40;

export const LIMITS: Record<PanelId, { min: number; max: number }> = {
  explorer: { min: 180, max: 420 },
  create: { min: 280, max: 640 },
  understand: { min: 280, max: 640 },
};

export const DEFAULT_LAYOUT: LayoutState = {
  widths: { explorer: 220, create: 340, understand: 340 },
  collapsed: { explorer: false, create: false, understand: false },
};

const PANELS = Object.keys(LIMITS) as PanelId[];

export function clampWidth(panel: PanelId, width: number): number {
  const { min, max } = LIMITS[panel];
  if (!Number.isFinite(width)) return DEFAULT_LAYOUT.widths[panel];
  return Math.min(max, Math.max(min, Math.round(width)));
}

export function setWidth(state: LayoutState, panel: PanelId, width: number): LayoutState {
  return { ...state, widths: { ...state.widths, [panel]: clampWidth(panel, width) } };
}

export function toggleCollapsed(state: LayoutState, panel: PanelId): LayoutState {
  return { ...state, collapsed: { ...state.collapsed, [panel]: !state.collapsed[panel] } };
}

/** Rendered column width: a slim rail when collapsed, otherwise the stored width. */
export function columnWidth(state: LayoutState, panel: PanelId): number {
  return state.collapsed[panel] ? COLLAPSED_WIDTH : state.widths[panel];
}

/** Restores saved state, falling back to defaults for anything missing, malformed or out of range. */
export function parseLayout(raw: string | null): LayoutState {
  if (!raw) return DEFAULT_LAYOUT;
  try {
    const data = JSON.parse(raw) as {
      widths?: Partial<Record<PanelId, unknown>>;
      collapsed?: Partial<Record<PanelId, unknown>>;
    };
    const next: LayoutState = structuredClone(DEFAULT_LAYOUT);
    for (const panel of PANELS) {
      const width = data.widths?.[panel];
      if (typeof width === "number") next.widths[panel] = clampWidth(panel, width);
      const collapsed = data.collapsed?.[panel];
      if (typeof collapsed === "boolean") next.collapsed[panel] = collapsed;
    }
    return next;
  } catch {
    return DEFAULT_LAYOUT;
  }
}
