import { z } from "zod";

/**
 * Typed commands shared by manual UI interactions and both chat agents (Create / Understand).
 * Every persistent command carries an operation ID (idempotency + receipt) and an expected
 * catalog revision so stale writes are rejected instead of silently applied.
 */

const id = z.string().trim().min(1).max(128);
// 500 mirrors the existing bound on agent tag proposals.
const assetIds = z.array(id).min(1).max(500);
// Tags are free-form strings: some library spaces use `namespace:value`, others plain words.
const tag = z.string().trim().min(1).max(80);

export const panelNames = ["explorer", "create", "understand", "workspace", "preview"] as const;
export const panelSchema = z.enum(panelNames);

export const viewModes = ["grid", "list", "board"] as const;
export const viewModeSchema = z.enum(viewModes);

export const knowledgeScopes = ["brand", "technical", "marketing"] as const;

export const commandSchema = z.discriminatedUnion("name", [
  z.object({
    name: z.literal("assets.search"),
    args: z.object({
      query: z.string().trim().max(500).default(""),
      folderId: id.optional(),
      tags: z.array(tag).max(20).default([]),
      limit: z.number().int().min(1).max(200).default(50),
    }),
  }),
  z.object({ name: z.literal("assets.select"), args: z.object({ assetIds }) }),
  z.object({ name: z.literal("assets.open"), args: z.object({ assetId: id }) }),
  z.object({
    name: z.literal("assets.move"),
    args: z.object({ assetIds, folderId: id }),
  }),
  z.object({
    name: z.literal("assets.tag"),
    args: z.object({
      assetIds,
      add: z.array(tag).max(20).default([]),
      remove: z.array(tag).max(20).default([]),
    }),
  }),
  z.object({
    name: z.literal("assets.analyze"),
    args: z.object({ assetIds, kind: z.enum(["ocr", "classify", "caption"]) }),
  }),
  z.object({
    name: z.literal("boards.addAssets"),
    args: z.object({
      boardId: id,
      assetIds,
      position: z.object({ x: z.number(), y: z.number() }).optional(),
    }),
  }),
  z.object({
    name: z.literal("boards.arrange"),
    args: z.object({
      boardId: id,
      strategy: z.enum(["grid", "cluster", "timeline"]),
      assetIds: z.array(id).max(500).optional(),
    }),
  }),
  z.object({
    name: z.literal("workspace.openPanel"),
    args: z.object({ panel: panelSchema, view: viewModeSchema.optional() }),
  }),
  z.object({
    name: z.literal("knowledge.search"),
    args: z.object({
      query: z.string().trim().min(1).max(500),
      scope: z.enum(knowledgeScopes),
      limit: z.number().int().min(1).max(20).default(5),
    }),
  }),
  z.object({
    name: z.literal("generation.start"),
    args: z.object({
      brief: z.string().trim().min(1).max(4000),
      referenceAssetIds: z.array(id).max(20).default([]),
      conversationModel: z.string().trim().max(200).optional(),
      imageModel: z.string().trim().max(200).optional(),
      count: z.number().int().min(1).max(4).default(1),
    }),
  }),
]);

export type Command = z.infer<typeof commandSchema>;
export type CommandName = Command["name"];

/** Commands that change catalog, board or spend state. They require `expectedRevision`. */
export const persistentCommandNames = [
  "assets.move",
  "assets.tag",
  "boards.addAssets",
  "boards.arrange",
  "generation.start",
] as const satisfies readonly CommandName[];

export function isPersistentCommand(command: Pick<Command, "name">): boolean {
  return (persistentCommandNames as readonly string[]).includes(command.name);
}

export const actorSchema = z.enum(["user", "create-agent", "understand-agent"]);
export type Actor = z.infer<typeof actorSchema>;

export const commandEnvelopeSchema = z
  .object({
    /** Idempotency key. A retried envelope with the same ID must never repeat a paid or destructive step. */
    operationId: z.uuid(),
    /** Library spaces are isolated; a command resolves inside exactly one. */
    libraryId: id,
    actor: actorSchema,
    expectedRevision: z.number().int().nonnegative().optional(),
    command: commandSchema,
  })
  .superRefine((envelope, ctx) => {
    if (isPersistentCommand(envelope.command) && envelope.expectedRevision === undefined) {
      ctx.addIssue({
        code: "custom",
        path: ["expectedRevision"],
        message: `expectedRevision is required for persistent command ${envelope.command.name}`,
      });
    }
  });

export type CommandEnvelope = z.infer<typeof commandEnvelopeSchema>;

export const receiptStatuses = ["applied", "rejected", "pending", "needs_reconciliation"] as const;

export const receiptSchema = z.object({
  operationId: z.uuid(),
  status: z.enum(receiptStatuses),
  revision: z.number().int().nonnegative().optional(),
  undoable: z.boolean(),
  message: z.string().max(1000).optional(),
});

export type Receipt = z.infer<typeof receiptSchema>;
