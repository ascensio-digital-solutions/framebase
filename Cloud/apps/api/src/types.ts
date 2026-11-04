export interface VectorizeMatches {
  matches: Array<{
    id: string;
    score: number;
    values?: number[];
    metadata?: Record<string, unknown>;
  }>;
}

export interface VectorizeIndexBinding {
  upsert(vectors: Array<{ id: string; values: number[]; metadata?: Record<string, unknown> }>): Promise<unknown>;
  query(vector: number[], options?: { topK?: number; returnValues?: boolean; returnMetadata?: 'none' | 'indexed' | 'all'; filter?: Record<string, unknown> }): Promise<VectorizeMatches>;
}

export interface WorkersAiBinding {
  run(model: string, inputs: Record<string, unknown>, options?: Record<string, unknown>): Promise<unknown>;
}

export interface QueueBinding {
  send(message: unknown): Promise<void>;
}

export interface Bindings {
  DB: D1Database;
  BLOBS: R2Bucket;
  LEGACY_ORIGIN?: R2Bucket;
  IMAGES?: ImagesBinding;
  AI?: WorkersAiBinding;
  VECTORIZE?: VectorizeIndexBinding;
  VECTORIZE_INDEX?: VectorizeIndexBinding;
  INGEST_QUEUE?: QueueBinding;
  JWT_SECRET?: string;
  ENROLLMENT_SECRET?: string;
  R2_ACCOUNT_ID?: string;
  R2_ACCESS_KEY_ID?: string;
  R2_SECRET_ACCESS_KEY?: string;
  R2_BUCKET_NAME?: string;
  OBSERVABILITY_SAMPLE_RATE?: string;
  GEMINI_API_KEY?: string;
  GCP_PROJECT_ID?: string;
  AI_GATEWAY_ACCOUNT_ID?: string;
  AI_GATEWAY_NAME?: string;
  AI_GATEWAY_ID?: string;
  CF_ACCOUNT_ID?: string;
  LIBRARY_SPACE?: 'hsc' | 'personal' | 'knowledge';
}

export interface Variables {
  deviceId?: string;
  scopes?: string[];
  agentId?: string;
  agentScopes?: string[];
  requestId: string;
}

export interface AppEnv {
  Bindings: Bindings;
  Variables: Variables;
}
