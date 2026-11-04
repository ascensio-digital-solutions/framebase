import { Hono } from 'hono';
import { apiError } from '../lib/api.js';
import { GoogleAiStudioService } from '../services/googleAiStudio.js';
import type { AppEnv, VectorizeIndexBinding } from '../types.js';

export const assistantRouter = new Hono<AppEnv>();

export type AssistantToolName =
  | 'search_library'
  | 'create_album_from_query'
  | 'organize_into_subfolders'
  | 'find_knowledge_repos';

export interface AssistantToolArguments {
  albumName?: string;
  query?: string;
  hairColor?: string;
  hairlinePresentation?: string;
  photoRole?: string;
  folderPath?: string;
  tags?: string[];
  subfolders?: string[];
  topic?: string;
}

export interface AssistantToolCall {
  id: string;
  tool: AssistantToolName;
  arguments: AssistantToolArguments;
}

export interface AssistantCatalogContext {
  folders?: Array<{ id: string; path: string; assetCount?: number }>;
  albums?: Array<{ id: string; name: string; assetCount?: number }>;
  topTags?: string[];
}

export interface AssistantChatRequest {
  librarySpace?: 'hsc' | 'personal' | 'knowledge';
  message: string;
  conversationHistory?: Array<{ role: 'user' | 'assistant'; content: string }>;
  catalogContext?: AssistantCatalogContext;
}

export interface AssistantChatResponse {
  reply: string;
  toolCalls: AssistantToolCall[];
  matchedAssetIds: string[];
  provider: string;
}

interface ParsedIntent {
  reply: string;
  toolCalls: AssistantToolCall[];
  searchTerms: string[];
  tagPatterns: string[];
  folderHint?: string;
}

const HAIR_COLOR_MAP: Array<{ pattern: RegExp; color: string; tags: string[]; label: string }> = [
  { pattern: /\b(blonde|light\s+blonde|#?22)\b/i, color: 'blonde', tags: ['color:22', 'color:blonde'], label: 'Blonde' },
  { pattern: /\b(jet\s+black|#?1\b)/i, color: 'black', tags: ['color:1', 'color:black'], label: 'Jet Black' },
  { pattern: /\b(off\s+black|natural\s+black|#?1b)\b/i, color: 'black', tags: ['color:1B', 'color:black'], label: 'Natural Black' },
  { pattern: /\b(black)\b/i, color: 'black', tags: ['color:1B', 'color:black'], label: 'Black' },
  { pattern: /\b(dark\s+brown|#?2|#?3)\b/i, color: 'brown', tags: ['color:3', 'color:brown'], label: 'Dark Brown' },
  { pattern: /\b(medium\s+brown|#?4)\b/i, color: 'brown', tags: ['color:4', 'color:brown'], label: 'Medium Brown' },
  { pattern: /\b(light\s+brown|#?5)\b/i, color: 'brown', tags: ['color:5', 'color:brown'], label: 'Light Brown' },
  { pattern: /\b(brown)\b/i, color: 'brown', tags: ['color:4', 'color:brown'], label: 'Brown' },
  { pattern: /\b(grey|gray|silver|salt\s+and\s+pepper)\b/i, color: 'grey', tags: ['grey:20%', 'color:grey'], label: 'Grey' },
  { pattern: /\b(red|auburn)\b/i, color: 'red', tags: ['color:red'], label: 'Auburn' }
];

function detectHairColor(message: string): { color: string; tags: string[]; label: string } | null {
  for (const entry of HAIR_COLOR_MAP) {
    if (entry.pattern.test(message)) {
      return { color: entry.color, tags: entry.tags, label: entry.label };
    }
  }
  return null;
}

function detectHairlinePresentation(message: string): { presentation: string; tags: string[] } | null {
  if (/\b(not[-\s]visible)\b/i.test(message)) {
    return { presentation: 'not-visible', tags: ['hairline:not-visible'] };
  }
  if (/\b(partially[-\s]visible)\b/i.test(message)) {
    return { presentation: 'partially-visible', tags: ['hairline:partially-visible'] };
  }
  if (/\b(hairlines?|front\s+edge|exposed\s+front|undetectable\s+hairline)\b/i.test(message)) {
    const tags = ['hairline:clearly-visible'];
    if (/\bundetectable\b/i.test(message)) {
      tags.push('hairline:undetectable');
    }
    return { presentation: 'clearly-visible', tags };
  }
  return null;
}

function detectSubfolders(message: string): string[] {
  const explicit: string[] = [];
  if (/\bheadshots?\b/i.test(message)) explicit.push('headshots');
  if (/\beditorial\b/i.test(message)) explicit.push('editorial');
  if (/\bbefore[-\s/&]+after\b/i.test(message)) explicit.push('before-after');
  if (/\binstall[-\s/&]+cut\b/i.test(message)) explicit.push('install-cut');

  if (explicit.length > 0) {
    return explicit;
  }

  if (/\bswatch(es)?\b/i.test(message)) {
    return ['dark-shades', 'medium-shades', 'blonde-shades', 'grey-blends'];
  }

  return ['headshots', 'editorial', 'before-after'];
}

function resolveTargetFolder(message: string, catalogContext?: AssistantCatalogContext, isSwatch = false): string {
  // Check explicit path in message first
  const pathMatch = message.match(/\b([0-9]{2}_[a-z0-9_-]+\/[a-z0-9_/-]+|models\/[a-z0-9_-]+)\b/i);
  if (pathMatch) {
    return pathMatch[1];
  }

  // Check if any catalogContext folder path or name is referenced
  if (catalogContext?.folders && catalogContext.folders.length > 0) {
    const lower = message.toLowerCase();
    for (const folder of catalogContext.folders) {
      const segments = folder.path.toLowerCase().split('/').filter(Boolean);
      const lastSegment = segments[segments.length - 1];
      if (lastSegment && lower.includes(lastSegment)) {
        return folder.path;
      }
    }
    return catalogContext.folders[0].path;
  }

  // Extract model name if phrased like "model folder <name>" or "model <name>"
  const modelNameMatch = message.match(/\bmodel(?:\s+folder)?\s+([a-z0-9_-]+)\b/i);
  if (modelNameMatch && !['into', 'folder', 'subfolders', 'with', 'by', 'to', 'the', 'a'].includes(modelNameMatch[1].toLowerCase())) {
    return `03_people/models/${modelNameMatch[1].toLowerCase()}`;
  }

  return isSwatch ? '01_products/color-swatches' : '03_people/models';
}

export function planDeterministicIntent(req: AssistantChatRequest): ParsedIntent {
  const message = req.message.trim();
  const lower = message.toLowerCase();

  const hairColorInfo = detectHairColor(message);
  const hairlineInfo = detectHairlinePresentation(message);

  // 1. Check for Knowledge / Open-Source Repo / CRM screenshot discovery
  const isKnowledgeRepoIntent =
    req.librarySpace === 'knowledge' && /\b(repo|repos|repository|repositories|crm|crms|open[-\s]?source|github)\b/i.test(message) ||
    /\b(open[-\s]?source|github\s+repos?|repositories|crm\s+repos?)\b/i.test(message) ||
    (/\b(screenshots?)\b/i.test(message) && /\b(crm|crms|repo|repos|open[-\s]?source|github)\b/i.test(message));

  if (isKnowledgeRepoIntent) {
    const isCrm = /\bcrms?\b/i.test(message);
    const topic = isCrm ? 'crm' : 'open-source';
    const tags = ['source:screenshot', 'category:open-source'];
    if (isCrm) {
      tags.push('topic:crm');
    }
    const folderPath = req.catalogContext?.folders?.[0]?.path ?? (isCrm ? '02_saas_&_crm' : '01_ai_&_code/github-repos');
    const query = isCrm ? 'open-source CRM github repository screenshot' : message;

    const findCall: AssistantToolCall = {
      id: `call_${crypto.randomUUID().slice(0, 8)}`,
      tool: 'find_knowledge_repos',
      arguments: {
        topic,
        query,
        folderPath,
        tags
      }
    };

    const searchCall: AssistantToolCall = {
      id: `call_${crypto.randomUUID().slice(0, 8)}`,
      tool: 'search_library',
      arguments: {
        query,
        topic,
        folderPath,
        tags
      }
    };

    return {
      reply: `Searching your Knowledge Library screenshots for ${isCrm ? 'open-source CRM repositories' : 'open-source repositories'} and extracting repository metadata.`,
      toolCalls: [findCall, searchCall],
      searchTerms: isCrm ? ['crm', 'open-source', 'github', 'screenshot', 'repo'] : ['open-source', 'github', 'screenshot', 'repo'],
      tagPatterns: tags,
      folderHint: folderPath
    };
  }

  // 2. Check for Subfolder Organization (splitting a model or swatch folder into subfolders)
  const isOrganizeSubfoldersIntent =
    /\b(split|divide|organize|separate|break\s+down|sort)\b/i.test(message) &&
    (/\b(subfolders?|sub-folders?|headshots?|editorial|before[-\s/&]+after|models?|swatch(?:es)?)\b/i.test(message));

  if (isOrganizeSubfoldersIntent) {
    const isSwatch = /\bswatch(es)?\b/i.test(message);
    const subfolders = detectSubfolders(message);
    const folderPath = resolveTargetFolder(message, req.catalogContext, isSwatch);
    const photoRole = isSwatch ? 'color-swatch' : 'model-portfolio';
    const tags = isSwatch
      ? ['category:color-swatch']
      : ['subject_count:single_person', ...subfolders.map((sf) => `role:${sf}`)];

    const organizeCall: AssistantToolCall = {
      id: `call_${crypto.randomUUID().slice(0, 8)}`,
      tool: 'organize_into_subfolders',
      arguments: {
        folderPath,
        subfolders,
        photoRole,
        query: `${folderPath} ${subfolders.join(' ')}`,
        tags
      }
    };

    return {
      reply: `Organizing "${folderPath}" into ${subfolders.map((s) => `\`${s}\``).join(', ')} subfolders while enforcing solo-subject model qualification rules.`,
      toolCalls: [organizeCall],
      searchTerms: [folderPath.split('/').pop() ?? 'model', ...subfolders],
      tagPatterns: tags,
      folderHint: folderPath
    };
  }

  // 3. Check for Album Creation from Query
  const isAlbumIntent =
    /\b(albums?|collections?)\b/i.test(message) &&
    /\b(create|make|build|new|gather|compile|add|with|all)\b/i.test(message);

  if (isAlbumIntent) {
    const hairColor = hairColorInfo?.color;
    const hairlinePresentation = hairlineInfo?.presentation ?? (/\bhairlines?\b/i.test(message) ? 'clearly-visible' : undefined);
    const tags: string[] = [];
    if (hairlineInfo) {
      tags.push(...hairlineInfo.tags);
    } else if (hairlinePresentation) {
      tags.push(`hairline:${hairlinePresentation}`);
    }
    if (hairColorInfo) {
      for (const t of hairColorInfo.tags) {
        if (!tags.includes(t)) tags.push(t);
      }
    }

    let albumName = 'Curated Selection';
    const quotedMatch = message.match(/(?:named|called)\s+["']([^"']+)["']/i);
    if (quotedMatch) {
      albumName = quotedMatch[1].trim();
    } else if (hairColorInfo && hairlinePresentation) {
      albumName = `${hairColorInfo.label} Hairlines`;
    } else if (hairColorInfo) {
      albumName = `${hairColorInfo.label} Hair Systems`;
    } else if (hairlinePresentation) {
      albumName = 'Clearly Visible Hairlines';
    }

    const queryParts = [
      hairColor,
      hairlinePresentation ? `hairline ${hairlinePresentation}` : undefined,
      'photos'
    ].filter(Boolean);
    const query = queryParts.length > 1 ? queryParts.join(' ') : message;
    const photoRole = hairlinePresentation ? 'hairline-showcase' : undefined;

    const sharedArgs: AssistantToolArguments = {
      albumName,
      query,
      ...(hairColor ? { hairColor } : {}),
      ...(hairlinePresentation ? { hairlinePresentation } : {}),
      ...(photoRole ? { photoRole } : {}),
      ...(tags.length > 0 ? { tags } : {})
    };

    const albumCall: AssistantToolCall = {
      id: `call_${crypto.randomUUID().slice(0, 8)}`,
      tool: 'create_album_from_query',
      arguments: sharedArgs
    };

    const searchCall: AssistantToolCall = {
      id: `call_${crypto.randomUUID().slice(0, 8)}`,
      tool: 'search_library',
      arguments: {
        query,
        ...(hairColor ? { hairColor } : {}),
        ...(hairlinePresentation ? { hairlinePresentation } : {}),
        ...(photoRole ? { photoRole } : {}),
        ...(tags.length > 0 ? { tags } : {})
      }
    };

    const searchTerms: string[] = [];
    if (hairColor) searchTerms.push(hairColor);
    if (hairlinePresentation) searchTerms.push('hairline', hairlinePresentation);
    if (searchTerms.length === 0) {
      searchTerms.push(...lower.split(/\W+/).filter((w) => w.length > 3));
    }

    return {
      reply: `Created album "${albumName}" matching ${hairColor ? `${hairColor} hair ` : ''}${hairlinePresentation ? `with ${hairlinePresentation} hairline presentation` : 'your query'}.`,
      toolCalls: [albumCall, searchCall],
      searchTerms,
      tagPatterns: tags
    };
  }

  // 4. Default: Search Library
  const tags: string[] = [];
  if (hairlineInfo) tags.push(...hairlineInfo.tags);
  if (hairColorInfo) tags.push(...hairColorInfo.tags);

  const searchArgs: AssistantToolArguments = {
    query: message,
    ...(hairColorInfo ? { hairColor: hairColorInfo.color } : {}),
    ...(hairlineInfo ? { hairlinePresentation: hairlineInfo.presentation } : {}),
    ...(tags.length > 0 ? { tags } : {})
  };

  return {
    reply: `Executed hybrid semantic and structured search for "${message}".`,
    toolCalls: [
      {
        id: `call_${crypto.randomUUID().slice(0, 8)}`,
        tool: 'search_library',
        arguments: searchArgs
      }
    ],
    searchTerms: lower.split(/\W+/).filter((w) => w.length > 2),
    tagPatterns: tags
  };
}

function buildDeterministicVector(text: string, dimensions = 1024): number[] {
  const vec = new Array<number>(dimensions).fill(0);
  const normalized = text.toLowerCase().trim() || 'framebase';
  for (let i = 0; i < normalized.length; i++) {
    const code = normalized.charCodeAt(i);
    vec[(i * 31 + code) % dimensions] += (code % 29) / 29.0 + 0.1;
  }
  const norm = Math.sqrt(vec.reduce((acc, v) => acc + v * v, 0)) || 1;
  return vec.map((v) => v / norm);
}

async function queryD1StructuredAssets(
  db: D1Database | undefined,
  intent: ParsedIntent
): Promise<string[]> {
  if (!db) return [];

  try {
    const rows = await db.prepare(
      `SELECT assets.id, assets.display_name, assets.folder_id, assets.asset_metadata,
              folders.name AS folder_name,
              GROUP_CONCAT(tags.name, ',') AS tag_names
       FROM assets
       LEFT JOIN folders ON folders.id = assets.folder_id
       LEFT JOIN asset_tags ON asset_tags.asset_id = assets.id
       LEFT JOIN tags ON tags.id = asset_tags.tag_id
       WHERE assets.status = 'active'
       GROUP BY assets.id
       ORDER BY assets.updated_at DESC
       LIMIT 100`
    ).all<{
      id: string;
      display_name: string;
      folder_id: string;
      asset_metadata: string;
      folder_name: string | null;
      tag_names: string | null;
    }>();

    const allActive = rows.results ?? [];
    if (allActive.length === 0) return [];

    const matched: string[] = [];
    for (const row of allActive) {
      const haystack = [
        row.id,
        row.display_name,
        row.folder_id,
        row.folder_name ?? '',
        row.asset_metadata ?? '',
        row.tag_names ?? ''
      ].join(' ').toLowerCase();

      const tagMatch = intent.tagPatterns.some((t) => haystack.includes(t.toLowerCase()));
      const termMatch = intent.searchTerms.some((term) => term.length > 2 && haystack.includes(term.toLowerCase()));
      const folderMatch = intent.folderHint
        ? haystack.includes(intent.folderHint.toLowerCase()) ||
          haystack.includes((intent.folderHint.split('/').pop() ?? '').toLowerCase())
        : false;

      if (tagMatch || termMatch || folderMatch) {
        matched.push(row.id);
      }
    }

    return matched;
  } catch {
    return [];
  }
}

async function queryVectorizeAssets(
  c: any,
  vectorize: VectorizeIndexBinding | undefined,
  queryText: string
): Promise<string[]> {
  if (!vectorize) return [];

  let vector: number[] | null = null;
  const apiKey = (c.env as any).GEMINI_API_KEY || (c.env as any).GOOGLE_AI_STUDIO_API_KEY || '';
  const hasCustomFetcher = Boolean((c.env as any).AI_FETCHER);

  if (apiKey || hasCustomFetcher) {
    try {
      const aiStudio = new GoogleAiStudioService({
        apiKey: apiKey || 'test-key',
        aiGatewayAccountId: (c.env as any).CF_ACCOUNT_ID ?? (c.env as any).AI_GATEWAY_ACCOUNT_ID,
        aiGatewayName: (c.env as any).AI_GATEWAY_ID ?? (c.env as any).AI_GATEWAY_NAME,
        fetcher: (c.env as any).AI_FETCHER ?? fetch
      });
      vector = await aiStudio.embedMultimodal({
        text: queryText,
        outputDimensionality: 1024
      });
    } catch {
      vector = null;
    }
  }

  if (!vector) {
    vector = buildDeterministicVector(queryText, 1024);
  }

  try {
    const result = await vectorize.query(vector, {
      topK: 20,
      returnMetadata: 'all'
    });
    return (result?.matches ?? []).map((m) => m.id).filter(Boolean);
  } catch {
    return [];
  }
}

assistantRouter.post('/assistant/chat', async (c) => {
  let body: AssistantChatRequest;
  try {
    body = await c.req.json<AssistantChatRequest>();
  } catch {
    return apiError(c, 400, 'BAD_REQUEST', 'Request body must be valid JSON');
  }

  if (!body || typeof body.message !== 'string' || body.message.trim().length === 0) {
    return apiError(c, 400, 'INVALID_MESSAGE', 'message must be a non-empty string');
  }

  const intent = planDeterministicIntent(body);
  const vectorize: VectorizeIndexBinding | undefined =
    c.env.VECTORIZE_INDEX ?? c.env.VECTORIZE;

  const [d1AssetIds, vectorAssetIds] = await Promise.all([
    queryD1StructuredAssets(c.env.DB, intent),
    queryVectorizeAssets(c, vectorize, body.message)
  ]);

  const matchedAssetIds = [...new Set([...vectorAssetIds, ...d1AssetIds])];

  let provider = 'framebase-deterministic-planner';
  let reply = intent.reply;

  if (c.env.AI) {
    try {
      const gatewayId = c.env.AI_GATEWAY_ID ?? c.env.AI_GATEWAY_NAME ?? 'framebase-vision-dev';
      const aiResult = await c.env.AI.run(
        '@cf/meta/llama-3.1-8b-instruct',
        {
          messages: [
            {
              role: 'system',
              content: `You are the Framebase 2.0 Media OS Assistant operating in the "${body.librarySpace ?? 'hsc'}" library space.`
            },
            ...(body.conversationHistory ?? []),
            { role: 'user', content: body.message }
          ]
        },
        { gateway: { id: gatewayId } }
      ) as { response?: string } | null;

      if (aiResult && typeof aiResult.response === 'string' && aiResult.response.trim().length > 0) {
        reply = aiResult.response.trim();
      }
      provider = c.env.AI_GATEWAY_ID ? `cloudflare-ai-gateway:${c.env.AI_GATEWAY_ID}` : 'cloudflare-workers-ai';
    } catch {
      // Keep deterministic fallback reply and toolCalls when Workers AI fails or is offline
    }
  } else if (c.env.AI_GATEWAY_ID) {
    provider = `cloudflare-ai-gateway:${c.env.AI_GATEWAY_ID}`;
  }

  const response: AssistantChatResponse = {
    reply,
    toolCalls: intent.toolCalls,
    matchedAssetIds,
    provider
  };

  return c.json(response);
});
