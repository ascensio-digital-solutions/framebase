import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import type { LibraryAsset, LibraryStructure, LibrarySummary } from "@framebase/web-contracts";
import { ApiError, libraryApi } from "./api";

export interface Filter {
  folderId?: string;
  albumId?: string;
  tagId?: string;
  q: string;
}

export type Phase = "loading" | "ready" | "unconfigured" | "error";

interface LibraryState {
  phase: Phase;
  message?: string;
  summary?: LibrarySummary;
  structure?: LibraryStructure;
  filter: Filter;
  assets: LibraryAsset[];
  total: number;
  hasMore: boolean;
  loadingAssets: boolean;
  selected?: LibraryAsset;
  setFilter: (next: Partial<Filter>) => void;
  /** Replaces the whole scope: only the keys given stay set. Used when picking a folder, album or tag. */
  scopeTo: (scope: Pick<Filter, "folderId" | "albumId" | "tagId">) => void;
  loadMore: () => void;
  select: (asset: LibraryAsset | undefined) => void;
  refresh: () => void;
}

const Ctx = createContext<LibraryState | null>(null);

export function useLibrary(): LibraryState {
  const value = useContext(Ctx);
  if (!value) throw new Error("useLibrary must be used inside <LibraryProvider>");
  return value;
}

function describe(error: unknown): { phase: Phase; message: string } {
  if (error instanceof ApiError && error.code === "cloud_not_configured")
    return {
      phase: "unconfigured",
      message:
        "Not connected to Cloudflare yet. Set FRAMEBASE_CLOUD_API_URL and FRAMEBASE_CLOUD_PAIRING_SECRET, then restart the API.",
    };
  if (error instanceof ApiError && error.code === "library_access_unprotected")
    return {
      phase: "unconfigured",
      message:
        "Library access is disabled in production until an authentication layer is in place.",
    };
  if (error instanceof ApiError && error.code === "cloud_unavailable")
    return {
      phase: "error",
      message: "The Framebase Cloudflare API did not respond. Try again shortly.",
    };
  return { phase: "error", message: "Could not load the library." };
}

export function LibraryProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [message, setMessage] = useState<string>();
  const [summary, setSummary] = useState<LibrarySummary>();
  const [structure, setStructure] = useState<LibraryStructure>();
  const [filter, setFilterState] = useState<Filter>({ q: "" });
  const [assets, setAssets] = useState<LibraryAsset[]>([]);
  const [total, setTotal] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [selected, setSelected] = useState<LibraryAsset>();
  const [reloadKey, setReloadKey] = useState(0);
  const pageRequest = useRef(0);

  // Library structure and summary load once, and again on refresh.
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([libraryApi.summary(controller.signal), libraryApi.structure(controller.signal)])
      .then(([s, st]) => {
        setSummary(s);
        setStructure(st);
        setPhase("ready");
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const d = describe(error);
        setPhase(d.phase);
        setMessage(d.message);
      });
    return () => controller.abort();
  }, [reloadKey]);

  // The first page reloads whenever the scope or search changes.
  useEffect(() => {
    if (phase !== "ready") return;
    const controller = new AbortController();
    const request = ++pageRequest.current;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the flag must flip before the fetch starts
    setLoadingAssets(true);
    libraryApi
      .assets(filter, controller.signal)
      .then((page) => {
        if (request !== pageRequest.current) return;
        setAssets(page.assets);
        setTotal(page.total);
        setCursor(page.nextCursor);
        setSelected(undefined);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const d = describe(error);
        setPhase(d.phase);
        setMessage(d.message);
      })
      .finally(() => {
        if (request === pageRequest.current) setLoadingAssets(false);
      });
    return () => controller.abort();
  }, [phase, filter]);

  const loadMore = useCallback(() => {
    if (cursor === null || loadingAssets) return;
    const request = ++pageRequest.current;
    setLoadingAssets(true);
    libraryApi
      .assets({ ...filter, cursor })
      .then((page) => {
        if (request !== pageRequest.current) return;
        setAssets((prev) => [...prev, ...page.assets]);
        setCursor(page.nextCursor);
      })
      .catch(() => setMessage("Could not load more items."))
      .finally(() => {
        if (request === pageRequest.current) setLoadingAssets(false);
      });
  }, [cursor, filter, loadingAssets]);

  const refresh = useCallback(() => {
    setPhase("loading");
    libraryApi
      .refresh()
      .catch(() => undefined)
      .finally(() => setReloadKey((k) => k + 1));
  }, []);

  const value = useMemo<LibraryState>(
    () => ({
      phase,
      message,
      summary,
      structure,
      filter,
      assets,
      total,
      hasMore: cursor !== null,
      loadingAssets,
      selected,
      setFilter: (next) => setFilterState((f) => ({ ...f, ...next })),
      scopeTo: (scope) => setFilterState((f) => ({ q: f.q, ...scope })),
      loadMore,
      select: setSelected,
      refresh,
    }),
    [
      phase,
      message,
      summary,
      structure,
      filter,
      assets,
      total,
      cursor,
      loadingAssets,
      selected,
      loadMore,
      refresh,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
