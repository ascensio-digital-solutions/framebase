import { Hono } from "hono";
import { imageVariantSchema } from "@framebase/web-contracts";
import { CatalogStore } from "./cloud/catalogIndex";
import { CloudApiError, type CloudClient } from "./cloud/client";
import type { Env } from "./env";

const ID = /^[A-Za-z0-9_-]{1,128}$/;

const idParam = (value: string | undefined) => (value && ID.test(value) ? value : undefined);

/**
 * Read-only library API: catalog structure, paged asset lists and image derivatives, all fetched
 * server-side from the Framebase Cloudflare API.
 */
export function createLibraryRoutes(env: Env, cloud: CloudClient | undefined) {
  const app = new Hono();
  const store = cloud ? new CatalogStore({ load: () => cloud.fetchCatalog() }) : undefined;

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
    return c.json((await index()).query({ ...ids, q: q.q?.slice(0, 200), cursor, limit }));
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
