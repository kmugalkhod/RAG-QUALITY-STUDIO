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

type NodeBase = { id: string };

export type IngestionNode =
  | (NodeBase & { type: 'source'; config: ExistingFilesConfig | WebsiteConfig })
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
