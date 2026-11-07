import { webcrypto } from "node:crypto";
import type { BootstrapEntity } from "../cloud/client";

const { subtle } = webcrypto;
const fromB64url = (v: string) => new Uint8Array(Buffer.from(v, "base64url"));

export const PAIRING_SECRET = "test-pairing-secret";
export const BASE_URL = "https://framebase.test";

export function sampleEntities(): BootstrapEntity[] {
  const folder = (
    id: string,
    name: string,
    parentId: string | null,
    sortOrder = 0,
  ): BootstrapEntity => ({
    entityType: "folder",
    entityId: id,
    revision: 1,
    payload: { id, name, parentId, systemKind: null, sortOrder },
  });
  const asset = (
    id: string,
    displayName: string,
    folderId: string,
    trashed = false,
  ): BootstrapEntity => ({
    entityType: "asset",
    entityId: id,
    revision: 1,
    payload: {
      id,
      displayName,
      folderId,
      favorite: false,
      rating: 0,
      status: "active",
      blob: { sha256: id, byteSize: 2048, mediaType: "image/jpeg", originalExtension: "jpg" },
      createdAt: "2026-01-01T00:00:00Z",
      trash: trashed ? { trashedAt: "2026-02-01T00:00:00Z" } : null,
    },
  });
  return [
    folder("f-root", "01_products", null, 1),
    folder("f-sub", "swiss-lace", "f-root", 1),
    folder("f-people", "03_people", null, 2),
    asset("a1", "Mono Mesh Front", "f-root"),
    asset("a2", "Swiss Lace Closeup", "f-sub"),
    asset("a3", "swiss lace hairline", "f-sub"),
    asset("a4", "Barry Portrait", "f-people"),
    asset("a5", "Deleted Thing", "f-sub", true),
    {
      entityType: "album",
      entityId: "al1",
      revision: 1,
      payload: { id: "al1", name: "Hero shots", assetIds: ["a1", "a4", "a5"] },
    },
    {
      entityType: "tag",
      entityId: "t1",
      revision: 1,
      payload: { id: "t1", name: "state:after-hair-system", assetIds: ["a2", "a3", "a4"] },
    },
    {
      entityType: "tag",
      entityId: "t2",
      revision: 1,
      payload: { id: "t2", name: "status:review", assetIds: ["a1"] },
    },
    { entityType: "saved_search", entityId: "s1", revision: 1, payload: { id: "s1" } },
    { entityType: "asset", entityId: "bad", revision: 1, payload: { nonsense: true } },
  ];
}

interface Challenge {
  deviceId: string;
  publicKey: string;
  scopes: string[];
  challenge: string;
}

/** A stand-in for the Framebase Worker that verifies real ECDSA enrollment signatures. */
export function createFakeCloud(options: { pageSize?: number; entities?: BootstrapEntity[] } = {}) {
  const entities = options.entities ?? sampleEntities();
  const pageSize = options.pageSize ?? 500;
  const challenges = new Map<string, Challenge>();
  const tokens = new Map<string, { scopes: string[]; expiresAtMs: number }>();
  const state = {
    enrollments: 0,
    bootstrapCalls: 0,
    variantCalls: 0,
    enrolledScopes: [] as string[][],
    variantStatus: undefined as number | undefined,
  };
  let seq = 0;

  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  const err = (status: number, code: string, message: string) =>
    json({ error: { code, message } }, status);

  const fetchImpl = (async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(
      typeof input === "string" ? input : input instanceof URL ? input.href : input.url,
    );
    const method = init?.method ?? "GET";
    const headers = new Headers(init?.headers);
    const path = url.pathname;

    if (method === "POST" && path === "/v1/auth/enroll/challenge") {
      if (headers.get("X-Pairing-Credential") !== PAIRING_SECRET)
        return err(401, "UNAUTHORIZED", "Invalid or missing pairing credential");
      const body = JSON.parse(String(init?.body));
      const id = `c${++seq}`;
      challenges.set(id, {
        deviceId: body.deviceId,
        publicKey: body.publicKey,
        scopes: body.scopes,
        challenge: `ch${seq}`,
      });
      return json({ challengeId: id, challenge: `ch${seq}`, expiresAt: "2099-01-01T00:00:00Z" });
    }

    if (method === "POST" && path === "/v1/auth/enroll/complete") {
      const body = JSON.parse(String(init?.body));
      const c = challenges.get(body.challengeId);
      if (!c)
        return err(
          404,
          "ENROLLMENT_CHALLENGE_EXPIRED",
          "Enrollment challenge is invalid or expired",
        );
      const key = await subtle.importKey(
        "spki",
        fromB64url(c.publicKey),
        { name: "ECDSA", namedCurve: "P-256" },
        false,
        ["verify"],
      );
      const payload = new TextEncoder().encode(`${body.challengeId}.${c.deviceId}.${c.challenge}`);
      const ok = await subtle.verify(
        { name: "ECDSA", hash: "SHA-256" },
        key,
        fromB64url(body.signature),
        payload,
      );
      if (!ok) return err(401, "ENROLLMENT_PROOF_INVALID", "Device signature did not verify");
      challenges.delete(body.challengeId);
      state.enrollments++;
      state.enrolledScopes.push(c.scopes);
      const token = `tok-${state.enrollments}`;
      const expiresAtMs = Date.now() + 3_600_000;
      tokens.set(token, { scopes: c.scopes, expiresAtMs });
      return json({ status: "enrolled", token, expiresAt: new Date(expiresAtMs).toISOString() });
    }

    const bearer = headers.get("authorization")?.replace(/^Bearer /, "");
    const session = bearer ? tokens.get(bearer) : undefined;
    if (!session) return err(401, "UNAUTHORIZED", "Invalid or expired token");
    if (!session.scopes.includes("library.read")) return err(403, "FORBIDDEN", "Missing scope");

    if (method === "GET" && path === "/v1/catalog/bootstrap") {
      state.bootstrapCalls++;
      const cursor = Number(url.searchParams.get("cursor") ?? 0);
      const limit = Math.min(Number(url.searchParams.get("limit") ?? 100), pageSize);
      const page = entities.slice(cursor, cursor + limit);
      const next = cursor + page.length;
      return json({
        watermarkRevision: 42,
        entities: page,
        nextCursor: next < entities.length ? String(next) : null,
      });
    }

    const variant = path.match(/^\/v1\/assets\/([^/]+)\/variants\/([^/]+)$/);
    if (method === "GET" && variant) {
      state.variantCalls++;
      if (state.variantStatus) return err(state.variantStatus, "UPSTREAM", "forced");
      if (variant[1] === "missing")
        return err(404, "ASSET_NOT_FOUND", "Verified asset was not found");
      return new Response(new Uint8Array([1, 2, 3]), { headers: { "content-type": "image/webp" } });
    }
    return err(404, "NOT_FOUND", "no route");
  }) as typeof fetch;

  return {
    fetch: fetchImpl,
    state,
    /** Makes every issued session look revoked/expired to the Worker. */
    invalidateSessions: () => tokens.clear(),
  };
}
