import { Hono } from "hono";
import {
  imageVariantSchema,
  libraryActionSchema,
  type LibraryActionResult,
} from "@framebase/web-contracts";
import { ActionError, applyAction } from "./actions";
import { CatalogStore } from "./cloud/catalogIndex";
import { CloudApiError, type CloudClient } from "./cloud/client";
import type { Env } from "./env";

const ID = /^[A-Za-z0-9_-]{1,128}$/;

const idParam = (value: string | undefined) => (value && ID.test(value) ? value : undefined);

/**
 * Read-only library API: catalog structure, paged asset lists and image derivatives, all fetched
 * server-side from the Framebase Cloudflare API.
 */
export function createLibraryRoutes(
  env: Env,
  cloud: CloudClient | undefined,
  options: { warmUp?: boolean } = {},
) {
  const app = new Hono();
  const store = cloud ? new CatalogStore({ load: () => cloud.fetchCatalog() }) : undefined;
  const recentEdits = new Map<string, LibraryActionResult>();

  // The first catalog load reads every table once per page and can take a minute on a large library,
  // so start it at boot instead of making the first visitor wait. Skipped where access is not allowed.
  const allowed = env.NODE_ENV !== "production" || env.LIBRARY_ACCESS_PROTECTED;
  if (options.warmUp && store && allowed) {
    const started = Date.now();
    store
      .get()
      .then((index) => {
        const s = index.summary();
        console.log(
          `catalog ready: ${s.assetCount} assets, ${s.folderCount} folders in ${Date.now() - started} ms`,
        );
      })
      .catch((error: unknown) =>
        console.error(
          `catalog warm-up failed (${error instanceof CloudApiError ? `${error.code}, HTTP ${error.status}` : "unexpected error"}); it will retry on first request`,
        ),
      );
  }

  // These routes serve private media and have no sign-in of their own.
  app.use("*", async (c, next) => {
    if (!cloud || !store) {
      return c.json(
        {
          error: "cloud_not_configured",
          message: "Set FRAMEBASE_CLOUD_API_URL and FRAMEBASE_CLOUD_PAIRING_SECRET.",
        },
        503,
      );
    }
    if (env.NODE_ENV === "production" && !env.LIBRARY_ACCESS_PROTECTED) {
      return c.json(
        {
          error: "library_access_unprotected",
          message:
            "Put authentication (Cloudflare Access or Entra) in front of this server, then set LIBRARY_ACCESS_PROTECTED=true.",
        },
        503,
      );
    }
    await next();
  });

  app.onError((error, c) => {
    if (error instanceof CloudApiError) {
      console.error(`cloud api: ${error.code} (HTTP ${error.status})`);
      return c.json({ error: "cloud_unavailable", code: error.code }, 502);
    }
    console.error(
      "library route failed:",
      error instanceof Error ? error.message : "unknown error",
    );
    return c.json({ error: "cloud_unavailable" }, 502);
  });

  const index = () => (store as CatalogStore).get();

  app.get("/summary", async (c) => c.json((await index()).summary()));
  app.get("/structure", async (c) => c.json((await index()).structure()));

  app.post("/refresh", async (c) => c.json((await (store as CatalogStore).refresh()).summary()));

  app.get("/assets", async (c) => {
    const q = c.req.query();
    const cursor = q.cursor === undefined ? 0 : Number(q.cursor);
    const limit = q.limit === undefined ? undefined : Number(q.limit);
    if (
      !Number.isInteger(cursor) ||
      cursor < 0 ||
      (limit !== undefined && !Number.isInteger(limit))
    ) {
      return c.json({ error: "invalid_query" }, 400);
    }
    const ids = {
      folderId: idParam(q.folderId),
      albumId: idParam(q.albumId),
      tagId: idParam(q.tagId),
    };
    for (const [key, raw] of [
      ["folderId", q.folderId],
      ["albumId", q.albumId],
      ["tagId", q.tagId],
    ] as const) {
      if (raw !== undefined && !ids[key]) return c.json({ error: "invalid_query" }, 400);
    }
    return c.json(
      (await index()).query({
        ...ids,
        q: q.q?.slice(0, 200),
        trashed: q.trashed === "true",
        cursor,
        limit,
      }),
    );
  });

  /**
   * Edits (rename, favorite, rating, tags, move, Trash, restore). Disabled unless LIBRARY_WRITES_ENABLED.
   * The browser session cookie makes this a CSRF target, so only same-origin JSON requests are accepted.
   * There is deliberately no permanent-delete action: Trash is restorable for 30 days.
   */
  app.post("/actions", async (c) => {
    if (!env.LIBRARY_WRITES_ENABLED) {
      return c.json(
        { error: "writes_disabled", message: "Editing is turned off on this server." },
        403,
      );
    }
    if (!c.req.header("content-type")?.toLowerCase().startsWith("application/json")) {
      return c.json({ error: "unsupported_media_type" }, 415);
    }
    const site = c.req.header("sec-fetch-site");
    const origin = c.req.header("origin");
    const host = c.req.header("x-forwarded-host") ?? c.req.header("host");
    let sameOrigin = site ? site === "same-origin" : true;
    if (origin) {
      try {
        sameOrigin = sameOrigin && new URL(origin).host === host;
      } catch {
        sameOrigin = false;
      }
    }
    if (!sameOrigin) return c.json({ error: "cross_origin_request_refused" }, 403);

    let body: unknown;
    try {
      body = await c.req.json();
    } catch {
      return c.json({ error: "invalid_json" }, 400);
    }
    const parsed = libraryActionSchema.safeParse(body);
    if (!parsed.success) {
      return c.json(
        {
          error: "invalid_action",
          issues: parsed.error.issues.map((i) => ({ path: i.path.join("."), message: i.message })),
        },
        400,
      );
    }

    const user = c.req.header("x-ms-client-principal-name") ?? "unknown user";
    try {
      // A retry of an edit that already succeeded (the browser lost the answer) replays the stored result.
      const already = recentEdits.get(parsed.data.operationId);
      if (already) return c.json(already);
      const result = await applyAction(cloud as CloudClient, await index(), parsed.data);
      recentEdits.set(parsed.data.operationId, result);
      if (recentEdits.size > 200) recentEdits.delete(recentEdits.keys().next().value as string);
      console.log(`edit: ${parsed.data.action} by ${user}, ${result.assets.length} item(s)`);
      (store as CatalogStore).refreshSoon(); // converge on the Worker's state (memberships, counts)
      return c.json(result);
    } catch (error) {
      if (error instanceof ActionError)
        return c.json({ error: error.code, message: error.message }, error.status);
      if (error instanceof CloudApiError) {
        console.error(
          `edit failed: ${parsed.data.action} by ${user}: ${error.code} (HTTP ${error.status})`,
        );
        if (error.status === 409) {
          (store as CatalogStore).refreshSoon(1_000);
          return c.json(
            {
              error: "stale",
              message: "This item changed elsewhere. Reloading; please try again.",
            },
            409,
          );
        }
        if (error.status === 403) {
          return c.json(
            { error: "writes_not_permitted", message: "This server may not edit the library." },
            403,
          );
        }
        if (error.status === 400 || error.status === 422) {
          return c.json(
            { error: "rejected", code: error.code, message: "The library refused this edit." },
            422,
          );
        }
      }
      throw error; // everything else is an outage: the shared handler answers 502
    }
  });

  app.get("/assets/:id", async (c) => {
    const asset = (await index()).get(c.req.param("id"));
    return asset ? c.json(asset) : c.json({ error: "not_found" }, 404);
  });

  // Only assets present in the catalog snapshot are proxied, and only the three browse variants.
  app.get("/assets/:id/image", async (c) => {
    const variant = imageVariantSchema.safeParse(c.req.query("variant") ?? "grid-256");
    if (!variant.success) return c.json({ error: "invalid_variant" }, 400);
    const id = c.req.param("id");
    if (!(await index()).get(id)) return c.json({ error: "not_found" }, 404);

    const upstream = await (cloud as CloudClient).fetchVariant(id, variant.data);
    if (!upstream.ok || !upstream.body) {
      await upstream.body?.cancel();
      // 404 = original missing in storage, 422 = too large / cannot transform. Everything else is an outage.
      const status = upstream.status === 404 || upstream.status === 422 ? upstream.status : 502;
      return c.json({ error: status === 502 ? "cloud_unavailable" : "image_unavailable" }, status);
    }
    return new Response(upstream.body, {
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "image/webp",
        "cache-control": "private, max-age=86400",
      },
    });
  });

  return app;
}
