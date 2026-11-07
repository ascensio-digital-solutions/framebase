import { describe, expect, it } from "vitest";
import { BASE_URL, PAIRING_SECRET, createFakeCloud, sampleEntities } from "../testing/fakeCloud";
import { CloudApiError, CloudClient } from "./client";

const make = (cloud = createFakeCloud(), pairingSecret = PAIRING_SECRET) => ({
  cloud,
  client: new CloudClient({
    baseUrl: BASE_URL + "/",
    pairingSecret,
    deviceId: "framebase-web-test",
    fetchImpl: cloud.fetch,
  }),
});

describe("CloudClient", () => {
  it("enrolls with a verifiable signature and requests only library.read", async () => {
    const { cloud, client } = make();
    const res = await client.get("/v1/catalog/bootstrap?cursor=0&limit=500");
    expect(res.status).toBe(200);
    expect(cloud.state.enrollments).toBe(1);
    expect(cloud.state.enrolledScopes).toEqual([["library.read"]]);
  });

  it("reuses the session and enrolls only once for concurrent requests", async () => {
    const { cloud, client } = make();
    await Promise.all([client.get("/v1/catalog/bootstrap"), client.get("/v1/catalog/bootstrap")]);
    await client.get("/v1/catalog/bootstrap");
    expect(cloud.state.enrollments).toBe(1);
  });

  it("re-enrolls once and retries when the session is rejected", async () => {
    const { cloud, client } = make();
    await client.get("/v1/catalog/bootstrap");
    cloud.invalidateSessions();
    const res = await client.get("/v1/catalog/bootstrap");
    expect(res.status).toBe(200);
    expect(cloud.state.enrollments).toBe(2);
  });

  it("refreshes a session that is about to expire without waiting for a 401", async () => {
    let clock = Date.now();
    const cloud = createFakeCloud();
    const client = new CloudClient({
      baseUrl: BASE_URL,
      pairingSecret: PAIRING_SECRET,
      deviceId: "framebase-web-test",
      fetchImpl: cloud.fetch,
      now: () => clock,
    });
    await client.get("/v1/catalog/bootstrap");
    clock += 3_600_000 - 30_000; // inside the 60s skew window
    await client.get("/v1/catalog/bootstrap");
    expect(cloud.state.enrollments).toBe(2);
  });

  it("rejects a wrong pairing secret without leaking it", async () => {
    const { client } = make(createFakeCloud(), "wrong-secret-value");
    const failure = await client.get("/v1/catalog/bootstrap").catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(CloudApiError);
    expect((failure as CloudApiError).status).toBe(401);
    expect(String((failure as Error).message)).not.toContain("wrong-secret-value");
  });

  it("follows catalog pagination to the end", async () => {
    const cloud = createFakeCloud({ pageSize: 3 });
    const { client } = make(cloud);
    const { entities, watermarkRevision } = await client.fetchCatalog();
    expect(entities).toHaveLength(sampleEntities().length);
    expect(watermarkRevision).toBe(42);
    expect(cloud.state.bootstrapCalls).toBeGreaterThan(1);
  });
});
