import { describe, expect, it } from "vitest";
import {
  commandEnvelopeSchema,
  commandSchema,
  isPersistentCommand,
  persistentCommandNames,
  workspaceEventSchema,
} from "./index";

const operationId = "7b0f3c1e-2d54-4b6a-9d6e-0c1f2a3b4c5d";

describe("commandSchema", () => {
  it("applies defaults to assets.search", () => {
    const parsed = commandSchema.parse({ name: "assets.search", args: {} });
    expect(parsed).toEqual({
      name: "assets.search",
      args: { query: "", tags: [], limit: 50 },
    });
  });

  it("rejects unknown commands and empty asset lists", () => {
    expect(commandSchema.safeParse({ name: "assets.delete", args: {} }).success).toBe(false);
    expect(
      commandSchema.safeParse({
        name: "assets.tag",
        args: { assetIds: [], add: ["status:review"] },
      }).success,
    ).toBe(false);
  });

  it("bounds bulk operations at 500 assets", () => {
    const assetIds = Array.from({ length: 501 }, (_, i) => `asset-${i}`);
    expect(commandSchema.safeParse({ name: "assets.select", args: { assetIds } }).success).toBe(
      false,
    );
  });

  it("accepts plain and namespaced tags", () => {
    const parsed = commandSchema.parse({
      name: "assets.tag",
      args: { assetIds: ["a1"], add: ["archive", "status:review"] },
    });
    expect(parsed.name).toBe("assets.tag");
  });
});

describe("commandEnvelopeSchema", () => {
  it("requires expectedRevision for every persistent command", () => {
    expect(persistentCommandNames.length).toBeGreaterThan(0);
    const result = commandEnvelopeSchema.safeParse({
      operationId,
      libraryId: "lib-1",
      actor: "understand-agent",
      command: { name: "assets.move", args: { assetIds: ["a1"], folderId: "f1" } },
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.path).toEqual(["expectedRevision"]);
  });

  it("lets read-only commands omit expectedRevision", () => {
    const result = commandEnvelopeSchema.safeParse({
      operationId,
      libraryId: "lib-1",
      actor: "user",
      command: { name: "assets.search", args: { query: "mono mesh" } },
    });
    expect(result.success).toBe(true);
  });

  it("rejects a non-UUID operation ID", () => {
    expect(
      commandEnvelopeSchema.safeParse({
        operationId: "not-a-uuid",
        libraryId: "lib-1",
        actor: "user",
        command: { name: "assets.open", args: { assetId: "a1" } },
      }).success,
    ).toBe(false);
  });

  it("classifies persistent commands", () => {
    expect(isPersistentCommand({ name: "generation.start" })).toBe(true);
    expect(isPersistentCommand({ name: "knowledge.search" })).toBe(false);
  });
});

describe("workspaceEventSchema", () => {
  it("parses a generation update that needs reconciliation", () => {
    const event = workspaceEventSchema.parse({
      type: "generation.updated",
      jobId: "job-1",
      status: "needs_reconciliation",
    });
    expect(event.type).toBe("generation.updated");
  });
});
