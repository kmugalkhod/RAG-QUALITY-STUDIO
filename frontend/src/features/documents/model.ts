import type { RetrievalSettings } from '../../lib/retrieval';
import type { Page } from '../../lib/pagination';
export interface Run {
  id: string;
  document_id: string;
  version: number;
  chunk_size: number;
  overlap: number;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  progress: number;
  error: string | null;
  chunk_count: number;
  attempts: number;
  config_version: string;
  parser_version: string;
  created_at: string;
}
export interface Document {
  id: string;
  filename: string;
  size_bytes: number;
  content_hash: string;
  created_at: string;
  latest_run: Run | null;
}
export interface Chunk {
  ordinal: number;
  page_number: number | null;
  start_char: number;
  end_char: number;
  text: string;
}

export interface EmbeddingConfig {
  provider: string;
  model: string;
  dimensions: number;
  endpoint_id: string;
  revision: string;
}
export interface EmbeddingSettings {
  configured: boolean;
  config: EmbeddingConfig | null;
  error: string | null;
}
export interface IndexVersion {
  id: string;
  project_id: string;
  version: number;
  embedding_config: EmbeddingConfig;
  status: Run['status'];
  chunk_count: number;
  embedded_count: number;
  attempts: number;
  failures: number;
  error: string | null;
  created_at: string;
}
export type IndexPage = Page<IndexVersion>;
export interface Evidence {
  rank: number;
  document_id: string;
  filename: string;
  content_hash: string;
  run_id: string;
  processing_version: number;
  ordinal: number;
  page_number: number | null;
  start_char: number;
  end_char: number;
  text: string;
  cosine_distance: number | null;
  lexical_score?: number | null;
  fusion_score?: number | null;
  vector_rank?: number | null;
  keyword_rank?: number | null;
}
export interface Retrieval {
  index_id: string;
  index_version: number;
  embedding_config: EmbeddingConfig;
  items: Evidence[];
  score_semantics: string;
  retrieval?: RetrievalSettings;
  diagnostics?: Record<string, unknown>;
}
