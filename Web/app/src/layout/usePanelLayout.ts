import { useCallback, useEffect, useState } from "react";
import {
  DEFAULT_LAYOUT,
  type LayoutState,
  type PanelId,
  parseLayout,
  setWidth,
  toggleCollapsed,
} from "./layoutModel";

const STORAGE_KEY = "framebase.layout.v1";

// Storage can be blocked or empty (private windows, cleared site data); the layout must still render.
function load(): LayoutState {
  try {
    return parseLayout(localStorage.getItem(STORAGE_KEY));
  } catch {
    return DEFAULT_LAYOUT;
  }
}

export function usePanelLayout() {
  const [layout, setLayout] = useState<LayoutState>(load);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
    } catch {
      /* per-viewer convenience only */
    }
  }, [layout]);

  const resize = useCallback(
    (panel: PanelId, width: number) => setLayout((s) => setWidth(s, panel, width)),
    [],
  );
  const toggle = useCallback((panel: PanelId) => setLayout((s) => toggleCollapsed(s, panel)), []);
  const reset = useCallback(() => setLayout(DEFAULT_LAYOUT), []);

  return { layout, resize, toggle, reset };
}
