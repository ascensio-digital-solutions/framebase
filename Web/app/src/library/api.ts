import type {
  ImageVariant,
  LibraryAction,
  LibraryActionResult,
  LibraryAssetPage,
  LibraryStructure,
  LibrarySummary,
} from "@framebase/web-contracts";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    /** A message from the server that is safe to show to the user. */
    readonly detail?: string,
  ) {
    super(`${code} (HTTP ${status})`);
  }
}

async function failure(res: Response, fallback: string): Promise<ApiError> {
  let code = fallback;
  let detail: string | undefined;
  try {
    const body = (await res.json()) as { error?: string; message?: string };
    code = body.error ?? code;
    detail = body.message;
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, code, detail);
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal });
  if (!res.ok) throw await failure(res, "request_failed");
  return (await res.json()) as T;
}

export interface AssetQuery {
  folderId?: string;
  albumId?: string;
  tagId?: string;
  q?: string;
  /** Show items in Trash instead of the live library. */
  trashed?: boolean;
  cursor?: string | null;
}

/** An edit without its idempotency key: the client adds one per user action. */
export type Edit = LibraryAction extends infer A
  ? A extends { operationId: string }
    ? Omit<A, "operationId">
    : never
  : never;

export const imageUrl = (assetId: string, variant: ImageVariant) =>
  `/v1/library/assets/${encodeURIComponent(assetId)}/image?variant=${variant}`;

export const libraryApi = {
  config: (signal?: AbortSignal) =>
    getJson<{ library?: { writes?: boolean } }>("/v1/config", signal),
  summary: (signal?: AbortSignal) => getJson<LibrarySummary>("/v1/library/summary", signal),
  structure: (signal?: AbortSignal) => getJson<LibraryStructure>("/v1/library/structure", signal),
  assets: (query: AssetQuery, signal?: AbortSignal) => {
    const params = new URLSearchParams({ limit: "120" });
    for (const [key, value] of Object.entries(query)) if (value) params.set(key, String(value));
    return getJson<LibraryAssetPage>(`/v1/library/assets?${params}`, signal);
  },
  async refresh(): Promise<LibrarySummary> {
    const res = await fetch("/v1/library/refresh", { method: "POST" });
    if (!res.ok) throw new ApiError(res.status, "refresh_failed");
    return (await res.json()) as LibrarySummary;
  },
  /** Applies one edit. `operationId` makes a retry of the same user action safe. */
  async act(edit: Edit, operationId = crypto.randomUUID()): Promise<LibraryActionResult> {
    const res = await fetch("/v1/library/actions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...edit, operationId }),
    });
    if (!res.ok) throw await failure(res, "edit_failed");
    return (await res.json()) as LibraryActionResult;
  },
};
