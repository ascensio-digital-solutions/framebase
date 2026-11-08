import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { createApp } from "./app";
import { loadEnv } from "./env";

const operationId = "7b0f3c1e-2d54-4b6a-9d6e-0c1f2a3b4c5d";
const post = (app: ReturnType<typeof createApp>, body: unknown) =>
  app.request("/v1/commands", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

describe("loadEnv", () => {
  it("treats blank values as unset and applies defaults", () => {
    const env = loadEnv({ OPENROUTER_API_KEY: "", FRAMEBASE_CLOUD_API_URL: "" });
    expect(env.PORT).toBe(8788);
    expect(env.OPENROUTER_API_KEY).toBeUndefined();
    expect(env.FRAMEBASE_CLOUD_API_URL).toBeUndefined();
  });
});

describe("web API", () => {
  it("reports health", async () => {
    const res = await createApp(loadEnv({})).request("/healthz");
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ status: "ok", service: "framebase-web" });
  });

  it("reports configured providers without leaking values", async () => {
    const app = createApp(
      loadEnv({ OPENROUTER_API_KEY: "sk-secret-value", DATABASE_URL: "postgres://x" }),
    );
    const res = await app.request("/v1/config");
    const text = await res.text();
    expect(JSON.parse(text)).toEqual({
      providers: { openrouter: true, cloudCatalog: false, database: true },
      library: { writes: false }, // editing is off unless explicitly enabled and a library is connected
    });
    expect(text).not.toContain("sk-secret-value");
  });

  it("rejects malformed JSON and invalid envelopes", async () => {
    const app = createApp(loadEnv({}));
    const bad = await app.request("/v1/commands", { method: "POST", body: "{nope" });
    expect(bad.status).toBe(400);

    const invalid = await post(app, {
      operationId,
      libraryId: "lib-1",
      actor: "user",
      command: { name: "assets.move", args: { assetIds: ["a1"], folderId: "f1" } },
    });
    expect(invalid.status).toBe(400);
    expect(await invalid.json()).toMatchObject({ error: "invalid_command" });
  });

  it("acknowledges a valid envelope as not implemented", async () => {
    const res = await post(createApp(loadEnv({})), {
      operationId,
      libraryId: "lib-1",
      actor: "create-agent",
      command: { name: "knowledge.search", args: { query: "lace", scope: "technical" } },
    });
    expect(res.status).toBe(501);
    expect(await res.json()).toEqual({
      error: "not_implemented",
      operationId,
      command: "knowledge.search",
    });
  });

  it("returns JSON 404 for unknown API routes", async () => {
    const res = await createApp(loadEnv({})).request("/v1/nope");
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ error: "not_found" });
  });
});

describe("static hosting", () => {
  it("serves assets and falls back to index.html for app routes", async () => {
    const dir = mkdtempSync(join(tmpdir(), "framebase-static-"));
    writeFileSync(join(dir, "index.html"), "<!doctype html><title>Framebase</title>");
    writeFileSync(join(dir, "app.js"), "console.log(1)");
    const app = createApp(loadEnv({ STATIC_DIR: dir }));

    expect((await app.request("/app.js")).status).toBe(200);
    const route = await app.request("/library/board/1");
    expect(route.status).toBe(200);
    expect(await route.text()).toContain("<title>Framebase</title>");
    expect((await app.request("/v1/nope")).status).toBe(404);
  });
});
