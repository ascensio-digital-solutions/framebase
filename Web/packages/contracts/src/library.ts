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
  watermarkRevision: z.number().int().nonnegative(),
  fetchedAt: z.string(),
});

export type LibraryFolder = z.infer<typeof libraryFolderSchema>;
export type LibraryNamedCount = z.infer<typeof libraryNamedCountSchema>;
export type LibraryAsset = z.infer<typeof libraryAssetSchema>;
export type LibraryAssetPage = z.infer<typeof libraryAssetPageSchema>;
export type LibraryStructure = z.infer<typeof libraryStructureSchema>;
export type LibrarySummary = z.infer<typeof librarySummarySchema>;
