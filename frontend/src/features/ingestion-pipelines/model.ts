export type ExistingFilesConfig = {
  kind: 'existing_files';
  document_ids: string[];
};

export type WebsiteSelection =
  | { mode: 'single_url'; url: string }
  | { mode: 'url_list'; urls: string[] }
  | { mode: 'crawl'; start_url: string }
  | { mode: 'sitemap'; sitemap_url: string };

export type WebsiteConfig = {
  kind: 'website';
  selection: WebsiteSelection;
  allowed_origins: string[];
  include_path_prefixes?: string[];
  exclude_path_prefixes?: string[];
  max_pages: number;
  max_depth: number;
  max_response_bytes: number;
  max_total_bytes: number;
  request_timeout_seconds: number;
  deadline_seconds: number;
  concurrency: number;
  requests_per_second: number;
  redirect_limit: number;
  user_agent: string;
  respect_robots?: boolean;
};

export type S3Config = {
  kind: 's3';
  connection_id: string;
  region: string;
  bucket: string;
  prefix?: string;
  expected_bucket_owner?: string | null;
  allowed_file_types: ('txt' | 'pdf')[];
  max_objects: number;
  max_pages: number;
  max_object_bytes: number;
  max_total_bytes: number;
  request_timeout_seconds: number;
};

export type NotionConfig = {
  kind: 'notion';
  connection_id: string;
  selection:
    | { mode: 'workspace' }
    | { mode: 'pages'; page_ids: string[] }
    | { mode: 'data_sources'; data_source_ids: string[] };
  max_pages: number;
  max_api_pages: number;
  max_blocks_per_page: number;
  max_block_depth: number;
  max_text_chars: number;
  request_timeout_seconds: number;
};

export type ConfluenceConfig = {
  kind: 'confluence';
  connection_id: string;
  selection:
    | { mode: 'site' }
    | { mode: 'spaces'; space_ids: string[] }
    | { mode: 'pages'; page_ids: string[] };
  title_prefixes: string[];
  exclude_title_prefixes: string[];
  label_ids: string[];
  max_pages: number;
  max_api_pages: number;
  max_response_bytes: number;
  max_text_chars: number;
  request_timeout_seconds: number;
};

type NodeBase = { id: string };

export type IngestionNode =
  | (NodeBase & {
      type: 'source';
      config: ExistingFilesConfig | WebsiteConfig | S3Config | NotionConfig | ConfluenceConfig;
    })
  | (NodeBase & {
      type: 'extract';
      strategy?: 'media_type_registry';
      config_version?: string;
    })
  | (NodeBase & {
      type: 'clean';
      normalize_whitespace?: boolean;
      repeated_boilerplate?: string[];
      minimum_text_chars?: number;
      maximum_text_chars?: number;
      exact_content_deduplication?: boolean;
    })
  | (NodeBase & {
      type: 'chunk';
      algorithm?: 'character_window';
      unit?: 'characters';
      size: number;
      overlap: number;
      config_version?: string;
    })
  | (NodeBase & {
      type: 'embed';
      provider: string;
      model: string;
      dimensions: number;
      config_version: string;
    })
  | (NodeBase & {
      type: 'publish_index';
      knowledge_set_name: string;
      knowledge_set_id?: string | null;
    });

export type IngestionPipelineDraft = {
  kind: 'ingestion';
  name: string;
  execution: {
    schema_version: 1;
    nodes: IngestionNode[];
    edges: { source: string; target: string }[];
  };
  layout: { positions: Record<string, { x: number; y: number }> };
};

export type IngestionPipelineVersion = IngestionPipelineDraft & {
  id: string;
  pipeline_id: string;
  project_id: string;
  version: number;
  created_at: string;
};

export type SourcePreviewItem = {
  ordinal: number;
  source_node_id: string;
  external_id: string | null;
  display_name: string;
  canonical_location: string | null;
  provider_revision: string | null;
  media_type: string | null;
  status: 'included' | 'excluded' | 'duplicate' | 'failed';
  reason: string;
  size_bytes: number | null;
  depth: number | null;
  error_code: string | null;
};

export type SourcePreview = {
  id: string;
  project_id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  progress: number;
  discovered_count: number;
  included_count: number;
  excluded_count: number;
  duplicate_count: number;
  failed_count: number;
  attempts: number;
  failures: number;
  error: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type IngestionRun = {
  id: string;
  project_id: string;
  pipeline_version_id: string;
  knowledge_set_id: string;
  knowledge_set_name: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  stage: 'discovering' | 'processing' | 'indexing' | 'complete';
  progress: number;
  discovered_count: number;
  processed_count: number;
  failed_count: number;
  new_count: number;
  changed_count: number;
  unchanged_count: number;
  removed_count: number;
  chunk_count: number;
  embedded_count: number;
  published_count: number;
  attempts: number;
  failures: number;
  error: string | null;
  published_index_id: string | null;
  published_index_version: number | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type ExistingIngestionRunItem = {
  source_kind: 'existing_files';
  document_id: string;
  filename: string;
  content_hash: string;
  media_type: string;
  source_node_id: string;
  processing_run_id: string;
  processing_version: number;
  processing_created: boolean;
  status: 'processing' | 'ready' | 'succeeded' | 'failed' | 'cancelled';
  chunk_count: number;
  error: string | null;
  updated_at: string;
};

export type WebsiteIngestionRunItem = {
  source_kind: 'website';
  ordinal: number;
  source_node_id: string;
  source_item_id: string | null;
  source_revision_id: string | null;
  canonical_location: string | null;
  display_name: string;
  media_type: string | null;
  outcome: 'new' | 'changed' | 'unchanged' | 'removed' | 'excluded' | 'duplicate' | 'failed';
  status: 'ready' | 'succeeded' | 'failed' | 'cancelled';
  reason: string;
  chunk_count: number;
  error: string | null;
  updated_at: string;
};

export type S3IngestionRunItem = Omit<WebsiteIngestionRunItem, 'source_kind'> & {
  source_kind: 's3';
};

export type NotionIngestionRunItem = Omit<WebsiteIngestionRunItem, 'source_kind'> & {
  source_kind: 'notion';
};

export type ConfluenceIngestionRunItem = Omit<WebsiteIngestionRunItem, 'source_kind'> & {
  source_kind: 'confluence';
};

export type IngestionRunItem =
  | ExistingIngestionRunItem
  | WebsiteIngestionRunItem
  | S3IngestionRunItem
  | NotionIngestionRunItem
  | ConfluenceIngestionRunItem;

export function canonicalIngestion(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalIngestion).join(',')}]`;
  }
  if (value !== null && typeof value === 'object') {
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalIngestion(item)}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}
