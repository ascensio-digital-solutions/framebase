import { Hono } from 'hono';
import { apiError } from '../lib/api.js';
import { requireAuth } from '../middleware/auth.js';
import { GoogleAiStudioService } from '../services/googleAiStudio.js';
import type { AppEnv } from '../types.js';

export const intelligenceRouter = new Hono<AppEnv>();

function getGoogleAiStudio(c: any): GoogleAiStudioService {
  const apiKey = (c.env as any).GEMINI_API_KEY ||
                 (c.env as any).GOOGLE_AI_STUDIO_API_KEY ||
                 (c.env as any).GOOGLE_API_KEY ||
                 '';
  return new GoogleAiStudioService({
    apiKey,
    aiGatewayAccountId: (c.env as any).AI_GATEWAY_ACCOUNT_ID,
    aiGatewayName: (c.env as any).AI_GATEWAY_NAME,
    fetcher: (c.env as any).AI_FETCHER ?? fetch
  });
}

intelligenceRouter.post('/intelligence/analyze/:id', requireAuth('library.write'), async (c) => {
  const assetID = c.req.param('id');

  const asset = await c.env.DB.prepare(
    `SELECT assets.id, assets.folder_id, assets.display_name, assets.asset_metadata,
            blobs.sha256, blobs.r2_key, blobs.r2_key AS storage_key, blobs.media_type, blobs.upload_state
     FROM assets JOIN blobs ON blobs.id = assets.blob_id WHERE assets.id = ?`
  ).bind(assetID).first<{
    id: string;
    folder_id: string | null;
    display_name: string;
    asset_metadata: string;
    sha256: string;
    r2_key: string;
    storage_key: string;
    media_type: string;
    upload_state: string;
  }>();

  if (!asset) {
    return apiError(c, 404, 'ASSET_NOT_FOUND', 'Asset was not found');
  }

  const derivativeKey = `derivatives/v1/${asset.sha256}/grid-512.webp`;
  let object = await c.env.BLOBS.get(derivativeKey);
  let mimeType = 'image/webp';

  if (!object?.body) {
    object = await c.env.BLOBS.get(asset.storage_key);
    mimeType = asset.media_type || 'image/jpeg';
  }
  if (!object?.body) {
    const legacyOrigin = (c.env as { LEGACY_ORIGIN?: R2Bucket }).LEGACY_ORIGIN;
    if (legacyOrigin) {
      object = await legacyOrigin.get(asset.storage_key);
      mimeType = asset.media_type || 'image/jpeg';
    }
  }
  if (!object?.body) {
    return apiError(c, 404, 'R2_OBJECT_MISSING', 'Source image data is missing in storage');
  }

  const arrayBuf = await object.arrayBuffer();
  const imageBytes = new Uint8Array(arrayBuf);

  let bodyParams: { librarySpace?: 'hsc' | 'personal'; ocrHint?: string; filename?: string; catalogId?: string } = {};
  try {
    bodyParams = await c.req.json();
  } catch {
    // Body is optional
  }

  // Tier-1 Cloudflare Workers AI if bound
  if ((c.env as any).AI) {
    try {
      await (c.env as any).AI.run('@cf/unum/uform-gen2-qwen-500m', {
        image: [...imageBytes],
        prompt: 'Analyze image'
      });
    } catch (err) {
      console.warn('Optional Workers AI Tier-1 run failed:', err);
    }
  }

  const aiStudio = getGoogleAiStudio(c);

  const vision = await aiStudio.analyzeImageVision({
    imageBytes,
    mimeType,
    librarySpace: bodyParams.librarySpace ?? 'hsc',
    filename: bodyParams.filename ?? asset.display_name,
    ocrHint: bodyParams.ocrHint
  });

  const embedding = await aiStudio.embedMultimodal({
    imageBytes,
    mimeType,
    text: vision.caption ? `${vision.caption} ${vision.proposedTags.join(' ')}` : undefined,
    outputDimensionality: 1024
  });

  let catalogId = bodyParams.catalogId;
  if (!catalogId) {
    const libraryRow = await c.env.DB.prepare('SELECT id FROM library_metadata LIMIT 1').first<{ id: string }>();
    catalogId = libraryRow?.id ?? 'framebase-dev-library';
  }

  const isVectorizeBound = Boolean((c.env as any).VECTORIZE);
  if (isVectorizeBound) {
    const vectorizeRecord = {
      id: asset.id,
      values: embedding,
      metadata: {
        catalog_id: catalogId,
        asset_id: asset.id,
        folder_id: asset.folder_id ?? '',
        top_folder: vision.topFolder
      }
    };
    try {
      await (c.env as any).VECTORIZE.upsert([vectorizeRecord]);
    } catch {
      await (c.env as any).VECTORIZE.upsert(vectorizeRecord);
    }
  }

  return c.json({
    status: 'ok',
    assetId: asset.id,
    analysis: vision,
    vectorIndexed: isVectorizeBound
  });
});

intelligenceRouter.post('/search/semantic', requireAuth('library.read'), async (c) => {
  let body: { query?: string; limit?: number; catalogId?: string } = {};
  try {
    body = await c.req.json();
  } catch {
    return apiError(c, 400, 'BAD_REQUEST', 'Invalid JSON body');
  }

  const query = body.query?.trim();
  if (!query) {
    return apiError(c, 400, 'INVALID_QUERY', 'Search query cannot be empty');
  }

  const limit = typeof body.limit === 'number' && body.limit > 0 ? body.limit : 20;

  let catalogId = body.catalogId;
  if (!catalogId) {
    const libraryRow = await c.env.DB.prepare('SELECT id FROM library_metadata LIMIT 1').first<{ id: string }>();
    catalogId = libraryRow?.id ?? 'framebase-dev-library';
  }

  if (!(c.env as any).VECTORIZE) {
    return apiError(c, 503, 'VECTOR_SEARCH_UNAVAILABLE', 'Vectorize is not bound or configured');
  }

  const aiStudio = getGoogleAiStudio(c);
  const vector = await aiStudio.embedMultimodal({
    text: query,
    outputDimensionality: 1024
  });

  const queryResults = await (c.env as any).VECTORIZE.query(vector, {
    topK: limit,
    returnMetadata: 'all'
  });

  const rawMatches = queryResults?.matches ?? [];
  const filteredMatches = rawMatches.filter((match: any) => {
    if (!match.metadata?.catalog_id) return true;
    return match.metadata.catalog_id === catalogId;
  });

  const assetIds = filteredMatches.map((m: any) => m.id);
  const assetMap = new Map<string, any>();

  if (assetIds.length > 0) {
    const placeholders = assetIds.map(() => '?').join(',');
    const queryResult = await c.env.DB.prepare(
      `SELECT assets.id, assets.display_name, assets.folder_id, assets.favorite, assets.rating, assets.status,
              assets.asset_metadata, assets.created_at, assets.updated_at,
              blobs.sha256, blobs.media_type, blobs.byte_size
       FROM assets JOIN blobs ON blobs.id = assets.blob_id
       WHERE assets.id IN (${placeholders})`
    ).bind(...assetIds).all();

    for (const row of queryResult.results ?? []) {
      assetMap.set((row as any).id, row);
    }
  }

  const matches = filteredMatches.map((m: any) => {
    const asset = assetMap.get(m.id);
    return {
      id: m.id,
      score: m.score,
      metadata: m.metadata,
      asset: asset ? {
        ...asset,
        displayName: asset.display_name,
        folderId: asset.folder_id,
        mediaType: asset.media_type,
        byteSize: asset.byte_size
      } : null
    };
  });

  return c.json({ matches });
});
