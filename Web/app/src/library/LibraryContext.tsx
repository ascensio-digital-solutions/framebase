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
import type {
  LibraryActionResult,
  LibraryAsset,
  LibraryStructure,
  LibrarySummary,
} from "@framebase/web-contracts";
import { ApiError, libraryApi, type Edit } from "./api";

export interface Filter {
  folderId?: string;
  albumId?: string;
  tagId?: string;
  /** Show the Trash instead of the library. */
  trashed?: boolean;
  q: string;
}

export type Phase = "loading" | "ready" | "unconfigured" | "error";

export interface Notice {
  kind: "info" | "error";
  text: string;
  /** Reverses the edit, when it can be reversed. */
  undo?: () => void;
}

interface ActOptions {
  /** Shown after success. */
  label?: string;
  /** The edit that reverses this one, offered as an Undo button. */
  undo?: Edit;
}

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
  /** Editing is available (turned on server-side). */
  canEdit: boolean;
  editing: boolean;
  checked: ReadonlySet<string>;
  notice?: Notice;
  setFilter: (next: Partial<Filter>) => void;
  /** Replaces the whole scope: only the keys given stay set. Used when picking a folder, album or tag. */
  scopeTo: (scope: Pick<Filter, "folderId" | "albumId" | "tagId">) => void;
  showTrash: () => void;
  loadMore: () => void;
  select: (asset: LibraryAsset | undefined) => void;
  toggleChecked: (id: string) => void;
  checkAllLoaded: () => void;
  clearChecked: () => void;
  /** Applies an edit. Resolves the result on success, undefined on failure; failures are reported through `notice`. */
  act: (edit: Edit, options?: ActOptions) => Promise<LibraryActionResult | undefined>;
  dismissNotice: () => void;
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

const EDITS_THAT_STAY_IN_PLACE = new Set(["rename", "favorite", "rating"]);

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
  const [pageKey, setPageKey] = useState(0);
  const [canEdit, setCanEdit] = useState(false);
  const [editing, setEditing] = useState(false);
  const [checked, setChecked] = useState<ReadonlySet<string>>(new Set());
  const [notice, setNotice] = useState<Notice>();
  const pageRequest = useRef(0);

  useEffect(() => {
    libraryApi
      .config()
      .then((c) => setCanEdit(Boolean(c.library?.writes)))
      .catch(() => undefined);
  }, []);

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

  // The first page reloads whenever the scope, the search or an edit changes what is listed.
  useEffect(() => {
    if (phase !== "ready") return;
    const controller = new AbortController();
    const request = ++pageRequest.current;
    setLoadingAssets(true);
    libraryApi
      .assets(filter, controller.signal)
      .then((page) => {
        if (request !== pageRequest.current) return;
        setAssets(page.assets);
        setTotal(page.total);
        setCursor(page.nextCursor);
        setSelected(undefined);
        setChecked(new Set());
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
  }, [phase, filter, pageKey]);

  // Notices disappear on their own.
  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(undefined), notice.kind === "error" ? 12_000 : 9_000);
    return () => clearTimeout(id);
  }, [notice]);

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

  /** Re-reads counts and the folder tree without flashing the loading state. */
  const refreshStructure = useCallback(async () => {
    try {
      const [s, st] = await Promise.all([libraryApi.summary(), libraryApi.structure()]);
      setSummary(s);
      setStructure(st);
    } catch {
      /* keep what is shown */
    }
  }, []);

  const act = useCallback(
    async function run(
      edit: Edit,
      options: ActOptions = {},
    ): Promise<LibraryActionResult | undefined> {
      setEditing(true);
      try {
        const result = await libraryApi.act(edit);
        if (EDITS_THAT_STAY_IN_PLACE.has(edit.action)) {
          const byId = new Map(result.assets.map((a) => [a.id, a]));
          setAssets((prev) => prev.map((a) => byId.get(a.id) ?? a));
          setSelected((s) => (s ? (byId.get(s.id) ?? s) : s));
        } else {
          setPageKey((k) => k + 1); // moved, trashed, restored or retagged items may leave this view
        }
        void refreshStructure();
        const undo = options.undo;
        setNotice(
          options.label
            ? { kind: "info", text: options.label, undo: undo ? () => void run(undo) : undefined }
            : undefined,
        );
        return result;
      } catch (error) {
        if (error instanceof ApiError && error.code === "stale") setPageKey((k) => k + 1);
        setNotice({
          kind: "error",
          text:
            error instanceof ApiError && error.detail
              ? error.detail
              : "That edit could not be applied. Nothing was changed.",
        });
        return undefined;
      } finally {
        setEditing(false);
      }
    },
    [refreshStructure],
  );

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
      canEdit,
      editing,
      checked,
      notice,
      setFilter: (next) => setFilterState((f) => ({ ...f, ...next })),
      scopeTo: (scope) => setFilterState((f) => ({ q: f.q, ...scope })),
      showTrash: () => setFilterState((f) => ({ q: f.q, trashed: true })),
      loadMore,
      select: setSelected,
      toggleChecked: (id) =>
        setChecked((prev) => {
          const next = new Set(prev);
          if (!next.delete(id)) next.add(id);
          return next;
        }),
      checkAllLoaded: () => setChecked(new Set(assets.map((a) => a.id))),
      clearChecked: () => setChecked(new Set()),
      act,
      dismissNotice: () => setNotice(undefined),
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
      canEdit,
      editing,
      checked,
      notice,
      loadMore,
      act,
      refresh,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
