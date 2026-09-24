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

export type CleaningTransform =
  | {
      id: string;
      type: 'preserve_structure';
      enabled: boolean;
      block_types: ('table' | 'list_item' | 'code' | 'quote' | 'footnote')[];
    }
  | { id: string; type: 'unicode_normalize'; enabled: boolean; form: 'NFC' | 'NFKC' }
  | { id: string; type: 'remove_control_characters'; enabled: boolean }
  | {
      id: string;
      type: 'reflow_pdf_lines';
      enabled: boolean;
      block_types: ('paragraph' | 'unknown')[];
    }
  | { id: string; type: 'dehyphenate'; enabled: boolean; mode: 'conservative' }
  | {
      id: string;
      type: 'remove_repeated_headers_footers';
      enabled: boolean;
      minimum_page_ratio: number;
      minimum_pages: number;
      margin_ratio: number;
    }
  | {
      id: string;
      type: 'remove_empty_blocks';
      enabled: boolean;
      minimum_characters: number;
    }
  | {
      id: string;
      type: 'remove_literal_boilerplate';
      enabled: boolean;
      values: string[];
      block_types: string[];
    }
  | {
      id: string;
      type: 'website_selectors';
      enabled: boolean;
      include: string[];
      exclude: string[];
    }
  | {
      id: string;
      type: 'website_main_content';
      enabled: boolean;
      remove_semantic_chrome: boolean;
      remove_cookie_banners: boolean;
      remove_repeated_site_chrome: boolean;
      minimum_page_ratio: number;
    }
  | {
      id: string;
      type: 'validate_useful_content';
      enabled: boolean;
      minimum_characters: number;
      maximum_characters: number;
    };

export type IngestionNode =
  | (NodeBase & {
      type: 'source';
      config: ExistingFilesConfig | WebsiteConfig | S3Config | NotionConfig | ConfluenceConfig;
    })
  | (NodeBase & {
      type: 'extract';
      strategy?: 'media_type_registry' | 'native_text' | 'auto' | 'native' | 'layout_aware';
      ocr?: {
        mode: 'off' | 'auto' | 'always';
        languages: string[];
        rotate_pages: boolean;
        deskew: boolean;
        dpi: number;
        max_pages: number;
        timeout_seconds: number;
      };
      tables?: 'preserve' | 'markdown' | 'plain_text';
      quality_policy?: 'default-v1' | 'strict-v1' | 'warn-v1';
      config_version?: string;
    })
  | (NodeBase & {
      type: 'clean';
      normalize_whitespace?: boolean;
      repeated_boilerplate?: string[];
      minimum_text_chars?: number;
      maximum_text_chars?: number;
      exact_content_deduplication?: boolean;
      profile?: 'standard-v1' | 'structure-aware-v1';
      config_version?: string;
      steps?: CleaningTransform[];
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
    schema_version: 1 | 2;
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
  schedule_id: string | null;
  source_snapshot_id: string | null;
  trigger_kind: 'manual' | 'scheduled';
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
  node_states?: {
    node_id: string;
    node_type: IngestionNode['type'];
    ordinal: number;
    status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
    started_at: string | null;
    finished_at: string | null;
  }[];
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
  processing_versions: Record<string, string> | null;
  updated_at: string;
};

export type WebsiteIngestionRunItem = {
  source_kind: 'website';
  ordinal: number;
  source_node_id: string;
  source_item_id: string | null;
  source_revision_id: string | null;
  processing_run_id: string | null;
  canonical_location: string | null;
  display_name: string;
  media_type: string | null;
  outcome: 'new' | 'changed' | 'unchanged' | 'removed' | 'excluded' | 'duplicate' | 'failed';
  status: 'ready' | 'succeeded' | 'failed' | 'cancelled';
  reason: string;
  chunk_count: number;
  error: string | null;
  processing_versions: Record<string, string> | null;
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

export type ContentDerivation = {
  id: string;
  project_id: string;
  document_id: string;
  processing_run_id: string;
  kind: 'extracted' | 'cleaned';
  schema_version: 1;
  engine_version: string;
  configuration_hash: string;
  input_hash: string;
  output_hash: string;
  title: string | null;
  media_type: string;
  measurements: {
    character_count: number;
    block_count: number;
    page_count: number;
    empty_block_count?: number;
    page_character_counts?: number[];
    page_block_counts?: number[];
    native_page_count?: number;
    layout_page_count?: number;
    ocr_page_count?: number;
    empty_page_count?: number;
    replacement_character_ratio?: number;
    control_character_ratio?: number;
    repeated_line_ratio?: number;
    suspicious_reading_order_count?: number;
    table_count?: number;
    malformed_table_count?: number;
    ocr_confidence_median?: number | null;
    ocr_confidence_p05?: number | null;
    extraction_duration_ms?: number;
    resource_category?: 'native' | 'bounded-cpu';
    fallback_path?: string[];
    quality_decision?: 'pass' | 'warn' | 'exclude' | 'fail';
  };
  findings: {
    code: string;
    severity: string;
    count: number;
    message: string;
    page_numbers?: number[];
    remediation?: string | null;
  }[];
  transforms: {
    transform: string;
    version: string;
    changed_blocks: number;
    removed_blocks: number;
    duration_ms?: number;
    metrics?: Record<string, string | number | boolean>;
    changes?: {
      block_id: string;
      action: 'rewritten' | 'removed' | 'retained';
      reason: string;
      count: number;
    }[];
  }[];
  created_at: string;
};

export type ExtractionCapabilities = {
  schema_version: 1;
  media_types: ('application/pdf' | 'text/plain')[];
  profiles: {
    id: 'auto' | 'native' | 'layout_aware';
    available: boolean;
    reason: string | null;
  }[];
  ocr: {
    available: boolean;
    languages: string[];
    reason: string | null;
    max_pages: number;
    max_pixels_per_page: number;
  };
  table_modes: ('preserve' | 'markdown' | 'plain_text')[];
  quality_policies: ('default-v1' | 'strict-v1' | 'warn-v1')[];
  cleaning_profiles: {
    id: 'structure-aware-v1';
    name: string;
    config_version: 'structure-clean-v1';
    steps: CleaningTransform[];
  }[];
};

export type CleaningDiff = {
  block_id: string;
  block_type: string;
  page_number: number | null;
  before_text: string;
  after_text: string | null;
  action: 'unchanged' | 'rewritten' | 'removed';
  transforms: string[];
  reasons: string[];
};

export type ContentBlock = {
  derivation_id: string;
  ordinal: number;
  block_id: string;
  block_type: string;
  text: string;
  page_number: number | null;
  bounding_box: Record<string, number> | null;
  heading_path: string[];
  source_span: Record<string, unknown>;
  attributes: Record<string, unknown>;
};

export type IngestionSchedule = {
  id: string;
  project_id: string;
  pipeline_id: string;
  pipeline_version_id: string;
  pipeline_version: number;
  name: string;
  status: 'paused' | 'enabled';
  cadence:
    | { kind: 'interval'; minutes: number }
    | { kind: 'daily'; local_time: string; timezone: string };
  next_run_at: string | null;
  last_run_id: string | null;
  last_triggered_at: string | null;
  last_outcome: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'skipped' | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

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
