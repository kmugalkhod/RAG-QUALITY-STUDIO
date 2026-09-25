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
  artifact_state?: 'legacy_plaintext' | 'encrypted' | 'deleting' | 'deleted';
  raw_retained_until?: string | null;
  raw_deleted_at?: string | null;
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
  knowledge_set_id: string;
  knowledge_set_name: string;
  version: number;
  embedding_config: EmbeddingConfig;
  status: Run['status'];
  chunk_count: number;
  embedded_count: number;
  attempts: number;
  failures: number;
  processing_run_count: number;
  is_current: boolean;
  source_snapshot_id?: string | null;
  source_snapshot_number?: number | null;
  source_snapshot_collected_at?: string | null;
  ingestion_pipeline_id?: string | null;
  ingestion_pipeline_name?: string | null;
  ingestion_pipeline_version?: number | null;
  chunk_size?: number | null;
  chunk_overlap?: number | null;
  error: string | null;
  created_at: string;
}
export interface KnowledgeSet {
  id: string;
  project_id: string;
  name: string;
  current_ready_index_id: string | null;
  created_at: string;
}

export function formatIndexOption(index: IndexVersion): string {
  return `${index.knowledge_set_name} · Version ${index.version} · ${index.chunk_count} passages`;
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
  source_url?: string | null;
  section_path?: string[];
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

export interface IndexRecord {
  run_id: string;
  ordinal: number;
  document_id: string;
  filename: string;
  processing_version: number;
  page_number: number | null;
  start_char: number;
  end_char: number;
  text: string;
  source_url: string | null;
  section_path: string[];
  dimensions: number;
  embedded: boolean;
  embedding_norm: number | null;
  embedding_preview: number[];
}

export type IndexRecordPage = Page<IndexRecord>;

export interface SourceSnapshot {
  id: string;
  project_id: string;
  source_kind: 'website' | 's3' | 'notion' | 'confluence';
  source_identity: {
    source_kind?: string;
    mode?: string;
    origins?: string[];
    selection_modes?: string[];
    buckets?: string[];
    prefixes?: string[];
  };
  snapshot_number: number;
  status: 'collecting' | 'ready' | 'failed' | 'cancelled';
  discovered_count: number;
  included_count: number;
  excluded_count: number;
  duplicate_count: number;
  failed_count: number;
  new_count: number;
  changed_count: number;
  unchanged_count: number;
  removed_count: number;
  total_bytes: number;
  creating_ingestion_run_id: string;
  downstream_index_count: number;
  error: string | null;
  created_at: string;
  collected_at: string | null;
}
export interface SourceSnapshotMember {
  ordinal: number;
  canonical_location: string;
  media_type: string;
  size_bytes: number;
  fetched_at: string;
  provider_revision: string | null;
}
export interface SourceSnapshotIndex {
  id: string;
  knowledge_set_id: string;
  knowledge_set_name: string;
  version: number;
  status: Run['status'];
  chunk_count: number;
  embedded_count: number;
  is_current: boolean;
  ingestion_pipeline_id: string | null;
  ingestion_pipeline_version_id: string | null;
  ingestion_pipeline_name: string | null;
  ingestion_pipeline_version: number | null;
  created_at: string;
}
