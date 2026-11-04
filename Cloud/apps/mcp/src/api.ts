export interface FramebaseAgentOperation {
  id: string;
  operation: 'addTags';
  status: 'proposed' | 'approved' | 'succeeded' | 'stale' | 'expired' | 'failed';
  targetAssetIds: string[];
  catalogRevision: number;
  tagId: string;
  createdAt: string;
  updatedAt: string;
  expiresAt: string | null;
  result: Record<string, unknown> | null;
}

export interface ApprovedAssetOutput {
  id: string;
  displayName: string;
  publicCdnUrl: string;
  variantUrl?: string;
  tags: string[];
}

export interface ApprovedAssetQuery {
  tag?: string;
  folder?: string;
  variant?: string;
  limit?: number;
}

export class FramebaseMcpError extends Error {
  constructor(public readonly code: string, message: string, public readonly status: number) {
    super(message);
  }
}

export type FetchFunction = typeof fetch;

export class FramebaseAgentAPI {
  private readonly baseURL: URL;
  private readonly cdnBaseURL: string;

  constructor(
    endpoint: string,
    private readonly credential: string,
    private readonly fetcher: FetchFunction = fetch,
    cdnBaseURL: string = 'https://assets.hairsolutions.co'
  ) {
    this.baseURL = new URL(endpoint.endsWith('/') ? endpoint : `${endpoint}/`);
    this.cdnBaseURL = cdnBaseURL.endsWith('/') ? cdnBaseURL.slice(0, -1) : cdnBaseURL;
    const local = this.baseURL.hostname === 'localhost' || this.baseURL.hostname === '127.0.0.1';
    if (this.baseURL.protocol !== 'https:' && !local) throw new FramebaseMcpError('INVALID_ENDPOINT', 'Framebase MCP requires an HTTPS API endpoint', 400);
    if (!/^[-A-Za-z0-9_]{3,128}\.[-A-Za-z0-9_]{32,128}$/.test(credential)) {
      throw new FramebaseMcpError('INVALID_CREDENTIAL', 'Framebase agent credential is invalid', 400);
    }
  }

  async proposeTag(tagId: string, targetAssetIds: string[], catalogRevision: number): Promise<FramebaseAgentOperation> {
    const body = await this.request('/v1/agent-operations/tag-proposals', 'POST', { tagId, targetAssetIds, catalogRevision });
    return this.operationFrom(body);
  }

  async getOperation(operationId: string): Promise<{ operation: FramebaseAgentOperation; audit: Array<Record<string, unknown>> }> {
    const body = await this.request(`/v1/agent-operations/${encodeURIComponent(operationId)}`, 'GET');
    return {
      operation: this.operationFrom(body),
      audit: Array.isArray(body.audit) ? body.audit.filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === 'object') : []
    };
  }

  async applyTagProposal(operationId: string, approvalToken: string): Promise<FramebaseAgentOperation> {
    const body = await this.request(`/v1/agent-operations/${encodeURIComponent(operationId)}/apply`, 'POST', { approvalToken });
    return this.operationFrom(body);
  }

  async getApprovedAssets(query: ApprovedAssetQuery = {}): Promise<ApprovedAssetOutput[]> {
    const limit = query.limit ?? 5;
    const params = new URLSearchParams();
    if (query.tag) params.set('tag', query.tag);
    if (query.folder) params.set('folder', query.folder);
    params.set('limit', String(limit));

    try {
      const body = await this.request(`/v1/catalog/bootstrap?${params.toString()}`, 'GET');
      const entities = Array.isArray(body.entities) ? (body.entities as Array<{ entityType: string; entityId: string; payload?: Record<string, unknown> }>) : [];
      const tagMap = new Map<string, string>();
      const assetTags = new Map<string, string[]>();

      for (const e of entities) {
        if (e.entityType === 'tag' && typeof e.payload?.name === 'string') {
          tagMap.set(e.entityId, e.payload.name);
        }
      }

      for (const e of entities) {
        if (e.entityType === 'asset_tag' && typeof e.payload?.asset_id === 'string' && typeof e.payload?.tag_id === 'string') {
          const tagName = tagMap.get(e.payload.tag_id) ?? e.payload.tag_id;
          const current = assetTags.get(e.payload.asset_id) ?? [];
          current.push(tagName);
          assetTags.set(e.payload.asset_id, current);
        }
      }

      const results: ApprovedAssetOutput[] = [];
      for (const e of entities) {
        if (e.entityType === 'asset' && e.payload) {
          const id = String(e.entityId || e.payload.id);
          const displayName = String(e.payload.display_name || e.payload.filename || id);
          const tags = assetTags.get(id) ?? [];

          if (query.tag && !tags.some(t => t.toLowerCase() === query.tag!.toLowerCase())) {
            continue;
          }

          const publicCdnUrl = `${this.cdnBaseURL}/assets/${id}`;
          const variantUrl = query.variant
            ? `${this.cdnBaseURL}/assets/${id}/variants/${query.variant}`
            : undefined;

          results.push({
            id,
            displayName,
            publicCdnUrl,
            ...(variantUrl ? { variantUrl } : {}),
            tags
          });

          if (results.length >= limit) break;
        }
      }
      return results;
    } catch {
      return [];
    }
  }

  async semanticSearch(
    query: string,
    limit: number = 10
  ): Promise<Array<{ id: string; score: number; displayName?: string; publicCdnUrl: string; metadata?: Record<string, unknown> }>> {
    const body = await this.request('/v1/search/semantic', 'POST', { query, limit });
    const matches = Array.isArray(body.matches) ? (body.matches as Array<Record<string, unknown>>) : [];
    return matches.map((match) => {
      const id = String(match.id ?? '');
      const score = typeof match.score === 'number' ? match.score : Number(match.score ?? 0);
      const displayName = typeof match.displayName === 'string' ? match.displayName : undefined;
      const metadata = match.metadata && typeof match.metadata === 'object' && !Array.isArray(match.metadata) ? (match.metadata as Record<string, unknown>) : undefined;
      return {
        id,
        score,
        ...(displayName ? { displayName } : {}),
        publicCdnUrl: `${this.cdnBaseURL}/assets/${id}`,
        ...(metadata ? { metadata } : {})
      };
    });
  }

  async analyzeAsset(
    assetId: string,
    librarySpace: 'hsc' | 'personal' = 'hsc'
  ): Promise<Record<string, unknown>> {
    return await this.request(`/v1/intelligence/analyze/${encodeURIComponent(assetId)}`, 'POST', { librarySpace });
  }

  private operationFrom(body: Record<string, unknown>): FramebaseAgentOperation {
    const operation = body.operation;
    if (!operation || typeof operation !== 'object' || Array.isArray(operation)) {
      throw new FramebaseMcpError('INVALID_RESPONSE', 'Framebase API returned an invalid operation response', 502);
    }
    return operation as FramebaseAgentOperation;
  }

  private async request(path: string, method: 'GET' | 'POST', payload?: Record<string, unknown>): Promise<Record<string, unknown>> {
    const response = await this.fetcher(new URL(path.slice(1), this.baseURL), {
      method,
      headers: {
        Authorization: `Agent ${this.credential}`,
        ...(payload ? { 'Content-Type': 'application/json' } : {})
      },
      body: payload ? JSON.stringify(payload) : undefined
    });
    let body: unknown = null;
    try { body = await response.json(); } catch { /* Error remains deliberately bounded below. */ }
    if (!response.ok) {
      const error = body && typeof body === 'object' && 'error' in body ? (body as { error?: { code?: unknown; message?: unknown } }).error : undefined;
      throw new FramebaseMcpError(
        typeof error?.code === 'string' ? error.code : 'FRAMEBASE_API_ERROR',
        typeof error?.message === 'string' ? error.message : `Framebase API request failed (${response.status})`,
        response.status
      );
    }
    if (!body || typeof body !== 'object' || Array.isArray(body)) throw new FramebaseMcpError('INVALID_RESPONSE', 'Framebase API returned an invalid response', 502);
    return body as Record<string, unknown>;
  }
}
