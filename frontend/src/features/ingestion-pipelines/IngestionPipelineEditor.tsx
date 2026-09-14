import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  useNodesState,
  type Node,
  type NodeChange,
  type NodeProps,
  type ReactFlowInstance,
  type Edge,
} from '@xyflow/react';
import { Check, CircleAlert, FileText, Play, Save, Square, X } from 'lucide-react';

import { useUnsavedChanges } from '../../app/navigation';
import { Pagination } from '../../components/Pagination';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../components/ui/native-select';
import { Textarea } from '../../components/ui/textarea';
import { allPages, type Page } from '../../lib/pagination';
import { listDocuments } from '../documents/api';
import { getEmbeddingSettings, listKnowledgeSets } from '../documents/indexApi';
import type { Document, EmbeddingConfig, KnowledgeSet } from '../documents/model';
import { getConnectionSettings, listConnections } from '../connections/api';
import type { ConnectionSettings, SourceConnection } from '../connections/model';
import * as api from './api';
import {
  canonicalIngestion,
  type ConfluenceConfig,
  type ExistingFilesConfig,
  type IngestionNode,
  type IngestionPipelineDraft,
  type IngestionPipelineVersion,
  type IngestionRun,
  type IngestionRunItem,
  type IngestionSchedule,
  type NotionConfig,
  type SourcePreview,
  type SourcePreviewItem,
  type S3Config,
  type WebsiteConfig,
} from './model';

type FlowData = { label: string; detail: string; first: boolean; last: boolean };
type FlowNode = Node<FlowData, 'ingestion'>;
const terminal = new Set(['succeeded', 'failed', 'cancelled']);
const labels: Record<IngestionNode['type'], string> = {
  source: 'Source',
  extract: 'Extract',
  clean: 'Clean',
  chunk: 'Chunk',
  embed: 'Embed',
  publish_index: 'Publish index',
};

const defaultWebsite = (): WebsiteConfig => ({
  kind: 'website',
  selection: { mode: 'crawl', start_url: 'https://example.com/' },
  allowed_origins: ['https://example.com'],
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

const defaultS3 = (connectionId = ''): S3Config => ({
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

const defaultNotion = (connectionId = ''): NotionConfig => ({
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

const defaultConfluence = (connectionId = ''): ConfluenceConfig => ({
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

async function loadConnectionState(projectId: string) {
  const settings = await getConnectionSettings(projectId);
  const connections = settings.enabled
    ? await allPages((offset) => listConnections(projectId, offset))
    : [];
  return { settings, connections };
}

const lines = (value: string) =>
  value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);

function IngestionFlowNode({ data, selected }: NodeProps<FlowNode>) {
  return (
    <div
      className={`workflow-node vertical-node w-80 border border-border rounded-[10px] bg-background text-foreground h-21 flex items-center gap-4 shadow-none py-4.5 px-5.5 ${selected ? 'workflow-selected border-primary outline-2 -outline-offset-1 outline-primary' : ''}`}
    >
      {!data.first && <Handle type="target" position={Position.Top} />}
      <FileText className="node-symbol shrink-0 text-muted-foreground" size={20} />
      <div className="node-copy min-w-0">
        <strong>{data.label}</strong>
        <div className="workflow-node-content p-0 text-xs wrap-anywhere mt-1 text-muted-foreground whitespace-nowrap overflow-hidden text-ellipsis">
          {data.detail}
        </div>
      </div>
      {!data.last && <Handle type="source" position={Position.Bottom} />}
    </div>
  );
}

const nodeTypes = { ingestion: IngestionFlowNode };

function defaultDraft(embedding: EmbeddingConfig, documentIds: string[]): IngestionPipelineDraft {
  const nodes: IngestionNode[] = [
    { id: 'source', type: 'source', config: { kind: 'existing_files', document_ids: documentIds } },
    { id: 'extract', type: 'extract', strategy: 'media_type_registry', config_version: '1' },
    {
      id: 'clean',
      type: 'clean',
      normalize_whitespace: true,
      repeated_boilerplate: [],
      minimum_text_chars: 1,
      maximum_text_chars: 2_000_000,
      exact_content_deduplication: true,
    },
    {
      id: 'chunk',
      type: 'chunk',
      algorithm: 'character_window',
      unit: 'characters',
      size: 1000,
      overlap: 100,
      config_version: '1',
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
      schema_version: 1,
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

function detail(node: IngestionNode, documents: Document[]) {
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
    return 'Supported source text';
  }
  if (node.type === 'clean') {
    return 'Normalize and deduplicate';
  }
  return documents.length ? 'Configured' : 'Waiting';
}

const message = (cause: unknown) => (cause instanceof Error ? cause.message : 'Request failed.');

function editableVersion(version: IngestionPipelineVersion): IngestionPipelineDraft {
  return {
    kind: 'ingestion',
    name: version.name,
    execution: structuredClone(version.execution),
    layout: structuredClone(version.layout),
  };
}

function WebsiteSettings({
  config,
  update,
}: {
  config: WebsiteConfig;
  update: (config: WebsiteConfig) => void;
}) {
  const selectionValue =
    config.selection.mode === 'url_list'
      ? config.selection.urls.join('\n')
      : config.selection.mode === 'single_url'
        ? config.selection.url
        : config.selection.mode === 'crawl'
          ? config.selection.start_url
          : config.selection.sitemap_url;
  const setSelection = (value: string) => {
    const selection =
      config.selection.mode === 'url_list'
        ? ({ mode: 'url_list', urls: lines(value) } as const)
        : config.selection.mode === 'single_url'
          ? ({ mode: 'single_url', url: value } as const)
          : config.selection.mode === 'crawl'
            ? ({ mode: 'crawl', start_url: value } as const)
            : ({ mode: 'sitemap', sitemap_url: value } as const);
    update({ ...config, selection });
  };
  const numberField = (
    key:
      | 'max_pages'
      | 'max_depth'
      | 'max_response_bytes'
      | 'max_total_bytes'
      | 'request_timeout_seconds'
      | 'deadline_seconds'
      | 'concurrency'
      | 'requests_per_second'
      | 'redirect_limit',
    label: string,
    min: number,
  ) => (
    <Label>
      {label}
      <Input
        type="number"
        min={min}
        value={config[key]}
        onChange={(event) => update({ ...config, [key]: Number(event.target.value) })}
      />
    </Label>
  );

  return (
    <>
      <div className="website-preview-notice">
        <CircleAlert size={17} />
        <p>
          Website runs fetch bounded HTML, preserve immutable revisions, and publish only after
          every required page succeeds. Preview the exact scope before saving.
        </p>
      </div>
      <Label>
        Discovery mode
        <NativeSelect
          value={config.selection.mode}
          onChange={(event) => {
            const mode = event.target.value;
            update({
              ...config,
              selection:
                mode === 'url_list'
                  ? { mode: 'url_list', urls: [] }
                  : mode === 'single_url'
                    ? { mode: 'single_url', url: '' }
                    : mode === 'sitemap'
                      ? { mode: 'sitemap', sitemap_url: '' }
                      : { mode: 'crawl', start_url: '' },
            });
          }}
        >
          <NativeSelectOption value="single_url">Single URL</NativeSelectOption>
          <NativeSelectOption value="url_list">URL list</NativeSelectOption>
          <NativeSelectOption value="crawl">Crawl from URL</NativeSelectOption>
          <NativeSelectOption value="sitemap">Sitemap</NativeSelectOption>
        </NativeSelect>
      </Label>
      <Label>
        {config.selection.mode === 'url_list' ? 'URLs (one per line)' : 'Starting URL'}
        {config.selection.mode === 'url_list' ? (
          <Textarea
            value={selectionValue}
            rows={4}
            onChange={(event) => setSelection(event.target.value)}
          />
        ) : (
          <Input
            type="url"
            value={selectionValue}
            onChange={(event) => setSelection(event.target.value)}
          />
        )}
      </Label>
      <Label>
        Allowed origins (one per line)
        <Textarea
          value={config.allowed_origins.join('\n')}
          rows={3}
          onChange={(event) => update({ ...config, allowed_origins: lines(event.target.value) })}
        />
      </Label>
      <Label>
        Include path prefixes (one per line)
        <Textarea
          value={(config.include_path_prefixes ?? []).join('\n')}
          rows={3}
          onChange={(event) =>
            update({ ...config, include_path_prefixes: lines(event.target.value) })
          }
        />
      </Label>
      <Label>
        Exclude path prefixes (one per line)
        <Textarea
          value={(config.exclude_path_prefixes ?? []).join('\n')}
          rows={3}
          onChange={(event) =>
            update({ ...config, exclude_path_prefixes: lines(event.target.value) })
          }
        />
      </Label>
      <div className="website-limit-grid">
        {numberField('max_pages', 'Maximum pages', 1)}
        {numberField('max_depth', 'Maximum crawl depth', 0)}
        {numberField('max_response_bytes', 'Bytes per response', 1)}
        {numberField('max_total_bytes', 'Total byte budget', 1)}
        {numberField('request_timeout_seconds', 'Request timeout (seconds)', 1)}
        {numberField('deadline_seconds', 'Preview deadline (seconds)', 1)}
        {numberField('concurrency', 'Concurrency', 1)}
        {numberField('requests_per_second', 'Requests per second', 0.1)}
        {numberField('redirect_limit', 'Redirect limit', 0)}
      </div>
      <Label>
        User agent
        <Input
          value={config.user_agent}
          onChange={(event) => update({ ...config, user_agent: event.target.value })}
        />
      </Label>
      <label className="website-checkbox">
        <input
          type="checkbox"
          checked={config.respect_robots ?? true}
          onChange={(event) => update({ ...config, respect_robots: event.target.checked })}
        />
        Respect robots.txt
      </label>
    </>
  );
}

function S3Settings({
  config,
  connections,
  projectId,
  update,
}: {
  config: S3Config;
  connections: SourceConnection[];
  projectId: string;
  update: (config: S3Config) => void;
}) {
  const s3Connections = connections.filter((connection) => connection.kind === 's3');
  const numberField = (
    key:
      | 'max_objects'
      | 'max_pages'
      | 'max_object_bytes'
      | 'max_total_bytes'
      | 'request_timeout_seconds',
    label: string,
    min: number,
  ) => (
    <Label>
      {label}
      <Input
        type="number"
        min={min}
        value={config[key]}
        onChange={(event) => update({ ...config, [key]: Number(event.target.value) })}
      />
    </Label>
  );
  return (
    <>
      <div className="website-preview-notice">
        <CircleAlert size={17} />
        <p>
          S3 reads only the selected bucket and prefix, accepts TXT/PDF, and publishes atomically
          after every required object succeeds.
        </p>
      </div>
      <Label>
        S3 connection
        <NativeSelect
          value={config.connection_id}
          onChange={(event) => update({ ...config, connection_id: event.target.value })}
        >
          <NativeSelectOption value="">Select an encrypted connection</NativeSelectOption>
          {s3Connections.map((connection) => (
            <NativeSelectOption key={connection.id} value={connection.id}>
              {connection.name} · {connection.status}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </Label>
      {s3Connections.length === 0 && (
        <p className="field-hint">
          No S3 connection is available.{' '}
          <a href={`#/projects/${projectId}/settings`}>Add one in project settings</a>.
        </p>
      )}
      <Label>
        AWS region
        <Input
          value={config.region}
          placeholder="us-east-1"
          onChange={(event) => update({ ...config, region: event.target.value })}
        />
      </Label>
      <Label>
        Bucket
        <Input
          value={config.bucket}
          placeholder="research-archive"
          onChange={(event) => update({ ...config, bucket: event.target.value })}
        />
      </Label>
      <Label>
        Prefix (optional)
        <Input
          value={config.prefix ?? ''}
          placeholder="documents/"
          onChange={(event) => update({ ...config, prefix: event.target.value })}
        />
      </Label>
      <Label>
        Expected AWS account ID (optional)
        <Input
          inputMode="numeric"
          value={config.expected_bucket_owner ?? ''}
          placeholder="123456789012"
          onChange={(event) =>
            update({ ...config, expected_bucket_owner: event.target.value || null })
          }
        />
      </Label>
      <fieldset className="s3-file-types">
        <legend>Allowed file types</legend>
        {(['txt', 'pdf'] as const).map((kind) => (
          <label key={kind}>
            <input
              type="checkbox"
              checked={config.allowed_file_types.includes(kind)}
              onChange={(event) =>
                update({
                  ...config,
                  allowed_file_types: event.target.checked
                    ? [...config.allowed_file_types, kind]
                    : config.allowed_file_types.filter((value) => value !== kind),
                })
              }
            />
            {kind.toUpperCase()}
          </label>
        ))}
      </fieldset>
      <div className="website-limit-grid">
        {numberField('max_objects', 'Maximum objects', 1)}
        {numberField('max_pages', 'Maximum list pages', 1)}
        {numberField('max_object_bytes', 'Bytes per object', 1024)}
        {numberField('max_total_bytes', 'Total byte budget', 1024)}
        {numberField('request_timeout_seconds', 'Request timeout (seconds)', 1)}
      </div>
    </>
  );
}

function NotionSettings({
  config,
  connections,
  projectId,
  update,
}: {
  config: NotionConfig;
  connections: SourceConnection[];
  projectId: string;
  update: (config: NotionConfig) => void;
}) {
  const notionConnections = connections.filter((connection) => connection.kind === 'notion');
  const selectionIds =
    config.selection.mode === 'pages'
      ? config.selection.page_ids.join('\n')
      : config.selection.mode === 'data_sources'
        ? config.selection.data_source_ids.join('\n')
        : '';
  const numberField = (
    key:
      | 'max_pages'
      | 'max_api_pages'
      | 'max_blocks_per_page'
      | 'max_block_depth'
      | 'max_text_chars'
      | 'request_timeout_seconds',
    label: string,
    min: number,
  ) => (
    <Label>
      {label}
      <Input
        type="number"
        min={min}
        value={config[key]}
        onChange={(event) => update({ ...config, [key]: Number(event.target.value) })}
      />
    </Label>
  );
  return (
    <>
      <div className="website-preview-notice">
        <CircleAlert size={17} />
        <p>
          Notion reads only content shared with the selected integration, extracts supported text
          blocks, and publishes only after every required page succeeds.
        </p>
      </div>
      <Label>
        Notion connection
        <NativeSelect
          value={config.connection_id}
          onChange={(event) => update({ ...config, connection_id: event.target.value })}
        >
          <NativeSelectOption value="">Select an encrypted connection</NativeSelectOption>
          {notionConnections.map((connection) => (
            <NativeSelectOption key={connection.id} value={connection.id}>
              {connection.name} · {connection.status}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </Label>
      {notionConnections.length === 0 && (
        <p className="field-hint">
          No Notion connection is available.{' '}
          <a href={`#/projects/${projectId}/settings`}>Add one in project settings</a>.
        </p>
      )}
      <Label>
        Discovery scope
        <NativeSelect
          value={config.selection.mode}
          onChange={(event) => {
            const mode = event.target.value;
            update({
              ...config,
              selection:
                mode === 'pages'
                  ? { mode: 'pages', page_ids: [] }
                  : mode === 'data_sources'
                    ? { mode: 'data_sources', data_source_ids: [] }
                    : { mode: 'workspace' },
            });
          }}
        >
          <NativeSelectOption value="workspace">
            All pages shared with integration
          </NativeSelectOption>
          <NativeSelectOption value="pages">Explicit page IDs</NativeSelectOption>
          <NativeSelectOption value="data_sources">Data source IDs</NativeSelectOption>
        </NativeSelect>
      </Label>
      {config.selection.mode !== 'workspace' && (
        <Label>
          {config.selection.mode === 'pages'
            ? 'Page IDs (one UUID per line)'
            : 'Data source IDs (one UUID per line)'}
          <Textarea
            rows={4}
            value={selectionIds}
            onChange={(event) => {
              const ids = lines(event.target.value);
              update({
                ...config,
                selection:
                  config.selection.mode === 'pages'
                    ? { mode: 'pages', page_ids: ids }
                    : { mode: 'data_sources', data_source_ids: ids },
              });
            }}
          />
        </Label>
      )}
      <div className="website-limit-grid">
        {numberField('max_pages', 'Maximum pages', 1)}
        {numberField('max_api_pages', 'Maximum API requests', 1)}
        {numberField('max_blocks_per_page', 'Blocks per page', 1)}
        {numberField('max_block_depth', 'Maximum block depth', 0)}
        {numberField('max_text_chars', 'Text characters per page', 100)}
        {numberField('request_timeout_seconds', 'Request timeout (seconds)', 1)}
      </div>
    </>
  );
}

function ConfluenceSettings({
  config,
  connections,
  projectId,
  update,
}: {
  config: ConfluenceConfig;
  connections: SourceConnection[];
  projectId: string;
  update: (config: ConfluenceConfig) => void;
}) {
  const available = connections.filter((connection) => connection.kind === 'confluence');
  const selectedIds =
    config.selection.mode === 'spaces'
      ? config.selection.space_ids.join('\n')
      : config.selection.mode === 'pages'
        ? config.selection.page_ids.join('\n')
        : '';
  const numberField = (
    key:
      | 'max_pages'
      | 'max_api_pages'
      | 'max_response_bytes'
      | 'max_text_chars'
      | 'request_timeout_seconds',
    label: string,
    min: number,
  ) => (
    <Label>
      {label}
      <Input
        type="number"
        min={min}
        value={config[key]}
        onChange={(event) => update({ ...config, [key]: Number(event.target.value) })}
      />
    </Label>
  );
  return (
    <>
      <div className="website-preview-notice">
        <CircleAlert size={17} />
        <p>
          Confluence reads only pages visible to the selected account. Credentials stay in the
          encrypted server vault, and a new index is published only after every included page
          succeeds.
        </p>
      </div>
      <Label>
        Confluence connection
        <NativeSelect
          value={config.connection_id}
          onChange={(event) => update({ ...config, connection_id: event.target.value })}
        >
          <NativeSelectOption value="">Select an encrypted connection</NativeSelectOption>
          {available.map((connection) => (
            <NativeSelectOption key={connection.id} value={connection.id}>
              {connection.name} · {connection.status}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </Label>
      {available.length === 0 && (
        <p className="field-hint">
          No Confluence connection is available.{' '}
          <a href={`#/projects/${projectId}/settings`}>Add one in project settings</a>.
        </p>
      )}
      <Label>
        Discovery scope
        <NativeSelect
          value={config.selection.mode}
          onChange={(event) =>
            update({
              ...config,
              selection:
                event.target.value === 'spaces'
                  ? { mode: 'spaces', space_ids: [] }
                  : event.target.value === 'pages'
                    ? { mode: 'pages', page_ids: [] }
                    : { mode: 'site' },
            })
          }
        >
          <NativeSelectOption value="site">All accessible current pages</NativeSelectOption>
          <NativeSelectOption value="spaces">Explicit space IDs</NativeSelectOption>
          <NativeSelectOption value="pages">Explicit page IDs</NativeSelectOption>
        </NativeSelect>
      </Label>
      {config.selection.mode !== 'site' && (
        <Label>
          {config.selection.mode === 'spaces'
            ? 'Space IDs (one numeric ID per line)'
            : 'Page IDs (one numeric ID per line)'}
          <Textarea
            rows={4}
            value={selectedIds}
            onChange={(event) => {
              const ids = lines(event.target.value);
              update({
                ...config,
                selection:
                  config.selection.mode === 'spaces'
                    ? { mode: 'spaces', space_ids: ids }
                    : { mode: 'pages', page_ids: ids },
              });
            }}
          />
        </Label>
      )}
      <Label>
        Included title prefixes (optional, one per line)
        <Textarea
          rows={3}
          value={config.title_prefixes.join('\n')}
          onChange={(event) => update({ ...config, title_prefixes: lines(event.target.value) })}
        />
      </Label>
      <Label>
        Excluded title prefixes (optional, one per line)
        <Textarea
          rows={3}
          value={config.exclude_title_prefixes.join('\n')}
          onChange={(event) =>
            update({ ...config, exclude_title_prefixes: lines(event.target.value) })
          }
        />
      </Label>
      <Label>
        Required label IDs (optional, one numeric ID per line)
        <Textarea
          rows={3}
          value={config.label_ids.join('\n')}
          onChange={(event) => update({ ...config, label_ids: lines(event.target.value) })}
        />
      </Label>
      <div className="website-limit-grid">
        {numberField('max_pages', 'Maximum pages', 1)}
        {numberField('max_api_pages', 'Maximum API requests', 1)}
        {numberField('max_response_bytes', 'Bytes per API response', 1024)}
        {numberField('max_text_chars', 'Text characters per page', 100)}
        {numberField('request_timeout_seconds', 'Request timeout (seconds)', 1)}
      </div>
    </>
  );
}

export function IngestionPipelineEditor({
  projectId,
  pipelineId,
  versionId = '',
}: {
  projectId: string;
  pipelineId: string;
  versionId?: string;
}) {
  const [draft, setDraft] = useState<IngestionPipelineDraft>();
  const [baseline, setBaseline] = useState('');
  const [versions, setVersions] = useState<IngestionPipelineVersion[]>([]);
  const [saved, setSaved] = useState<IngestionPipelineVersion>();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [knowledgeSets, setKnowledgeSets] = useState<KnowledgeSet[]>([]);
  const [connectionSettings, setConnectionSettings] = useState<ConnectionSettings>();
  const [connections, setConnections] = useState<SourceConnection[]>([]);
  const [selectedNode, setSelectedNode] = useState('source');
  const [preview, setPreview] = useState<SourcePreview>();
  const [previewPage, setPreviewPage] = useState<Page<SourcePreviewItem>>({
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
  });
  const [run, setRun] = useState<IngestionRun>();
  const [items, setItems] = useState<IngestionRunItem[]>([]);
  const [schedules, setSchedules] = useState<IngestionSchedule[]>([]);
  const [scheduleName, setScheduleName] = useState('Regular refresh');
  const [scheduleMinutes, setScheduleMinutes] = useState(1440);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const canvasRef = useRef<HTMLDivElement>(null);
  const [flow, setFlow] = useState<ReactFlowInstance<FlowNode, Edge>>();
  const [flowNodes, setFlowNodes, onFlowNodesChange] = useNodesState<FlowNode>([]);
  const dirty = !!draft && canonicalIngestion(draft) !== baseline;
  useUnsavedChanges(dirty);

  const open = useCallback(
    (version: IngestionPipelineVersion) => {
      const editable = editableVersion(version);
      setDraft(editable);
      setSaved(version);
      setBaseline(canonicalIngestion(editable));
      setPreview(undefined);
      setPreviewPage({ items: [], total: 0, limit: 20, offset: 0 });
      setRun(undefined);
      setItems([]);
      window.history.replaceState(
        null,
        '',
        `#/projects/${projectId}/pipelines/${version.pipeline_id}?kind=ingestion&version=${version.id}`,
      );
    },
    [projectId],
  );

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    void Promise.all([
      allPages((offset) => listDocuments(projectId, offset)),
      allPages((offset) => listKnowledgeSets(projectId, offset)),
      getEmbeddingSettings(projectId),
      loadConnectionState(projectId),
      pipelineId === 'new'
        ? Promise.resolve([] as IngestionPipelineVersion[])
        : allPages((offset) => api.listIngestionPipelineVersions(projectId, pipelineId, offset)),
    ])
      .then(([docs, sets, embedding, connectionState, savedVersions]) => {
        if (disposed) {
          return;
        }
        setDocuments(docs);
        setKnowledgeSets(sets);
        setConnectionSettings(connectionState.settings);
        setConnections(connectionState.connections);
        setVersions(savedVersions);
        if (!embedding.configured || !embedding.config) {
          throw new Error(
            embedding.error ||
              'Configure an embedding provider before creating ingestion pipelines.',
          );
        }
        if (pipelineId === 'new') {
          setDraft(defaultDraft(embedding.config, []));
          setBaseline('');
        } else {
          const target =
            savedVersions.find((version) => version.id === versionId) ?? savedVersions[0];
          if (!target) {
            throw new Error('No saved ingestion pipeline version was found.');
          }
          open(target);
        }
        setError('');
      })
      .catch((cause) => !disposed && setError(message(cause)))
      .finally(() => !disposed && setLoading(false));
    return () => {
      disposed = true;
    };
  }, [projectId, pipelineId, versionId, open]);

  useEffect(() => {
    let disposed = false;
    if (!saved) {
      setSchedules([]);
      return;
    }
    void allPages((offset) => api.listIngestionSchedules(projectId, offset))
      .then((values) => {
        if (!disposed) {
          setSchedules(values.filter((value) => value.pipeline_version_id === saved.id));
        }
      })
      .catch((cause) => !disposed && setError(message(cause)));
    return () => {
      disposed = true;
    };
  }, [projectId, saved]);

  useEffect(() => {
    if (!draft) {
      return;
    }
    const nodes = draft.execution.nodes.map((node, index) => ({
      id: node.id,
      type: 'ingestion' as const,
      position: draft.layout.positions[node.id],
      selected: node.id === selectedNode,
      data: {
        label:
          node.type === 'source'
            ? node.config.kind === 'website'
              ? 'Website'
              : node.config.kind === 's3'
                ? 'Amazon S3'
                : node.config.kind === 'notion'
                  ? 'Notion'
                  : node.config.kind === 'confluence'
                    ? 'Confluence'
                    : 'Existing files'
            : labels[node.type],
        detail: detail(node, documents),
        first: index === 0,
        last: index === draft.execution.nodes.length - 1,
      },
    }));
    setFlowNodes(nodes);
  }, [draft, documents, selectedNode, setFlowNodes]);

  const activeRunId = run?.id;
  const savedVersionId = saved?.id;

  useEffect(() => {
    if (!activeRunId) {
      setPollError('');
      return;
    }

    let disposed = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const next = await api.getIngestionRun(projectId, activeRunId);
        if (disposed) {
          return;
        }
        setRun((current) => (current?.id === activeRunId ? next : current));
        if (terminal.has(next.status)) {
          const nextItems = await allPages((offset) =>
            api.listIngestionRunItems(projectId, next.id, offset),
          );
          if (disposed) {
            return;
          }
          setItems(nextItems);
          if (savedVersionId) {
            const refreshed = await allPages((offset) =>
              api.listIngestionSchedules(projectId, offset),
            );
            if (disposed) {
              return;
            }
            setSchedules(refreshed.filter((value) => value.pipeline_version_id === savedVersionId));
          }
          setPollError('');
          return;
        }
        setPollError('');
        timer = window.setTimeout(() => void poll(), 1200);
      } catch (cause) {
        if (!disposed) {
          setPollError(message(cause));
          timer = window.setTimeout(() => void poll(), 1200);
        }
      }
    };

    timer = window.setTimeout(() => void poll(), 1200);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [activeRunId, projectId, savedVersionId]);

  useEffect(() => {
    if (!preview || terminal.has(preview.status)) {
      return;
    }
    const timer = window.setTimeout(() => {
      void api
        .getSourcePreview(projectId, preview.id)
        .then(async (next) => {
          setPreview(next);
          if (terminal.has(next.status)) {
            setPreviewPage(await api.listSourcePreviewItems(projectId, next.id));
          }
        })
        .catch((cause) => setError(message(cause)));
    }, 800);
    return () => window.clearTimeout(timer);
  }, [preview, projectId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !flow) {
      return;
    }
    let timer = 0;
    const observer = new ResizeObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        void flow.fitView({ padding: 0.14, maxZoom: 1 });
      }, 80);
    });
    observer.observe(canvas);
    return () => {
      observer.disconnect();
      window.clearTimeout(timer);
    };
  }, [flow]);

  const selected = draft?.execution.nodes.find((node) => node.id === selectedNode);
  const source = draft?.execution.nodes.find((node) => node.type === 'source');
  const validation = useMemo(() => {
    if (!draft) {
      return ['Loading configuration.'];
    }
    const reasons: string[] = [];
    if (!draft.name.trim()) {
      reasons.push('Enter a pipeline name.');
    }
    if (
      source?.type === 'source' &&
      source.config.kind === 'existing_files' &&
      source.config.document_ids.length === 0
    ) {
      reasons.push('Select at least one processed document.');
    }
    if (source?.type === 'source' && source.config.kind === 'website') {
      const selection = source.config.selection;
      const selectedUrls =
        selection.mode === 'url_list'
          ? selection.urls
          : [
              selection.mode === 'single_url'
                ? selection.url
                : selection.mode === 'crawl'
                  ? selection.start_url
                  : selection.sitemap_url,
            ];
      if (!selectedUrls.length || selectedUrls.some((url) => !url.trim())) {
        reasons.push('Enter at least one website URL.');
      }
      if (!source.config.allowed_origins.length) {
        reasons.push('Enter at least one allowed origin.');
      }
    }
    if (source?.type === 'source' && source.config.kind === 's3') {
      if (!connectionSettings?.enabled) {
        reasons.push('Enable the local encrypted connection vault before using S3.');
      }
      if (!source.config.connection_id) {
        reasons.push('Select an S3 connection.');
      }
      if (!source.config.region.trim()) {
        reasons.push('Enter an AWS region.');
      }
      if (!source.config.bucket.trim()) {
        reasons.push('Enter an S3 bucket.');
      }
      if (!source.config.allowed_file_types.length) {
        reasons.push('Allow TXT or PDF objects.');
      }
      if (source.config.max_total_bytes < source.config.max_object_bytes) {
        reasons.push('S3 total bytes must be at least the per-object limit.');
      }
    }
    if (source?.type === 'source' && source.config.kind === 'notion') {
      if (!connectionSettings?.enabled) {
        reasons.push('Enable the local encrypted connection vault before using Notion.');
      }
      if (!source.config.connection_id) {
        reasons.push('Select a Notion connection.');
      }
      if (
        (source.config.selection.mode === 'pages' &&
          source.config.selection.page_ids.length === 0) ||
        (source.config.selection.mode === 'data_sources' &&
          source.config.selection.data_source_ids.length === 0)
      ) {
        reasons.push('Enter at least one Notion page or data source ID.');
      }
    }
    if (source?.type === 'source' && source.config.kind === 'confluence') {
      if (!connectionSettings?.enabled) {
        reasons.push('Enable the local encrypted connection vault before using Confluence.');
      }
      if (!source.config.connection_id) {
        reasons.push('Select a Confluence connection.');
      }
      if (
        (source.config.selection.mode === 'spaces' &&
          source.config.selection.space_ids.length === 0) ||
        (source.config.selection.mode === 'pages' && source.config.selection.page_ids.length === 0)
      ) {
        reasons.push('Enter at least one Confluence space or page ID.');
      }
    }
    const chunk = draft.execution.nodes.find((node) => node.type === 'chunk');
    if (
      chunk?.type === 'chunk' &&
      (chunk.size < 100 || chunk.size > 10000 || chunk.overlap < 0 || chunk.overlap >= chunk.size)
    ) {
      reasons.push('Chunk size must be 100–10,000 and overlap must be smaller.');
    }
    return reasons;
  }, [connectionSettings, draft, source]);

  function updateNode(id: string, update: (node: IngestionNode) => IngestionNode) {
    setDraft((current) =>
      current
        ? {
            ...current,
            execution: {
              ...current.execution,
              nodes: current.execution.nodes.map((node) => (node.id === id ? update(node) : node)),
            },
          }
        : current,
    );
    setPreview(undefined);
  }

  function changeFlowNodes(changes: NodeChange<FlowNode>[]) {
    onFlowNodesChange(changes);
    const selectedChange = changes.find((change) => change.type === 'select' && change.selected);
    if (selectedChange?.type === 'select') {
      setSelectedNode(selectedChange.id);
    }
    const positions = changes.flatMap((change) =>
      change.type === 'position' && change.position
        ? [{ id: change.id, position: change.position }]
        : [],
    );
    if (positions.length) {
      setDraft((current) =>
        current
          ? {
              ...current,
              layout: {
                positions: {
                  ...current.layout.positions,
                  ...Object.fromEntries(positions.map((change) => [change.id, change.position])),
                },
              },
            }
          : current,
      );
    }
  }

  async function perform(work: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await work();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  function save() {
    if (!draft) {
      return;
    }
    void perform(async () => {
      const version = saved
        ? await api.createIngestionPipelineVersion(projectId, saved.pipeline_id, draft)
        : await api.createIngestionPipeline(projectId, draft);
      open(version);
      setVersions(
        await allPages((offset) =>
          api.listIngestionPipelineVersions(projectId, version.pipeline_id, offset),
        ),
      );
    });
  }

  function runPreview() {
    if (!draft) {
      return;
    }
    void perform(async () => {
      setPreviewPage({ items: [], total: 0, limit: 20, offset: 0 });
      setPreview(await api.previewIngestion(projectId, draft.execution));
    });
  }

  function loadPreviewPage(offset: number) {
    if (!preview) {
      return;
    }
    void perform(async () =>
      setPreviewPage(await api.listSourcePreviewItems(projectId, preview.id, offset)),
    );
  }

  function startRun() {
    if (!saved || dirty) {
      return;
    }
    void perform(async () => {
      setItems([]);
      setRun(await api.startIngestionRun(projectId, saved.pipeline_id, saved.id));
    });
  }

  function createSchedule() {
    if (!saved) {
      return;
    }
    void perform(async () => {
      const created = await api.createIngestionSchedule(projectId, {
        name: scheduleName,
        pipeline_id: saved.pipeline_id,
        pipeline_version_id: saved.id,
        cadence: { kind: 'interval', minutes: scheduleMinutes },
        enabled: false,
      });
      setSchedules((values) => [created, ...values]);
    });
  }

  function toggleSchedule(schedule: IngestionSchedule) {
    void perform(async () => {
      const changed = await api.updateIngestionSchedule(
        projectId,
        schedule,
        schedule.status !== 'enabled',
      );
      setSchedules((values) => values.map((value) => (value.id === changed.id ? changed : value)));
    });
  }

  function saveSchedule(schedule: IngestionSchedule) {
    void perform(async () => {
      const changed = await api.updateIngestionSchedule(
        projectId,
        schedule,
        schedule.status === 'enabled',
      );
      setSchedules((values) => values.map((value) => (value.id === changed.id ? changed : value)));
    });
  }

  function runSchedule(schedule: IngestionSchedule) {
    void perform(async () => setRun(await api.runIngestionSchedule(projectId, schedule.id)));
  }

  const websiteSource = source?.type === 'source' && source.config.kind === 'website';
  const s3Source = source?.type === 'source' && source.config.kind === 's3';
  const notionSource = source?.type === 'source' && source.config.kind === 'notion';
  const confluenceSource = source?.type === 'source' && source.config.kind === 'confluence';

  if (loading || !draft) {
    return <p role="status">Loading ingestion pipeline…</p>;
  }

  return (
    <div className="editor-workspace ingestion-editor">
      <a className="back-link" href={`#/projects/${projectId}/pipelines?kind=ingestion`}>
        All ingestion pipelines
      </a>
      <div className="editor-title">
        <h1>Ingestion editor</h1>
        <span>
          {websiteSource
            ? 'Website → ready index'
            : s3Source
              ? 'Amazon S3 → ready index'
              : notionSource
                ? 'Notion → ready index'
                : confluenceSource
                  ? 'Confluence → ready index'
                  : 'Existing files → ready index'}
        </span>
      </div>
      {(error || pollError) && (
        <p role="alert" className="error-message">
          {error || pollError}
        </p>
      )}
      <fieldset className="pipeline-fields" disabled={busy}>
        <div className="pipeline-toolbar flex flex-wrap m-0 gap-2.5 items-end border-b border-border py-3.5 px-5.5">
          <Label>
            Pipeline name
            <Input
              value={draft.name}
              maxLength={120}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
            />
          </Label>
          <Label>
            Saved version
            <NativeSelect
              aria-label="Saved ingestion version"
              value={saved?.id ?? ''}
              disabled={dirty}
              onChange={(event) => {
                const version = versions.find((item) => item.id === event.target.value);
                if (version) {
                  open(version);
                }
              }}
            >
              <NativeSelectOption value="">Not saved</NativeSelectOption>
              {versions.map((version) => (
                <NativeSelectOption key={version.id} value={version.id}>
                  Version {version.version}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Label>
          <span className={`draft-status ${dirty ? 'is-dirty' : ''}`} role="status">
            {dirty ? 'Unsaved changes' : saved ? `Saved version ${saved.version}` : 'Not saved'}
          </span>
          <Button onClick={save} disabled={validation.length > 0 || !dirty}>
            <Save size={15} />
            Save version
          </Button>
          <Button variant="outline" onClick={runPreview} disabled={validation.length > 0}>
            Preview source
          </Button>
          <Button onClick={startRun} disabled={!saved || dirty}>
            <Play size={15} />
            Run saved version
          </Button>
        </div>
        {validation.length > 0 && (
          <div
            className="pipeline-validation border-b border-border bg-background py-2 px-5"
            role="status"
          >
            <strong>Complete the configuration</strong>
            <ul>
              {validation.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="pipeline-editor ingestion-editor-grid">
          <div ref={canvasRef} className="pipeline-canvas" aria-label="Ingestion pipeline canvas">
            <ReactFlow<FlowNode, Edge>
              nodes={flowNodes}
              edges={draft.execution.edges.map((edge) => ({
                ...edge,
                id: `${edge.source}-${edge.target}`,
              }))}
              nodeTypes={nodeTypes}
              onInit={setFlow}
              onNodesChange={changeFlowNodes}
              onNodeClick={(_, node) => setSelectedNode(node.id)}
              nodesConnectable={false}
              deleteKeyCode={null}
              fitView
              fitViewOptions={{ padding: 0.12, maxZoom: 1 }}
            >
              <Background gap={22} size={1.2} />
              <Controls />
            </ReactFlow>
          </div>
          <aside id="node-settings" className="node-settings">
            <h2>
              {selected
                ? `${selected.type === 'source' ? (selected.config.kind === 'website' ? 'Website' : selected.config.kind === 's3' ? 'Amazon S3' : selected.config.kind === 'notion' ? 'Notion' : selected.config.kind === 'confluence' ? 'Confluence' : 'Existing files') : labels[selected.type]} settings`
                : 'Node settings'}
            </h2>
            {selected?.type === 'source' && (
              <div className="field-stack">
                <Label>
                  Source type
                  <NativeSelect
                    value={selected.config.kind}
                    onChange={(event) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'source'
                          ? {
                              ...node,
                              config:
                                event.target.value === 'website'
                                  ? defaultWebsite()
                                  : event.target.value === 's3'
                                    ? defaultS3(connections.find((item) => item.kind === 's3')?.id)
                                    : event.target.value === 'notion'
                                      ? defaultNotion(
                                          connections.find((item) => item.kind === 'notion')?.id,
                                        )
                                      : event.target.value === 'confluence'
                                        ? defaultConfluence(
                                            connections.find((item) => item.kind === 'confluence')
                                              ?.id,
                                          )
                                        : ({
                                            kind: 'existing_files',
                                            document_ids: [],
                                          } satisfies ExistingFilesConfig),
                            }
                          : node,
                      )
                    }
                  >
                    <NativeSelectOption value="existing_files">Existing files</NativeSelectOption>
                    <NativeSelectOption value="website">Website</NativeSelectOption>
                    {connectionSettings?.enabled && (
                      <>
                        <NativeSelectOption value="s3">Amazon S3</NativeSelectOption>
                        <NativeSelectOption value="notion">Notion</NativeSelectOption>
                        <NativeSelectOption value="confluence">Confluence</NativeSelectOption>
                      </>
                    )}
                  </NativeSelect>
                </Label>
                {selected.config.kind === 'existing_files' ? (
                  <>
                    <p className="field-hint">
                      Choose explicit project files. Only successfully processed files can run.
                    </p>
                    {documents.map((document) => {
                      const sourceConfig = selected.config as ExistingFilesConfig;
                      const checked = sourceConfig.document_ids.includes(document.id);
                      const disabled = document.latest_run?.status !== 'succeeded';
                      return (
                        <label className="ingestion-document-option" key={document.id}>
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={disabled}
                            onChange={(event) =>
                              updateNode(selected.id, (node) =>
                                node.type === 'source' && node.config.kind === 'existing_files'
                                  ? {
                                      ...node,
                                      config: {
                                        ...node.config,
                                        document_ids: event.target.checked
                                          ? [...node.config.document_ids, document.id]
                                          : node.config.document_ids.filter(
                                              (id: string) => id !== document.id,
                                            ),
                                      },
                                    }
                                  : node,
                              )
                            }
                          />
                          <span>
                            <strong>{document.filename}</strong>
                            <small>
                              {disabled
                                ? `Processing ${document.latest_run?.status ?? 'required'}`
                                : `${document.latest_run?.chunk_count ?? 0} chunks ready`}
                            </small>
                          </span>
                        </label>
                      );
                    })}
                    {documents.length === 0 && (
                      <p>No uploaded documents. Add and process files in Knowledge Base first.</p>
                    )}
                  </>
                ) : selected.config.kind === 'website' ? (
                  <WebsiteSettings
                    config={selected.config}
                    update={(config) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'source' ? { ...node, config } : node,
                      )
                    }
                  />
                ) : selected.config.kind === 's3' ? (
                  <S3Settings
                    config={selected.config}
                    connections={connections}
                    projectId={projectId}
                    update={(config) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'source' ? { ...node, config } : node,
                      )
                    }
                  />
                ) : selected.config.kind === 'notion' ? (
                  <NotionSettings
                    config={selected.config}
                    connections={connections}
                    projectId={projectId}
                    update={(config) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'source' ? { ...node, config } : node,
                      )
                    }
                  />
                ) : (
                  <ConfluenceSettings
                    config={selected.config}
                    connections={connections}
                    projectId={projectId}
                    update={(config) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'source' ? { ...node, config } : node,
                      )
                    }
                  />
                )}
              </div>
            )}
            {selected?.type === 'chunk' && (
              <div className="field-stack">
                <Label>
                  Chunk size (characters)
                  <Input
                    type="number"
                    min={100}
                    max={10000}
                    value={selected.size}
                    onChange={(event) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'chunk'
                          ? { ...node, size: Number(event.target.value) }
                          : node,
                      )
                    }
                  />
                </Label>
                <Label>
                  Overlap (characters)
                  <Input
                    type="number"
                    min={0}
                    value={selected.overlap}
                    onChange={(event) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'chunk'
                          ? { ...node, overlap: Number(event.target.value) }
                          : node,
                      )
                    }
                  />
                </Label>
              </div>
            )}
            {selected?.type === 'publish_index' && (
              <div className="field-stack">
                <Label>
                  Destination
                  <NativeSelect
                    value={selected.knowledge_set_id ?? ''}
                    onChange={(event) => {
                      const set = knowledgeSets.find((item) => item.id === event.target.value);
                      updateNode(selected.id, (node) =>
                        node.type === 'publish_index'
                          ? {
                              ...node,
                              knowledge_set_id: set?.id ?? null,
                              knowledge_set_name: set?.name ?? node.knowledge_set_name,
                            }
                          : node,
                      );
                    }}
                  >
                    <NativeSelectOption value="">Create a new knowledge set</NativeSelectOption>
                    {knowledgeSets.map((set) => (
                      <NativeSelectOption key={set.id} value={set.id}>
                        {set.name}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Label>
                {!selected.knowledge_set_id && (
                  <Label>
                    New knowledge set name
                    <Input
                      value={selected.knowledge_set_name}
                      maxLength={120}
                      onChange={(event) =>
                        updateNode(selected.id, (node) =>
                          node.type === 'publish_index'
                            ? { ...node, knowledge_set_name: event.target.value }
                            : node,
                        )
                      }
                    />
                  </Label>
                )}
              </div>
            )}
            {selected && !['source', 'chunk', 'publish_index'].includes(selected.type) && (
              <p className="field-hint">
                This deterministic stage uses the configured application implementation. Its exact
                settings are saved in the immutable version.
              </p>
            )}
          </aside>
        </div>
      </fieldset>
      {saved && (
        <section className="surface-section ingestion-results" aria-labelledby="schedule-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Automation</p>
              <h2 id="schedule-heading">Ingestion schedules</h2>
              <p>Schedules start paused and always run this exact immutable version.</p>
            </div>
          </div>
          <div className="pipeline-toolbar flex flex-wrap gap-2.5 items-end">
            <Label>
              Schedule name
              <Input
                value={scheduleName}
                onChange={(event) => setScheduleName(event.target.value)}
              />
            </Label>
            <Label>
              Interval (minutes)
              <Input
                type="number"
                min={15}
                max={10080}
                value={scheduleMinutes}
                onChange={(event) => setScheduleMinutes(Number(event.target.value))}
              />
            </Label>
            <Button
              variant="outline"
              onClick={createSchedule}
              disabled={!scheduleName.trim() || scheduleMinutes < 15 || scheduleMinutes > 10080}
            >
              Create paused schedule
            </Button>
          </div>
          {schedules.length === 0 ? (
            <p>No schedules target this saved version.</p>
          ) : (
            <ul className="project-list" aria-label="Ingestion schedules">
              {schedules.map((schedule) => (
                <li key={schedule.id}>
                  <div>
                    <Label>
                      Schedule name
                      <Input
                        value={schedule.name}
                        onChange={(event) =>
                          setSchedules((values) =>
                            values.map((value) =>
                              value.id === schedule.id
                                ? { ...value, name: event.target.value }
                                : value,
                            ),
                          )
                        }
                      />
                    </Label>
                    {schedule.cadence.kind === 'interval' && (
                      <Label>
                        Interval for {schedule.name} (minutes)
                        <Input
                          type="number"
                          min={15}
                          max={10080}
                          value={schedule.cadence.minutes}
                          onChange={(event) =>
                            setSchedules((values) =>
                              values.map((value) =>
                                value.id === schedule.id
                                  ? {
                                      ...value,
                                      cadence: {
                                        kind: 'interval',
                                        minutes: Number(event.target.value),
                                      },
                                    }
                                  : value,
                              ),
                            )
                          }
                        />
                      </Label>
                    )}
                    <p>
                      {schedule.status} ·{' '}
                      {schedule.cadence.kind === 'interval'
                        ? `every ${schedule.cadence.minutes} minutes`
                        : `daily at ${schedule.cadence.local_time} ${schedule.cadence.timezone}`}
                    </p>
                    <small>
                      Next:{' '}
                      {schedule.next_run_at
                        ? new Date(schedule.next_run_at).toLocaleString()
                        : 'paused'}{' '}
                      · Last: {schedule.last_outcome ?? 'never run'}
                    </small>
                    {schedule.last_error && <small>{schedule.last_error}</small>}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      onClick={() => saveSchedule(schedule)}
                      disabled={
                        !schedule.name.trim() ||
                        (schedule.cadence.kind === 'interval' &&
                          (schedule.cadence.minutes < 15 || schedule.cadence.minutes > 10080))
                      }
                    >
                      Save schedule
                    </Button>
                    <Button variant="outline" onClick={() => toggleSchedule(schedule)}>
                      {schedule.status === 'enabled' ? 'Pause' : 'Enable'}
                    </Button>
                    <Button variant="outline" onClick={() => runSchedule(schedule)}>
                      Run now
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      {preview && (
        <section className="surface-section ingestion-results" aria-live="polite">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Source preview</p>
              <h2>
                {preview.included_count} included · {preview.excluded_count} excluded
              </h2>
              <p>
                {preview.status} · {preview.progress}% · {preview.duplicate_count} duplicate ·{' '}
                {preview.failed_count} failed
              </p>
            </div>
            {!terminal.has(preview.status) && (
              <Button
                variant="outline"
                onClick={() =>
                  void perform(async () =>
                    setPreview(await api.cancelSourcePreview(projectId, preview.id)),
                  )
                }
              >
                <Square size={14} />
                Cancel preview
              </Button>
            )}
          </div>
          {preview.error && (
            <p role="alert" className="error-message">
              {preview.error}
            </p>
          )}
          <ul className="project-list">
            {previewPage.items.map((item) => (
              <li key={`${item.source_node_id}-${item.ordinal}`}>
                {item.status === 'included' ? <Check size={18} /> : <X size={18} />}
                <div>
                  <strong>{item.display_name}</strong>
                  <p>
                    {item.status} · {item.reason}
                    {item.depth !== null ? ` · depth ${item.depth}` : ''}
                    {item.size_bytes !== null ? ` · ${item.size_bytes} bytes` : ''}
                  </p>
                  {item.canonical_location && <small>{item.canonical_location}</small>}
                  {item.provider_revision && (
                    <small>Provider revision: {item.provider_revision}</small>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {terminal.has(preview.status) && previewPage.total === 0 && (
            <p>No preview items were discovered.</p>
          )}
          <Pagination
            offset={previewPage.offset}
            total={previewPage.total}
            pageSize={previewPage.limit}
            busy={busy}
            label="Source preview pages"
            onChange={loadPreviewPage}
          />
        </section>
      )}
      {run && (
        <section className="surface-section ingestion-results" aria-live="polite">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Ingestion run</p>
              <h2>
                {run.knowledge_set_name} · {run.status}
              </h2>
              <p>
                {run.stage} · {run.progress}% · {run.embedded_count}/{run.chunk_count} embedded
              </p>
              {(run.new_count > 0 ||
                run.changed_count > 0 ||
                run.unchanged_count > 0 ||
                run.removed_count > 0) && (
                <p>
                  {run.new_count} new · {run.changed_count} changed · {run.unchanged_count}{' '}
                  unchanged · {run.removed_count} removed
                </p>
              )}
            </div>
            {!terminal.has(run.status) && (
              <Button
                variant="outline"
                onClick={() =>
                  void perform(async () => setRun(await api.cancelIngestionRun(projectId, run.id)))
                }
              >
                <Square size={14} />
                Cancel
              </Button>
            )}
          </div>
          {run.error && (
            <p role="alert" className="error-message">
              {run.error}
            </p>
          )}
          {run.status === 'succeeded' && run.published_index_id && (
            <Button asChild variant="outline">
              <a
                href={`#/projects/${projectId}/knowledge-base?view=indexes&index=${run.published_index_id}`}
              >
                Inspect published index v{run.published_index_version}
              </a>
            </Button>
          )}
          <ul className="project-list">
            {items.map((item) => (
              <li key={item.source_kind !== 'existing_files' ? item.ordinal : item.document_id}>
                <FileText size={18} />
                <div>
                  {item.source_kind !== 'existing_files' ? (
                    <>
                      <strong>{item.display_name}</strong>
                      <p>
                        {item.outcome} · {item.status} · {item.chunk_count} chunks · {item.reason}
                      </p>
                      {item.canonical_location && <small>{item.canonical_location}</small>}
                    </>
                  ) : (
                    <>
                      <strong>{item.filename}</strong>
                      <p>
                        {item.status} · processing v{item.processing_version} · {item.chunk_count}{' '}
                        chunks · {item.content_hash.slice(0, 12)}
                      </p>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
