import type { Document, EmbeddingConfig } from '../documents/model';
import type {
  ExtractionCapabilities,
  ChunkNode,
  ConfluenceConfig,
  DuplicatePolicy,
  IngestionNode,
  IngestionPipelineDraft,
  IngestionPipelineVersion,
  IngestionSchedule,
  LanguagePolicy,
  NotionConfig,
  QualityPolicy,
  SensitiveDataPolicy,
  S3Config,
  WebsiteConfig,
} from './model';

export const defaultLanguagePolicy: LanguagePolicy = {
  id: 'language-v1',
  detection_model: 'deterministic-script-v1',
  allowlist: [],
  minimum_confidence: 0,
  disallowed_action: 'fail',
  mixed_language_action: 'warn',
};

export const defaultDuplicatePolicy: DuplicatePolicy = {
  id: 'duplicate-v1',
  exact_raw: true,
  exact_cleaned: true,
  normalized_sections: true,
  near_duplicate: false,
  near_duplicate_method: 'simhash64',
  near_duplicate_threshold: 0.92,
  pinned_canonical_locations: [],
  connector_priority: ['existing_files', 'website', 's3', 'notion', 'confluence'],
};

export const defaultSensitiveDataPolicy: SensitiveDataPolicy = {
  id: 'sensitive-data-v1',
  enabled: true,
  detector_version: 'deterministic-patterns-v1',
  rules: ['email', 'phone', 'ip_address', 'government_id', 'payment_card', 'api_secret'].map(
    (entity_class) => ({
      entity_class: entity_class as SensitiveDataPolicy['rules'][number]['entity_class'],
      action: 'redact' as const,
    }),
  ),
  government_id_formats: ['us_ssn', 'in_aadhaar'],
};

export const terminalIngestionStatuses = new Set(['succeeded', 'failed', 'cancelled', 'expired']);

export const defaultQualityPolicy: QualityPolicy = {
  id: 'default-v1',
  thresholds: {
    maximum_empty_page_ratio: 0.2,
    maximum_replacement_character_ratio: 0.01,
    maximum_control_character_ratio: 0.001,
    minimum_ocr_confidence: 50,
    fail_on_suspicious_reading_order: false,
    fail_on_malformed_tables: true,
  },
  warning_action: 'publish',
  failed_item_action: 'fail',
};

export function fallbackQualityPolicy(id: QualityPolicy['id']): QualityPolicy {
  if (id === 'strict-v1') {
    return {
      id,
      thresholds: {
        maximum_empty_page_ratio: 0,
        maximum_replacement_character_ratio: 0.001,
        maximum_control_character_ratio: 0,
        minimum_ocr_confidence: 70,
        fail_on_suspicious_reading_order: true,
        fail_on_malformed_tables: true,
      },
      warning_action: 'fail',
      failed_item_action: 'fail',
    };
  }
  if (id === 'warn-v1') {
    return {
      ...structuredClone(defaultQualityPolicy),
      id,
      failed_item_action: 'exclude',
    };
  }
  return structuredClone(defaultQualityPolicy);
}

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
  include_path_prefixes: [],
  exclude_path_prefixes: [],
  max_pages: 50,
  max_depth: 3,
  requests_per_second: 2,
});

/** Include prefix implied by a start URL: `/docs/x` → `/docs/`; none for `/`. */
export function derivedIncludePrefixes(url: string): string[] {
  try {
    const path = new URL(url).pathname;
    const directory = path.slice(0, path.lastIndexOf('/') + 1);
    return directory && directory !== '/' ? [directory] : [];
  } catch {
    return [];
  }
}

/**
 * Server 422 issues that belong to a node field, keyed `ocr.<field>` or `website.<field>`.
 * With `nodes`, keys are prefixed `<node id>:` so each source shows only its own errors.
 */
export function serverFieldErrors(
  issues: { loc: (string | number)[]; msg: string }[],
  nodes?: { id: string }[],
): Record<string, string> {
  return Object.fromEntries(
    issues.flatMap((issue) => {
      const position = issue.loc[issue.loc.indexOf('nodes') + 1];
      const nodeId =
        nodes && issue.loc.includes('nodes') && typeof position === 'number'
          ? nodes[position]?.id
          : undefined;
      const prefix = nodeId ? `${nodeId}:` : '';
      const ocr = issue.loc.lastIndexOf('ocr');
      if (ocr >= 0) {
        const field = String(issue.loc[ocr + 1]);
        return ['dpi', 'max_pages', 'timeout_seconds'].includes(field)
          ? [[`${prefix}ocr.${field}`, issue.msg]]
          : [];
      }
      const website = issue.loc.lastIndexOf('website');
      const field = String(issue.loc[website + 1]);
      return website >= 0 && ['max_pages', 'max_depth', 'requests_per_second'].includes(field)
        ? [[`${prefix}website.${field}`, issue.msg]]
        : [];
    }),
  );
}

/** The field errors of one node: its prefixed errors plus any not tied to a node. */
export function fieldErrorsForNode(
  errors: Record<string, string>,
  nodeId: string,
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(errors).flatMap(([key, value]) => {
      const separator = key.indexOf(':');
      if (separator < 0) {
        return [[key, value]];
      }
      return key.slice(0, separator) === nodeId ? [[key.slice(separator + 1), value]] : [];
    }),
  );
}

/** Mirrors the server's limits for newly saved versions. */
export const maxWebsiteSources = 5;
export const maxWebsiteRunPages = 2500;

export function sourceNodes(draft: IngestionPipelineDraft) {
  return draft.execution.nodes.filter(
    (node): node is Extract<IngestionNode, { type: 'source' }> => node.type === 'source',
  );
}

/** "Website 2" when a pipeline has several sources, so messages and lists say which one. */
export function sourceLabel(draft: IngestionPipelineDraft, nodeId: string) {
  const sources = sourceNodes(draft);
  const index = sources.findIndex((node) => node.id === nodeId);
  const node = sources[index];
  const name =
    node?.config.kind === 'website'
      ? 'Website'
      : node?.config.kind === 's3'
        ? 'Amazon S3'
        : node?.config.kind === 'notion'
          ? 'Notion'
          : node?.config.kind === 'confluence'
            ? 'Confluence'
            : 'Existing files';
  return sources.length > 1 ? `${name} ${index + 1}` : name;
}

/** Why another Website source cannot be added, or null when it can. */
export function addWebsiteSourceBlocked(draft: IngestionPipelineDraft): string | null {
  const sources = sourceNodes(draft);
  if (draft.execution.schema_version !== 2) {
    return 'Upgrade this pipeline before adding sources.';
  }
  if (sources.some((node) => node.config.kind !== 'website')) {
    return 'Only Website sources can be combined for now.';
  }
  if (sources.length >= maxWebsiteSources) {
    return `A pipeline can read at most ${maxWebsiteSources} Website sources.`;
  }
  return null;
}

const chainTypes = ['extract', 'clean', 'chunk', 'embed', 'publish_index'] as const;
const rowHeight = 116;
// Node width (--spacing-node, 288px) plus a gap, so side-by-side sources never overlap.
const columnWidth = 340;

export function indexLayout(draft: IngestionPipelineDraft): 'merged' | 'per_source' {
  return draft.execution.index_layout ?? 'merged';
}

/** The nodes after a node, following edges: a source's own chain in a per-source layout. */
export function branchChain(draft: IngestionPipelineDraft, sourceId: string): IngestionNode[] {
  const byId = new Map(draft.execution.nodes.map((node) => [node.id, node]));
  const chain: IngestionNode[] = [];
  let current = sourceId;
  for (let step = 0; step < chainTypes.length; step += 1) {
    const edge = draft.execution.edges.find((candidate) => candidate.source === current);
    const node = edge ? byId.get(edge.target) : undefined;
    if (!node) {
      break;
    }
    chain.push(node);
    current = node.id;
  }
  return chain;
}

/** The source a node belongs to in a per-source layout. */
export function branchSourceOf(draft: IngestionPipelineDraft, nodeId: string): string | undefined {
  const byId = new Map(draft.execution.nodes.map((node) => [node.id, node]));
  let current = nodeId;
  for (let step = 0; step <= chainTypes.length; step += 1) {
    const node = byId.get(current);
    if (!node) {
      return undefined;
    }
    if (node.type === 'source') {
      return node.id;
    }
    const edge = draft.execution.edges.find((candidate) => candidate.target === current);
    if (!edge) {
      return undefined;
    }
    current = edge.source;
  }
  return undefined;
}

/** "Chunk · Website 2" for a branch stage when several sources publish separately. */
export function nodeLabel(draft: IngestionPipelineDraft, node: IngestionNode) {
  if (node.type === 'source') {
    return sourceLabel(draft, node.id);
  }
  const base = ingestionStageLabels[node.type];
  if (indexLayout(draft) !== 'per_source' || sourceNodes(draft).length < 2) {
    return base;
  }
  const sourceId = branchSourceOf(draft, node.id);
  return sourceId ? `${base} · ${sourceLabel(draft, sourceId)}` : base;
}

function hostOf(node: IngestionNode) {
  if (node.type !== 'source' || node.config.kind !== 'website') {
    return null;
  }
  const selection = node.config.selection;
  const url =
    selection.mode === 'url_list'
      ? selection.urls[0]
      : selection.mode === 'single_url'
        ? selection.url
        : selection.mode === 'crawl'
          ? selection.start_url
          : selection.sitemap_url;
  try {
    return url ? new URL(url).host : null;
  } catch {
    return null;
  }
}

/** Default index name of a branch: "<pipeline> · <host>", or "· Website N" without a URL. */
export function branchIndexName(
  draft: IngestionPipelineDraft,
  source: IngestionNode,
  number: number,
) {
  const pipeline = draft.name.trim() || 'Ingested knowledge';
  return `${pipeline} · ${hostOf(source) ?? `Website ${number}`}`;
}

function uniqueId(ids: Set<string>, base: string) {
  let number = 2;
  while (ids.has(`${base}-${number}`)) {
    number += 1;
  }
  const id = `${base}-${number}`;
  ids.add(id);
  return id;
}

function withIndexName(node: IngestionNode, name: string): IngestionNode {
  if (node.type !== 'publish_index') {
    return node;
  }
  // A new branch publishes to a new index; it never reuses another branch's index.
  const { knowledge_set_id: _ignored, ...rest } = node;
  void _ignored;
  return { ...rest, knowledge_set_name: name };
}

function copyChain(template: IngestionNode[], ids: Set<string>, name: string): IngestionNode[] {
  return template.map((node) =>
    withIndexName(
      {
        ...structuredClone(node),
        id: uniqueId(ids, node.type === 'publish_index' ? 'publish' : node.type),
      },
      name,
    ),
  );
}

function chainEdges(chain: IngestionNode[]) {
  return chain.slice(1).map((node, index) => ({ source: chain[index].id, target: node.id }));
}

function columnPositions(
  chain: IngestionNode[],
  origin: { x: number; y: number },
): Record<string, { x: number; y: number }> {
  return Object.fromEntries(
    chain.map((node, index) => [node.id, { x: origin.x, y: origin.y + index * rowHeight }]),
  );
}

/**
 * Switches between one shared chain and one chain per source. Branches copy the shared
 * settings; switching back keeps the first branch's settings. Every new chain publishes
 * to a newly named index.
 */
export function setIndexLayout(
  draft: IngestionPipelineDraft,
  layout: 'merged' | 'per_source',
): IngestionPipelineDraft {
  if (draft.execution.schema_version !== 2 || indexLayout(draft) === layout) {
    return draft;
  }
  const sources = sourceNodes(draft);
  const positions: Record<string, { x: number; y: number }> = {};
  const origin = (source: IngestionNode, index: number) =>
    draft.layout.positions[source.id] ?? { x: 90 + index * columnWidth, y: 40 };
  if (layout === 'per_source') {
    const template = chainTypes.map(
      (type) => draft.execution.nodes.find((node) => node.type === type) as IngestionNode,
    );
    const ids = new Set(draft.execution.nodes.map((node) => node.id));
    const nodes: IngestionNode[] = [];
    const edges: { source: string; target: string }[] = [];
    sources.forEach((source, index) => {
      const name = branchIndexName(draft, source, index + 1);
      const chain =
        index === 0
          ? template.map((node) => withIndexName(node, name))
          : copyChain(template, ids, name);
      nodes.push(source, ...chain);
      edges.push(...chainEdges([source, ...chain]));
      Object.assign(positions, columnPositions([source, ...chain], origin(source, index)));
    });
    return {
      ...draft,
      execution: { ...draft.execution, index_layout: 'per_source', nodes, edges },
      layout: { positions },
    };
  }
  const first = sources[0];
  const chain = branchChain(draft, first.id).map((node) =>
    withIndexName(node, draft.name.trim() || 'Ingested knowledge'),
  );
  sources.forEach((source, index) => {
    positions[source.id] = origin(source, index);
  });
  Object.assign(positions, columnPositions([first, ...chain], origin(first, 0)));
  return {
    ...draft,
    execution: {
      ...draft.execution,
      index_layout: 'merged',
      nodes: [...sources, ...chain],
      edges: [
        ...sources.map((source) => ({ source: source.id, target: chain[0].id })),
        ...chainEdges(chain),
      ],
    },
    layout: { positions },
  };
}

/** One branch as a single-chain execution, for previewing a per-source layout. */
export function branchExecution(
  draft: IngestionPipelineDraft,
  sourceId: string,
): IngestionPipelineDraft['execution'] {
  const source = draft.execution.nodes.find((node) => node.id === sourceId);
  const chain = source ? [source, ...branchChain(draft, sourceId)] : [];
  return { schema_version: 2, index_layout: 'merged', nodes: chain, edges: chainEdges(chain) };
}

/**
 * Adds a Website source beside the others: wired into the shared Extract stage, or in a
 * per-source layout given its own copy of the first branch's stages and a new index.
 */
export function addWebsiteSource(draft: IngestionPipelineDraft): {
  draft: IngestionPipelineDraft;
  nodeId: string;
} {
  const sources = sourceNodes(draft);
  const ids = new Set(draft.execution.nodes.map((node) => node.id));
  let number = sources.length + 1;
  while (ids.has(`source-${number}`)) {
    number += 1;
  }
  const nodeId = `source-${number}`;
  ids.add(nodeId);
  const source: IngestionNode = { id: nodeId, type: 'source', config: defaultWebsite() };
  const last = sources[sources.length - 1];
  const lastPosition = last ? draft.layout.positions[last.id] : undefined;
  const position = lastPosition
    ? { x: lastPosition.x + columnWidth, y: lastPosition.y }
    : { x: 90, y: 40 };
  if (indexLayout(draft) === 'per_source') {
    const chain = copyChain(
      branchChain(draft, sources[0].id),
      ids,
      branchIndexName(draft, source, sources.length + 1),
    );
    return {
      nodeId,
      draft: {
        ...draft,
        execution: {
          ...draft.execution,
          nodes: [...draft.execution.nodes, source, ...chain],
          edges: [...draft.execution.edges, ...chainEdges([source, ...chain])],
        },
        layout: {
          positions: {
            ...draft.layout.positions,
            ...columnPositions([source, ...chain], position),
          },
        },
      },
    };
  }
  const extract = draft.execution.nodes.find((node) => node.type === 'extract');
  const lastSourceIndex = draft.execution.nodes.findIndex((node) => node.id === last?.id);
  const nodes = [...draft.execution.nodes];
  nodes.splice(lastSourceIndex + 1, 0, source);
  return {
    nodeId,
    draft: {
      ...draft,
      execution: {
        ...draft.execution,
        nodes,
        edges: extract
          ? [...draft.execution.edges, { source: nodeId, target: extract.id }]
          : draft.execution.edges,
      },
      layout: { positions: { ...draft.layout.positions, [nodeId]: position } },
    },
  };
}

/** Removes one of several sources (with its own stages in a per-source layout). */
export function removeSource(
  draft: IngestionPipelineDraft,
  nodeId: string,
): IngestionPipelineDraft {
  if (sourceNodes(draft).length < 2) {
    return draft;
  }
  const removed = new Set([
    nodeId,
    ...(indexLayout(draft) === 'per_source'
      ? branchChain(draft, nodeId).map((node) => node.id)
      : []),
  ]);
  const positions = Object.fromEntries(
    Object.entries(draft.layout.positions).filter(([id]) => !removed.has(id)),
  );
  return {
    ...draft,
    execution: {
      ...draft.execution,
      nodes: draft.execution.nodes.filter((node) => !removed.has(node.id)),
      edges: draft.execution.edges.filter(
        (edge) => !removed.has(edge.source) && !removed.has(edge.target),
      ),
    },
    layout: { positions },
  };
}

/** Sum of every Website source's Maximum pages. */
export function websitePageTotal(draft: IngestionPipelineDraft) {
  return sourceNodes(draft).reduce(
    (total, node) => total + (node.config.kind === 'website' ? node.config.max_pages : 0),
    0,
  );
}

/** The start URL with a trailing slash when its last segment looks like a folder. */
export function folderStartUrl(url: string): string | null {
  try {
    const parsed = new URL(url);
    const last = parsed.pathname.slice(parsed.pathname.lastIndexOf('/') + 1);
    if (!last || last.includes('.')) {
      return null;
    }
    parsed.pathname += '/';
    return parsed.toString();
  } catch {
    return null;
  }
}

export const defaultS3 = (connectionId = ''): S3Config => ({
  kind: 's3',
  connection_id: connectionId,
  region: 'us-east-1',
  bucket: '',
  prefix: '',
  expected_bucket_owner: null,
  allowed_file_types: ['txt', 'pdf', 'md', 'html', 'docx', 'pptx', 'csv', 'tsv', 'xlsx'],
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

function numberSetting(
  settings: Record<string, string | number | boolean> | undefined,
  key: string,
  fallback: number,
) {
  const value = settings?.[key];
  return typeof value === 'number' ? value : fallback;
}

function defaultChunk(capabilities?: ExtractionCapabilities): ChunkNode {
  const settings = capabilities?.chunking_profiles?.find(
    (profile) => profile.id === 'section_token' && profile.recommended,
  )?.settings;
  return {
    id: 'chunk',
    type: 'chunk',
    algorithm: 'section_token',
    unit: 'tokens',
    tokenizer_version: 'utf8-byte-v1',
    target_tokens: numberSetting(settings, 'target_tokens', 600),
    maximum_tokens: numberSetting(settings, 'maximum_tokens', 800),
    overlap_tokens: numberSetting(settings, 'overlap_tokens', 80),
    add_heading_context:
      typeof settings?.add_heading_context === 'boolean' ? settings.add_heading_context : true,
    config_version: 'section-token-v1',
  };
}

export function defaultIngestionDraft(
  embedding: EmbeddingConfig,
  documentIds: string[],
  capabilities?: ExtractionCapabilities,
): IngestionPipelineDraft {
  const cleaningProfile = capabilities?.cleaning_profiles?.[0];
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
      quality_policy: structuredClone(
        capabilities?.quality_policies.find((value) => value.id === 'default-v1')?.settings ??
          defaultQualityPolicy,
      ),
      language_policy: structuredClone(defaultLanguagePolicy),
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
      profile: cleaningProfile?.id ?? 'standard-v1',
      config_version: cleaningProfile?.config_version ?? 'deterministic-clean-v1',
      steps: structuredClone(cleaningProfile?.steps ?? []),
      duplicate_policy: structuredClone(defaultDuplicatePolicy),
      sensitive_data_policy: structuredClone(defaultSensitiveDataPolicy),
    },
    defaultChunk(capabilities),
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
      index_layout: 'merged',
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
    if (node.algorithm === 'section_token') {
      return `Section-aware · ${node.target_tokens} target · ${node.maximum_tokens} max tokens`;
    }
    if (node.algorithm === 'parent_child') {
      return `Parent/child · ${node.child_target_tokens} child · ${node.parent_target_tokens} parent`;
    }
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
    return node.profile === 'structure-aware-v1'
      ? `${node.steps?.filter((step) => step.enabled).length ?? 0} ordered transforms`
      : 'Normalize and deduplicate';
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
      return {
        ...node,
        strategy: 'native_text',
        language_policy: structuredClone(defaultLanguagePolicy),
        config_version: 'native-text-v1',
      };
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
        duplicate_policy: structuredClone(defaultDuplicatePolicy),
        config_version: 'deterministic-clean-v1',
      };
    }
    if (node.type === 'chunk') {
      return (node.algorithm ?? 'character_window') === 'character_window'
        ? { ...node, config_version: 'character-window-v1' }
        : node;
    }
    return node;
  });
  return upgraded;
}
