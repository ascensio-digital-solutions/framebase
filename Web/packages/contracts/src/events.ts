import { z } from "zod";
import { panelSchema, viewModeSchema } from "./commands";

/** Events fanned out so every panel reconciles against authoritative state after any action. */

const id = z.string().trim().min(1).max(128);

export const workspaceEventSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("assets.changed"),
    libraryId: id,
    assetIds: z.array(id).min(1).max(500),
    revision: z.number().int().nonnegative(),
  }),
  z.object({
    type: z.literal("board.changed"),
    libraryId: id,
    boardId: id,
    revision: z.number().int().nonnegative(),
  }),
  z.object({
    type: z.literal("generation.updated"),
    jobId: id,
    status: z.enum(["queued", "running", "succeeded", "failed", "needs_reconciliation"]),
    resultAssetId: id.optional(),
  }),
  z.object({
    type: z.literal("panel.requested"),
    panel: panelSchema,
    view: viewModeSchema.optional(),
  }),
]);

export type WorkspaceEvent = z.infer<typeof workspaceEventSchema>;
