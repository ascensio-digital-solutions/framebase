import { describe, expect, it } from "vitest";
import { libraryAssetPageSchema } from "@framebase/web-contracts";
import { createApp } from "./app";
import { CloudClient } from "./cloud/client";
import { loadEnv } from "./env";
import { BASE_URL, PAIRING_SECRET, createFakeCloud, sampleEntities } from "./testing/fakeCloud";

/** A second library with different photos, so mixing them up would be visible. */
function personalEntities() {
  const base = sampleEntities();
  return base.map((e) =>
    e.entityType === "asset" && (e.payload as { id: string }).id === "a1"
      ? { ...e, payload: { ...e.payload, displayName: "Beach holiday" } }
      : e,
  );
}

function setup() {
  const mk = (entities: ReturnType<typeof sampleEntities>) => {
    const cloud = createFakeCloud({ entities });
    return {
      cloud,
      client: new CloudClient({
        baseUrl: BASE_URL,
        pairingSecret: PAIRING_SECRET,
        deviceId: "framebase-web-test",
        fetchImpl: cloud.fetch,
        scopes: ["library.read", "assets.metadata.write", "assets.organize", "trash.write"],
      }),
    };
  };
  const hsc = mk(sampleEntities());
  const personal = mk(personalEntities());
  const app = createApp(loadEnv({ LIBRARY_WRITES_ENABLED: "true" }), {
    libraries: [
      { id: "hsc", label: "HSC Library", cloud: hsc.client },
      { id: "personal", label: "Personal Library", cloud: personal.client },
    ],
  });
  return { app, hsc, personal };
}

const names = async (app: ReturnType<typeof setup>["app"], path: string) =>
  libraryAssetPageSchema
    .parse(await (await app.request(path)).json())
    .assets.map((a) => a.displayName);

describe("several libraries", () => {
  it("lists the libraries without revealing any credential", async () => {
    const { app } = setup();
    const body = await (await app.request("/v1/config")).json();
    expect(body).toMatchObject({
      libraries: [
        { id: "hsc", label: "HSC Library" },
        { id: "personal", label: "Personal Library" },
      ],
    });
    expect(JSON.stringify(body)).not.toContain(PAIRING_SECRET);
  });

  it("keeps each library's catalog separate", async () => {
    const { app } = setup();
    expect(await names(app, "/v1/libraries/hsc/assets?q=mono")).toEqual(["Mono Mesh Front"]);
    expect(await names(app, "/v1/libraries/personal/assets?q=mono")).toEqual([]);
    expect(await names(app, "/v1/libraries/personal/assets?q=beach")).toEqual(["Beach holiday"]);
    expect(await names(app, "/v1/libraries/hsc/assets?q=beach")).toEqual([]);
  });

  it("treats the first library as the default for the original routes", async () => {
    const { app } = setup();
    expect(await names(app, "/v1/library/assets?q=mono")).toEqual(["Mono Mesh Front"]);
  });

  it("never applies an edit made in one library to the other", async () => {
    const { app, hsc, personal } = setup();
    const res = await app.request("/v1/libraries/personal/actions", {
      method: "POST",
      headers: { "content-type": "application/json", "sec-fetch-site": "same-origin" },
      body: JSON.stringify({
        operationId: crypto.randomUUID(),
        action: "favorite",
        assetId: "a1",
        favorite: true,
      }),
    });
    expect(res.status).toBe(200);
    expect(personal.cloud.state.mutations).toEqual(["update_favorite"]);
    expect(hsc.cloud.state.mutations).toEqual([]);
    // The same asset id in the other library is untouched.
    const other = await (await app.request("/v1/libraries/hsc/assets/a1")).json();
    expect(other).toMatchObject({ favorite: false });
  });

  it("answers 404 for a library that does not exist", async () => {
    const { app } = setup();
    expect((await app.request("/v1/libraries/nope/summary")).status).toBe(404);
  });
});
