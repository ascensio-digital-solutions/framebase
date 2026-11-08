import { z } from "zod";

/** Read-only library views served by the Web API. The browser never sees Cloudflare URLs or credentials. */

const id = z.string().min(1).max(128);

/** Derivative sizes the Web API will fetch. Other Cloudflare variants (shopify-*, email-*, social-*) are not exposed. */
export const imageVariants = ["grid-256", "grid-512", "preview-1600"] as const;
export const imageVariantSchema = z.enum(imageVariants);
export type ImageVariant = z.infer<typeof imageVariantSchema>;

export const libraryFolderSchema = z.object({
  id,
  name: z.string(),
  parentId: id.nullable(),
  systemKind: z.string().nullable(),
  sortOrder: z.number(),
  /** Assets in this folder and all of its descendants. */
  assetCount: z.number().int().nonnegative(),
});

export const libraryNamedCountSchema = z.object({
  id,
  name: z.string(),
  assetCount: z.number().int().nonnegative(),
  revision: z.number().int().nonnegative().optional(),
});

export const libraryAssetSchema = z.object({
  id,
  displayName: z.string(),
  folderId: id,
  favorite: z.boolean(),
  rating: z.number().int(),
  mediaType: z.string(),
  byteSize: z.number().int().nonnegative(),
  createdAt: z.string(),
  tags: z.array(z.string()),
  /** IDs of the same tags, in the same order, so a tag can be removed without a lookup. */
  tagIds: z.array(id),
  /** Catalog revision, needed by the Worker to accept an edit (stale edits are rejected). */
  revision: z.number().int().nonnegative(),
  /** Set only for items in Trash. */
  trashedAt: z.string().nullable().optional(),
  scheduledPurgeAt: z.string().nullable().optional(),
});

export const libraryAssetPageSchema = z.object({
  assets: z.array(libraryAssetSchema),
  total: z.number().int().nonnegative(),
  nextCursor: z.string().nullable(),
});

export const libraryStructureSchema = z.object({
  folders: z.array(libraryFolderSchema),
  albums: z.array(libraryNamedCountSchema),
  /** Most-used tags first, capped; `tagsTotal` is the real count. */
  tags: z.array(libraryNamedCountSchema),
  tagsTotal: z.number().int().nonnegative(),
});

export const librarySummarySchema = z.object({
  assetCount: z.number().int().nonnegative(),
  folderCount: z.number().int().nonnegative(),
  albumCount: z.number().int().nonnegative(),
  tagCount: z.number().int().nonnegative(),
  trashedCount: z.number().int().nonnegative(),
  watermarkRevision: z.number().int().nonnegative(),
  fetchedAt: z.string(),
});

export type LibraryFolder = z.infer<typeof libraryFolderSchema>;
export type LibraryNamedCount = z.infer<typeof libraryNamedCountSchema>;
export type LibraryAsset = z.infer<typeof libraryAssetSchema>;
export type LibraryAssetPage = z.infer<typeof libraryAssetPageSchema>;
export type LibraryStructure = z.infer<typeof libraryStructureSchema>;
export type LibrarySummary = z.infer<typeof librarySummarySchema>;

/**
 * Edits the web studio can make. Each maps onto the Worker's audited, revision-checked mutation API.
 * `operationId` is the idempotency key: retrying the same request never applies an edit twice.
 * "trash" is a reversible delete (restorable for 30 days). There is deliberately no permanent delete.
 */
const operationId = z.uuid();
const assetIds = z.array(id).min(1).max(200);

export const libraryActionSchema = z.discriminatedUnion("action", [
  z.object({
    action: z.literal("rename"),
    operationId,
    assetId: id,
    displayName: z.string().trim().min(1).max(160),
  }),
  z.object({ action: z.literal("favorite"), operationId, assetId: id, favorite: z.boolean() }),
  z.object({
    action: z.literal("rating"),
    operationId,
    assetId: id,
    rating: z.number().int().min(0).max(5),
  }),
  z.object({ action: z.literal("move"), operationId, assetIds, folderId: id }),
  z.object({ action: z.literal("trash"), operationId, assetIds }),
  z.object({ action: z.literal("restore"), operationId, assetIds }),
  z.object({
    action: z.literal("tag"),
    operationId,
    assetIds,
    tagId: id,
    mode: z.enum(["add", "remove"]),
  }),
  z.object({
    action: z.literal("createTag"),
    operationId,
    // The Worker only accepts lowercase `namespace:value` tags, e.g. `status:review`.
    name: z
      .string()
      .regex(
        /^[a-z][a-z0-9_-]{0,63}:[a-z0-9][a-z0-9._-]{0,127}$/,
        "Use lowercase namespace:value, e.g. status:review",
      ),
  }),
]);

export const libraryActionResultSchema = z.object({
  status: z.literal("applied"),
  /** The edited assets as they are now. */
  assets: z.array(libraryAssetSchema),
  /** Present after `createTag`. */
  tag: libraryNamedCountSchema.optional(),
});

export type LibraryAction = z.infer<typeof libraryActionSchema>;
export type LibraryActionResult = z.infer<typeof libraryActionResultSchema>;
