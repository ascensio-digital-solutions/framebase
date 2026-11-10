import { describe, expect, it } from "vitest";
import { libraryAssetPageSchema, libraryStructureSchema } from "@framebase/web-contracts";
import { createApp } from "./app";
import { CloudClient } from "./cloud/client";
import { loadEnv } from "./env";
import { BASE_URL, PAIRING_SECRET, createFakeCloud, sampleEntities } from "./testing/fakeCloud";

function setup() {
  const cloud = createFakeCloud({ entities: sampleEntities() });
  const client = new CloudClient({
    baseUrl: BASE_URL,
    pairingSecret: PAIRING_SECRET,
    deviceId: "framebase-web-test",
    fetchImpl: cloud.fetch,
    scopes: ["library.read", "assets.metadata.write", "assets.organize", "trash.write"],
  });
  const app = createApp(loadEnv({ LIBRARY_WRITES_ENABLED: "true" }), { cloud: client });
  const act = (body: Record<string, unknown>) =>
    app.request("/v1/library/actions", {
      method: "POST",
      headers: { "content-type": "application/json", "sec-fetch-site": "same-origin" },
      body: JSON.stringify({ operationId: crypto.randomUUID(), ...body }),
    });
  const list = async (q = "") =>
    libraryAssetPageSchema.parse(await (await app.request(`/v1/library/assets?${q}`)).json());
  const structure = async () =>
    libraryStructureSchema.parse(await (await app.request("/v1/library/structure")).json());
  return { app, cloud, act, list, structure };
}

describe("bulk metadata", () => {
  it("favorites and rates several items at once, and clears a rating with 0", async () => {
    const { act, list, cloud } = setup();
    expect(
      (await act({ action: "favorite", assetIds: ["a1", "a2", "a3"], favorite: true })).status,
    ).toBe(200);
    expect((await act({ action: "rating", assetIds: ["a1", "a2"], rating: 4 })).status).toBe(200);
    const all = (await list()).assets;
    expect(
      all
        .filter((a) => a.favorite)
        .map((a) => a.id)
        .sort(),
    ).toEqual(["a1", "a2", "a3"]);
    expect(all.find((a) => a.id === "a1")?.rating).toBe(4);
    expect(all.find((a) => a.id === "a3")?.rating).toBe(0);
    expect((await act({ action: "rating", assetIds: ["a1"], rating: 0 })).status).toBe(200);
    expect((await list("q=mono")).assets[0]?.rating).toBe(0);
    expect(cloud.state.mutations.filter((m) => m === "update_favorite")).toHaveLength(3);
  });
});

describe("albums", () => {
  it("creates an album, adds and removes photos, renames it, and deleting it keeps the photos", async () => {
    const { act, list, structure } = setup();
    const created = await act({ action: "createAlbum", name: "Spring shoot" });
    expect(created.status).toBe(200);
    const album = ((await created.json()) as { album: { id: string } }).album;

    expect(
      (await act({ action: "albumAdd", albumId: album.id, assetIds: ["a2", "a3", "a4"] })).status,
    ).toBe(200);
    expect((await list(`albumId=${album.id}`)).assets.map((a) => a.id).sort()).toEqual([
      "a2",
      "a3",
      "a4",
    ]);
    expect((await act({ action: "albumRemove", albumId: album.id, assetIds: ["a3"] })).status).toBe(
      200,
    );
    expect((await list(`albumId=${album.id}`)).total).toBe(2);

    expect(
      (await act({ action: "renameAlbum", albumId: album.id, name: "Spring 2026" })).status,
    ).toBe(200);
    expect((await structure()).albums.map((a) => a.name)).toContain("Spring 2026");

    const before = (await list()).total;
    expect((await act({ action: "deleteAlbum", albumId: album.id })).status).toBe(200);
    expect((await structure()).albums.map((a) => a.id)).not.toContain(album.id);
    expect((await list()).total).toBe(before); // no photo was touched
  });

  it("will not add missing or trashed photos, or use a missing album", async () => {
    const { act, cloud } = setup();
    expect((await act({ action: "albumAdd", albumId: "al1", assetIds: ["nope"] })).status).toBe(
      404,
    );
    expect((await act({ action: "albumAdd", albumId: "al1", assetIds: ["a5"] })).status).toBe(404); // a5 is in Trash
    expect((await act({ action: "albumAdd", albumId: "missing", assetIds: ["a1"] })).status).toBe(
      404,
    );
    expect(cloud.state.mutations).toEqual([]);
  });

  it("rejects an album edit made on a stale revision", async () => {
    const { act, cloud, list } = setup();
    await list();
    cloud.touch("album", "al1");
    const res = await act({ action: "renameAlbum", albumId: "al1", name: "Mine" });
    expect(res.status).toBe(409);
    expect(await res.json()).toMatchObject({ error: "stale" });
  });
});

describe("folders", () => {
  it("creates, renames and moves folders, and counts follow the photos", async () => {
    const { act, list, structure } = setup();
    const created = await act({ action: "createFolder", name: "Portraits", parentId: "f-people" });
    expect(created.status).toBe(200);
    const folder = ((await created.json()) as { folder: { id: string } }).folder;

    expect((await act({ action: "move", assetIds: ["a4"], folderId: folder.id })).status).toBe(200);
    const count = async (id: string) =>
      (await structure()).folders.find((f) => f.id === id)?.assetCount;
    expect(await count(folder.id)).toBe(1);
    expect(await count("f-people")).toBe(1); // rolls up from the subfolder

    expect(
      (await act({ action: "renameFolder", folderId: folder.id, name: "Headshots" })).status,
    ).toBe(200);
    expect((await structure()).folders.find((f) => f.id === folder.id)?.name).toBe("Headshots");

    // Moving it under 01_products moves its photos' roll-up with it.
    expect(
      (await act({ action: "moveFolder", folderId: folder.id, parentId: "f-root" })).status,
    ).toBe(200);
    expect(await count("f-root")).toBe(4); // a1 + a2 + a3 + a4
    expect(await count("f-people")).toBe(0);
    expect((await list("folderId=f-root")).total).toBe(4);
  });

  it("refuses to move a folder into itself or one of its own subfolders", async () => {
    const { act, cloud } = setup();
    for (const parentId of ["f-sub", "f-root"]) {
      const res = await act({ action: "moveFolder", folderId: "f-root", parentId });
      expect(res.status).toBe(400);
      expect(await res.json()).toMatchObject({ error: "invalid_folder" });
    }
    expect(cloud.state.mutations).toEqual([]);
  });

  it("refuses a missing parent and rejects a stale folder edit", async () => {
    const { act, cloud, list } = setup();
    expect(
      (await act({ action: "createFolder", name: "Orphan", parentId: "f-missing" })).status,
    ).toBe(404);
    await list();
    cloud.touch("folder", "f-sub");
    expect((await act({ action: "renameFolder", folderId: "f-sub", name: "Renamed" })).status).toBe(
      409,
    );
  });

  it("offers no folder delete", async () => {
    const { act } = setup();
    for (const action of ["deleteFolder", "removeFolder"]) {
      expect((await act({ action, folderId: "f-sub" })).status).toBe(400);
    }
  });
});
