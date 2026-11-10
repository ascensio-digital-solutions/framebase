import { describe, expect, it } from "vitest";
import { libraryAssetPageSchema, libraryStructureSchema } from "@framebase/web-contracts";
import { createApp } from "./app";
import { CloudClient } from "./cloud/client";
import { loadEnv } from "./env";
import { BASE_URL, PAIRING_SECRET, createFakeCloud, sampleEntities } from "./testing/fakeCloud";

const uuid = () => crypto.randomUUID();

function setup(
  env: Record<string, string> = { LIBRARY_WRITES_ENABLED: "true" },
  entities = sampleEntities(),
) {
  const cloud = createFakeCloud({ entities });
  const e = loadEnv(env);
  const client = new CloudClient({
    baseUrl: BASE_URL,
    pairingSecret: PAIRING_SECRET,
    deviceId: "framebase-web-test",
    fetchImpl: cloud.fetch,
    scopes: e.LIBRARY_WRITES_ENABLED
      ? ["library.read", "assets.metadata.write", "assets.organize", "trash.write"]
      : ["library.read"],
  });
  const app = createApp(e, { cloud: client });
  const act = (body: Record<string, unknown>, headers: Record<string, string> = {}) =>
    app.request("/v1/library/actions", {
      method: "POST",
      headers: { "content-type": "application/json", "sec-fetch-site": "same-origin", ...headers },
      body: JSON.stringify({ operationId: uuid(), ...body }),
    });
  const list = async (query = "") =>
    libraryAssetPageSchema.parse(await (await app.request(`/v1/library/assets?${query}`)).json());
  const structure = async () =>
    libraryStructureSchema.parse(await (await app.request("/v1/library/structure")).json());
  return { app, cloud, act, list, structure };
}

describe("editing: safety gates", () => {
  it("is off by default and never asks the Worker for write scopes", async () => {
    const { act, cloud, list } = setup({});
    const res = await act({ action: "favorite", assetIds: ["a1"], favorite: true });
    expect(res.status).toBe(403);
    expect(await res.json()).toMatchObject({ error: "writes_disabled" });
    await list(); // forces enrollment
    expect(cloud.state.enrolledScopes).toEqual([["library.read"]]);
  });

  it("requests exactly the write scopes it needs when enabled, and never a purge scope", async () => {
    const { act, cloud } = setup();
    await act({ action: "favorite", assetIds: ["a1"], favorite: true });
    expect(cloud.state.enrolledScopes[0]).toEqual([
      "library.read",
      "assets.metadata.write",
      "assets.organize",
      "trash.write",
    ]);
    expect(cloud.state.enrolledScopes.flat().some((s) => s.includes("purge"))).toBe(false);
  });

  it("refuses cross-site, non-JSON and malformed requests", async () => {
    const { act, app, cloud } = setup();
    expect(
      (
        await act(
          { action: "favorite", assetIds: ["a1"], favorite: true },
          { "sec-fetch-site": "cross-site" },
        )
      ).status,
    ).toBe(403);
    expect(
      (
        await act(
          { action: "favorite", assetIds: ["a1"], favorite: true },
          { origin: "https://evil.example", host: "app.example" },
        )
      ).status,
    ).toBe(403);
    const text = await app.request("/v1/library/actions", {
      method: "POST",
      headers: { "content-type": "text/plain" },
      body: "{}",
    });
    expect(text.status).toBe(415);
    expect((await act({ action: "purge", assetIds: ["a1"] })).status).toBe(400); // no such action
    expect((await act({ action: "rating", assetIds: ["a1"], rating: 9 })).status).toBe(400);
    expect((await act({ action: "createTag", name: "Not A Tag" })).status).toBe(400);
    expect(cloud.state.mutations).toEqual([]);
  });

  it("accepts a same-origin browser request", async () => {
    const { act } = setup();
    const res = await act(
      { action: "favorite", assetIds: ["a1"], favorite: true },
      { origin: "https://app.example", host: "app.example" },
    );
    expect(res.status).toBe(200);
  });
});

describe("editing: metadata", () => {
  it("renames, favorites and rates, sending the current revision each time", async () => {
    const { act, list, cloud } = setup();
    const first = await act({ action: "rename", assetId: "a1", displayName: "  Aaa First  " });
    expect(first.status).toBe(200);
    expect((await list("q=aaa")).assets[0]).toMatchObject({
      id: "a1",
      displayName: "Aaa First",
      revision: 2,
    });
    // A second edit uses the new revision, so it is accepted rather than rejected as stale.
    expect((await act({ action: "favorite", assetIds: ["a1"], favorite: true })).status).toBe(200);
    expect((await act({ action: "rating", assetIds: ["a1"], rating: 4 })).status).toBe(200);
    const asset = (await list("q=aaa")).assets[0];
    expect(asset).toMatchObject({ favorite: true, rating: 4, revision: 4 });
    expect(cloud.state.mutations).toEqual(["rename_asset", "update_favorite", "update_rating"]);
  });

  it("rejects an edit when the item changed elsewhere, and does not apply it", async () => {
    const { act, cloud, list } = setup();
    await list(); // load the snapshot
    cloud.touch("asset", "a1"); // someone else edited a1
    const res = await act({ action: "rename", assetId: "a1", displayName: "Mine" });
    expect(res.status).toBe(409);
    expect(await res.json()).toMatchObject({ error: "stale" });
    expect(cloud.state.mutations).toEqual([]);
  });

  it("will not edit an unknown or trashed item", async () => {
    const { act } = setup();
    expect((await act({ action: "rename", assetId: "nope", displayName: "x" })).status).toBe(404);
    expect((await act({ action: "rename", assetId: "a5", displayName: "x" })).status).toBe(404); // a5 is in Trash
  });
});

describe("editing: organization", () => {
  it("moves items and keeps folder counts right", async () => {
    const { act, structure, list } = setup();
    const res = await act({ action: "move", assetIds: ["a2", "a3"], folderId: "f-people" });
    expect(res.status).toBe(200);
    const count = async (id: string) =>
      (await structure()).folders.find((f) => f.id === id)?.assetCount;
    expect(await count("f-people")).toBe(3); // a4 + a2 + a3
    expect(await count("f-sub")).toBe(0);
    expect((await list("folderId=f-people")).total).toBe(3);
  });

  it("refuses to move into a folder that does not exist", async () => {
    const { act, cloud } = setup();
    const res = await act({ action: "move", assetIds: ["a1"], folderId: "f-missing" });
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchObject({ error: "invalid_folder" });
    expect(cloud.state.mutations).toEqual([]);
  });

  it("creates a tag, then adds and removes it", async () => {
    const { act, list } = setup();
    const created = await act({ action: "createTag", name: "status:approved" });
    expect(created.status).toBe(200);
    const tag = ((await created.json()) as { tag: { id: string; name: string } }).tag;
    expect(tag.name).toBe("status:approved");

    expect(
      (await act({ action: "tag", assetIds: ["a1", "a4"], tagId: tag.id, mode: "add" })).status,
    ).toBe(200);
    expect((await list("tagId=" + tag.id)).total).toBe(2);
    expect((await list("q=mono")).assets[0]?.tags).toContain("status:approved");

    expect(
      (await act({ action: "tag", assetIds: ["a4"], tagId: tag.id, mode: "remove" })).status,
    ).toBe(200);
    expect((await list("tagId=" + tag.id)).assets.map((a) => a.id)).toEqual(["a1"]);
  });
});

describe("editing: Trash (reversible delete)", () => {
  it("moves items to Trash, lists them there, and restores them to their old folder", async () => {
    const { act, list, structure } = setup();
    const trashed = await act({ action: "trash", assetIds: ["a2"] });
    expect(trashed.status).toBe(200);

    expect((await list("folderId=f-sub")).assets.map((a) => a.id)).toEqual(["a3"]); // gone from the library
    const inTrash = await list("trashed=true");
    expect(inTrash.assets.map((a) => a.id).sort()).toEqual(["a2", "a5"]); // a5 was already there
    expect(inTrash.assets.find((a) => a.id === "a2")?.scheduledPurgeAt).toBeTruthy();
    expect(
      await (await act({ action: "rename", assetId: "a2", displayName: "x" })).json(),
    ).toMatchObject({ error: "not_found" });

    const restored = await act({ action: "restore", assetIds: ["a2"] });
    expect(restored.status).toBe(200);
    expect((await list("folderId=f-sub")).assets.map((a) => a.id).sort()).toEqual(["a2", "a3"]);
    expect((await list("trashed=true")).assets.map((a) => a.id)).toEqual(["a5"]);
    expect((await structure()).folders.find((f) => f.id === "f-sub")?.assetCount).toBe(2);
  });

  it("will not trash something already in Trash, nor restore something that is not", async () => {
    const { act } = setup();
    expect((await act({ action: "trash", assetIds: ["a5"] })).status).toBe(404);
    expect((await act({ action: "restore", assetIds: ["a1"] })).status).toBe(404);
  });

  it("offers no permanent delete anywhere", async () => {
    const { act, app } = setup();
    for (const action of ["delete", "purge", "emptyTrash", "destroy"]) {
      expect((await act({ action, assetIds: ["a5"] })).status).toBe(400);
    }
    expect((await app.request("/v1/library/assets/a5", { method: "DELETE" })).status).toBe(404);
  });
});

describe("editing: reliability", () => {
  it("applies a retried edit once", async () => {
    const { app, cloud } = setup();
    const body = JSON.stringify({
      operationId: uuid(),
      action: "favorite",
      assetIds: ["a1"],
      favorite: true,
    });
    const send = () =>
      app.request("/v1/library/actions", {
        method: "POST",
        headers: { "content-type": "application/json", "sec-fetch-site": "same-origin" },
        body,
      });
    const first = await send();
    const retry = await send(); // the browser never saw the first answer
    expect(first.status).toBe(200);
    expect(retry.status).toBe(200);
    expect(await retry.json()).toEqual(await first.json());
    expect(cloud.state.mutations).toEqual(["update_favorite"]);
  });

  it("splits large batches to the Worker's 25-operation limit with stable keys", async () => {
    const many = [
      ...sampleEntities(),
      ...Array.from({ length: 30 }, (_, i) => ({
        entityType: "asset",
        entityId: `bulk-${i}`,
        revision: 1,
        payload: {
          id: `bulk-${i}`,
          displayName: `Bulk ${i}`,
          folderId: "f-root",
          favorite: false,
          rating: 0,
          blob: { byteSize: 100, mediaType: "image/jpeg" },
          createdAt: "2026-01-01T00:00:00Z",
          trash: null,
        },
      })),
    ];
    const { act, cloud, list } = setup({ LIBRARY_WRITES_ENABLED: "true" }, many);
    const opId = uuid();
    const res = await act({
      operationId: opId,
      action: "trash",
      assetIds: Array.from({ length: 30 }, (_, i) => `bulk-${i}`),
    });
    expect(res.status).toBe(200);
    expect(cloud.state.mutationKeys).toEqual([`${opId}-0`, `${opId}-1`]);
    expect(cloud.state.mutations).toHaveLength(30);
    expect((await list("trashed=true")).total).toBe(31); // 30 + the one already there
  });

  it("answers 403 when the Worker refuses the scope, without crashing", async () => {
    const cloud = createFakeCloud();
    const client = new CloudClient({
      baseUrl: BASE_URL,
      pairingSecret: PAIRING_SECRET,
      deviceId: "framebase-web-test",
      fetchImpl: cloud.fetch,
      scopes: ["library.read"], // writes enabled in the app but the device was only granted read
    });
    const app = createApp(loadEnv({ LIBRARY_WRITES_ENABLED: "true" }), { cloud: client });
    const res = await app.request("/v1/library/actions", {
      method: "POST",
      headers: { "content-type": "application/json", "sec-fetch-site": "same-origin" },
      body: JSON.stringify({
        operationId: uuid(),
        action: "favorite",
        assetIds: ["a1"],
        favorite: true,
      }),
    });
    expect(res.status).toBe(403);
    expect(await res.json()).toMatchObject({ error: "writes_not_permitted" });
  });
});
