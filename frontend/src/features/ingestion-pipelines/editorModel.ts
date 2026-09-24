import type { Document, EmbeddingConfig } from '../documents/model';
import type {
  ExtractionCapabilities,
  ConfluenceConfig,
  IngestionNode,
  IngestionPipelineDraft,
  IngestionPipelineVersion,
  IngestionSchedule,
  NotionConfig,
  S3Config,
  WebsiteConfig,
} from './model';

export const terminalIngestionStatuses = new Set(['succeeded', 'failed', 'cancelled']);

export const ingestionStageLabels: Record<IngestionNode['type'], string> = {
  source: 'Source',
  extract: 'Extract',
  clean: 'Clean',
  chunk: 'Chunk',
  embed: 'Embed',
  publish_index: 'Publish reusable index',
};

export function describeCadence(schedule: IngestionSchedule) {
  if (schedule.cadence.kind === 'daily') {
    return `Daily at ${schedule.cadence.local_time} ${schedule.cadence.timezone}`;
  }
  const minutes = schedule.cadence.minutes;
  if (minutes === 10080) {
    return 'Every week';
  }
  if (minutes === 1440) {
    return 'Every day';
  }
  if (minutes % 60 === 0) {
    const hours = minutes / 60;
    return `Every ${hours} ${hours === 1 ? 'hour' : 'hours'}`;
  }
  return `Every ${minutes} minutes`;
}

export const defaultWebsite = (): WebsiteConfig => ({
  kind: 'website',
  selection: { mode: 'crawl', start_url: '' },
  allowed_origins: [],
  include_path_prefixes: ['/'],
  exclude_path_prefixes: [],
  max_pages: 50,
  max_depth: 2,
  max_response_bytes: 2_000_000,
  max_total_bytes: 20_000_000,
  request_timeout_seconds: 10,
  deadline_seconds: 300,
  concurrency: 2,
  requests_per_second: 2,
  redirect_limit: 5,
  user_agent: 'RAGQualityStudio/1.0',
  respect_robots: true,
});

export const defaultS3 = (connectionId = ''): S3Config => ({
  kind: 's3',
  connection_id: connectionId,
  region: 'us-east-1',
  bucket: '',
  prefix: '',
  expected_bucket_owner: null,
  allowed_file_types: ['txt', 'pdf'],
  max_objects: 1000,
  max_pages: 10,
  max_object_bytes: 20 * 1024 * 1024,
  max_total_bytes: 100 * 1024 * 1024,
  request_timeout_seconds: 30,
});

export const defaultNotion = (connectionId = ''): NotionConfig => ({
  kind: 'notion',
  connection_id: connectionId,
  selection: { mode: 'workspace' },
  max_pages: 500,
  max_api_pages: 50,
  max_blocks_per_page: 5000,
  max_block_depth: 8,
  max_text_chars: 2_000_000,
  request_timeout_seconds: 30,
});

export const defaultConfluence = (connectionId = ''): ConfluenceConfig => ({
  kind: 'confluence',
  connection_id: connectionId,
  selection: { mode: 'site' },
  title_prefixes: [],
  exclude_title_prefixes: [],
  label_ids: [],
  max_pages: 500,
  max_api_pages: 100,
  max_response_bytes: 2 * 1024 * 1024,
  max_text_chars: 2_000_000,
  request_timeout_seconds: 30,
});

export function defaultIngestionDraft(
  embedding: EmbeddingConfig,
  documentIds: string[],
  capabilities?: ExtractionCapabilities,
): IngestionPipelineDraft {
  const nodes: IngestionNode[] = [
    { id: 'source', type: 'source', config: { kind: 'existing_files', document_ids: documentIds } },
    {
      id: 'extract',
      type: 'extract',
      strategy: 'auto',
      ocr: {
        mode: capabilities?.ocr.available ? 'auto' : 'off',
        languages: capabilities?.ocr.languages.slice(0, 1) ?? ['eng'],
        rotate_pages: true,
        deskew: true,
        dpi: 200,
        max_pages: Math.min(capabilities?.ocr.max_pages ?? 50, 50),
        timeout_seconds: 30,
      },
      tables: 'preserve',
      quality_policy: 'default-v1',
      config_version: 'layout-ocr-v1',
    },
    {
      id: 'clean',
      type: 'clean',
      normalize_whitespace: true,
      repeated_boilerplate: [],
      minimum_text_chars: 1,
      maximum_text_chars: 2_000_000,
      exact_content_deduplication: true,
      profile: 'standard-v1',
      config_version: 'deterministic-clean-v1',
    },
    {
      id: 'chunk',
      type: 'chunk',
      algorithm: 'character_window',
      unit: 'characters',
      size: 1000,
      overlap: 100,
      config_version: 'character-window-v1',
    },
    {
      id: 'embed',
      type: 'embed',
      provider: embedding.provider,
      model: embedding.model,
      dimensions: embedding.dimensions,
      config_version: embedding.revision,
    },
    { id: 'publish', type: 'publish_index', knowledge_set_name: 'Ingested knowledge' },
  ];
  return {
    kind: 'ingestion',
    name: 'Untitled ingestion pipeline',
    execution: {
      schema_version: 2,
      nodes,
      edges: nodes.slice(1).map((node, index) => ({ source: nodes[index].id, target: node.id })),
    },
    layout: {
      positions: Object.fromEntries(
        nodes.map((node, index) => [node.id, { x: 90, y: 40 + index * 116 }]),
      ),
    },
  };
}

export function describeIngestionNode(node: IngestionNode, documents: Document[]) {
  if (node.type === 'source' && node.config.kind === 'existing_files') {
    return `${node.config.document_ids.length} selected document${node.config.document_ids.length === 1 ? '' : 's'}`;
  }
  if (node.type === 'source' && node.config.kind === 'website') {
    const selection = node.config.selection;
    const location =
      selection.mode === 'url_list'
        ? `${selection.urls.length} URLs`
        : selection.mode === 'single_url'
          ? selection.url
          : selection.mode === 'crawl'
            ? selection.start_url
            : selection.sitemap_url;
    return `Website · ${location}`;
  }
  if (node.type === 'source' && node.config.kind === 's3') {
    return `S3 · ${node.config.bucket || 'Choose a bucket'}`;
  }
  if (node.type === 'source' && node.config.kind === 'notion') {
    const selection = node.config.selection;
    const scope =
      selection.mode === 'workspace'
        ? 'shared workspace'
        : selection.mode === 'pages'
          ? `${selection.page_ids.length} pages`
          : `${selection.data_source_ids.length} data sources`;
    return `Notion · ${scope}`;
  }
  if (node.type === 'source' && node.config.kind === 'confluence') {
    const selection = node.config.selection;
    const scope =
      selection.mode === 'site'
        ? 'accessible site'
        : selection.mode === 'spaces'
          ? `${selection.space_ids.length} spaces`
          : `${selection.page_ids.length} pages`;
    return `Confluence · ${scope}`;
  }
  if (node.type === 'chunk') {
    return `${node.size} characters · ${node.overlap} overlap`;
  }
  if (node.type === 'embed') {
    return `${node.provider} · ${node.model}`;
  }
  if (node.type === 'publish_index') {
    return node.knowledge_set_name;
  }
  if (node.type === 'extract') {
    if (node.config_version !== 'layout-ocr-v1') {
      return 'Native text · compatibility';
    }
    const strategy =
      node.strategy === 'layout_aware'
        ? 'Layout-aware'
        : node.strategy === 'native'
          ? 'Native'
          : 'Auto';
    return `${strategy} · OCR ${node.ocr?.mode ?? 'off'}`;
  }
  if (node.type === 'clean') {
    return 'Normalize and deduplicate';
  }
  return documents.length ? 'Configured' : 'Waiting';
}

export const requestErrorMessage = (cause: unknown) =>
  cause instanceof Error ? cause.message : 'Request failed.';

export function editableIngestionVersion(
  version: IngestionPipelineVersion,
): IngestionPipelineDraft {
  return {
    kind: 'ingestion',
    name: version.name,
    execution: structuredClone(version.execution),
    layout: structuredClone(version.layout),
  };
}

export function upgradeIngestionDraft(draft: IngestionPipelineDraft): IngestionPipelineDraft {
  if (draft.execution.schema_version === 2) {
    return structuredClone(draft);
  }
  const upgraded = structuredClone(draft);
  upgraded.execution.schema_version = 2;
  upgraded.execution.nodes = upgraded.execution.nodes.map((node) => {
    if (node.type === 'extract') {
      return { ...node, strategy: 'native_text', config_version: 'native-text-v1' };
    }
    if (node.type === 'clean') {
      return {
        ...node,
        normalize_whitespace: node.normalize_whitespace ?? true,
        repeated_boilerplate: node.repeated_boilerplate ?? [],
        minimum_text_chars: node.minimum_text_chars ?? 1,
        maximum_text_chars: node.maximum_text_chars ?? 2_000_000,
        exact_content_deduplication: node.exact_content_deduplication ?? true,
        profile: 'standard-v1',
        config_version: 'deterministic-clean-v1',
      };
    }
    if (node.type === 'chunk') {
      return { ...node, config_version: 'character-window-v1' };
    }
    return node;
  });
  return upgraded;
}
