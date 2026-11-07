import type {
  ImageVariant,
  LibraryAssetPage,
  LibraryStructure,
  LibrarySummary,
} from "@framebase/web-contracts";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(`${code} (HTTP ${status})`);
  }
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal });
  if (!res.ok) {
    let code = "request_failed";
    try {
      code = ((await res.json()) as { error?: string }).error ?? code;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code);
  }
  return (await res.json()) as T;
}

export interface AssetQuery {
  folderId?: string;
  albumId?: string;
  tagId?: string;
  q?: string;
  cursor?: string | null;
}

export const imageUrl = (assetId: string, variant: ImageVariant) =>
  `/v1/library/assets/${encodeURIComponent(assetId)}/image?variant=${variant}`;

export const libraryApi = {
  summary: (signal?: AbortSignal) => getJson<LibrarySummary>("/v1/library/summary", signal),
  structure: (signal?: AbortSignal) => getJson<LibraryStructure>("/v1/library/structure", signal),
  assets: (query: AssetQuery, signal?: AbortSignal) => {
    const params = new URLSearchParams({ limit: "120" });
    for (const [key, value] of Object.entries(query)) if (value) params.set(key, value);
    return getJson<LibraryAssetPage>(`/v1/library/assets?${params}`, signal);
  },
  async refresh(): Promise<LibrarySummary> {
    const res = await fetch("/v1/library/refresh", { method: "POST" });
    if (!res.ok) throw new ApiError(res.status, "refresh_failed");
    return (await res.json()) as LibrarySummary;
  },
};
