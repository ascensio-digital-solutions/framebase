import { describe, expect, it } from "vitest";
import {
  libraryAssetPageSchema,
  libraryStructureSchema,
  librarySummarySchema,
} from "@framebase/web-contracts";
import { createApp } from "./app";
import { CloudClient } from "./cloud/client";
import { loadEnv } from "./env";
import { BASE_URL, PAIRING_SECRET, createFakeCloud } from "./testing/fakeCloud";

function setup(env: Record<string, string> = {}, cloud = createFakeCloud()) {
  const client = new CloudClient({
    baseUrl: BASE_URL,
    pairingSecret: PAIRING_SECRET,
    deviceId: "framebase-web-test",
    fetchImpl: cloud.fetch,
  });
  return { cloud, app: createApp(loadEnv(env), { cloud: client }) };
}

describe("library routes", () => {
  it("is disabled until the cloud connection is configured", async () => {
    const res = await createApp(loadEnv({})).request("/v1/library/summary");
    expect(res.status).toBe(503);
    expect(await res.json()).toMatchObject({ error: "cloud_not_configured" });
  });

  it("stays disabled in production until an auth layer is asserted", async () => {
    const blocked = await setup({ NODE_ENV: "production" }).app.request("/v1/library/summary");
    expect(blocked.status).toBe(503);
    expect(await blocked.json()).toMatchObject({ error: "library_access_unprotected" });

    const allowed = await setup({
      NODE_ENV: "production",
      LIBRARY_ACCESS_PROTECTED: "true",
    }).app.request("/v1/library/summary");
    expect(allowed.status).toBe(200);
  });

  it("summarizes the snapshot and leaves out trashed and malformed entities", async () => {
    const res = await setup().app.request("/v1/library/summary");
    const summary = librarySummarySchema.parse(await res.json());
    expect(summary).toMatchObject({ assetCount: 4, folderCount: 3, albumCount: 1, tagCount: 2 });
    expect(summary.watermarkRevision).toBe(42);
  });

  it("rolls folder counts up the tree and orders tags by use", async () => {
    const res = await setup().app.request("/v1/library/structure");
    const s = libraryStructureSchema.parse(await res.json());
    const count = (id: string) => s.folders.find((f) => f.id === id)?.assetCount;
    expect(count("f-root")).toBe(3); // a1 + a2 + a3 (a5 is trashed)
    expect(count("f-sub")).toBe(2);
    expect(s.albums[0]).toMatchObject({ name: "Hero shots", assetCount: 2 }); // trashed a5 not counted
    expect(s.tags.map((t) => t.name)).toEqual(["state:after-hair-system", "status:review"]);
  });

  it("filters by folder (including descendants), search and tag", async () => {
    const { app } = setup();
    const page = async (query: string) =>
      libraryAssetPageSchema.parse(await (await app.request(`/v1/library/assets?${query}`)).json());

    expect((await page("folderId=f-root")).assets.map((a) => a.id).sort()).toEqual([
      "a1",
      "a2",
      "a3",
    ]);
    expect((await page("q=SWISS")).assets.map((a) => a.id)).toEqual(["a2", "a3"]); // case-insensitive, name-sorted
    expect((await page("tagId=t1")).total).toBe(3);
    const withTags = await page("folderId=f-people");
    expect(withTags.assets[0]?.tags).toEqual(["state:after-hair-system"]);
  });

  it("pages with a cursor", async () => {
    const { app } = setup();
    const first = libraryAssetPageSchema.parse(
      await (await app.request("/v1/library/assets?limit=3")).json(),
    );
    expect(first.assets).toHaveLength(3);
    expect(first.nextCursor).toBe("3");
    const second = libraryAssetPageSchema.parse(
      await (await app.request(`/v1/library/assets?limit=3&cursor=${first.nextCursor}`)).json(),
    );
    expect(second.assets).toHaveLength(1);
    expect(second.nextCursor).toBeNull();
  });

  it("rejects malformed query values", async () => {
    const { app } = setup();
    for (const q of ["cursor=-1", "cursor=abc", "folderId=../../etc", "limit=1.5"]) {
      expect((await app.request(`/v1/library/assets?${q}`)).status, q).toBe(400);
    }
  });

  describe("image proxy", () => {
    it("streams a derivative with private caching", async () => {
      const res = await setup().app.request("/v1/library/assets/a1/image?variant=grid-256");
      expect(res.status).toBe(200);
      expect(res.headers.get("content-type")).toBe("image/webp");
      expect(res.headers.get("cache-control")).toBe("private, max-age=86400");
      expect([...new Uint8Array(await res.arrayBuffer())]).toEqual([1, 2, 3]);
    });

    it("only proxies catalog assets and the browse variants", async () => {
      const { app, cloud } = setup();
      expect((await app.request("/v1/library/assets/missing/image")).status).toBe(404);
      // Trashed items still have previews so the Trash view can show what you would restore.
      expect((await app.request("/v1/library/assets/a5/image")).status).toBe(200);
      expect((await app.request("/v1/library/assets/a1/image?variant=social-story")).status).toBe(
        400,
      );
      expect(cloud.state.variantCalls).toBe(1); // only the trashed-but-known asset reached the Worker
    });

    it("maps upstream problems without exposing details", async () => {
      const { app, cloud } = setup();
      cloud.state.variantStatus = 422;
      expect((await app.request("/v1/library/assets/a1/image")).status).toBe(422);
      cloud.state.variantStatus = 500;
      const res = await app.request("/v1/library/assets/a1/image");
      expect(res.status).toBe(502);
      expect(await res.json()).toEqual({ error: "cloud_unavailable" });
    });
  });

  it("reports an unreachable or rejecting cloud as 502, never leaking the pairing secret", async () => {
    const cloud = createFakeCloud();
    const client = new CloudClient({
      baseUrl: BASE_URL,
      pairingSecret: "wrong-secret-value",
      deviceId: "framebase-web-test",
      fetchImpl: cloud.fetch,
    });
    const res = await createApp(loadEnv({}), { cloud: client }).request("/v1/library/summary");
    expect(res.status).toBe(502);
    expect(await res.text()).not.toContain("wrong-secret-value");
  });

  it("refresh is rate limited to avoid re-reading the whole catalog", async () => {
    const { app, cloud } = setup();
    await app.request("/v1/library/summary");
    const before = cloud.state.bootstrapCalls;
    await app.request("/v1/library/refresh", { method: "POST" });
    expect(cloud.state.bootstrapCalls).toBe(before); // within the minimum interval
  });
});
