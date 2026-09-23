import { CircleAlert } from 'lucide-react';

import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { Textarea } from '../../../components/ui/textarea';
import type { SourceConnection } from '../../connections/model';
import type { ConfluenceConfig, NotionConfig, S3Config, WebsiteConfig } from '../model';

const lines = (value: string) =>
  value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);

export function WebsiteSettings({
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
    const selectedUrls = config.selection.mode === 'url_list' ? lines(value) : [value];
    const inferredOrigins = Array.from(
      new Set(
        selectedUrls.flatMap((url) => {
          try {
            return [new URL(url).origin];
          } catch {
            return [];
          }
        }),
      ),
    );
    const stillDefault =
      config.allowed_origins.length === 0 ||
      (config.allowed_origins.length === 1 && config.allowed_origins[0] === 'https://example.com');
    update({
      ...config,
      selection,
      allowed_origins:
        stillDefault && inferredOrigins.length ? inferredOrigins : config.allowed_origins,
    });
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
      <p className="field-hint">
        Choose the pages to ingest. Preview checks the scope; a run publishes an index after all
        required pages succeed.
      </p>
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
      <details className="ingestion-advanced">
        <summary>Scope & fetch limits · up to {config.max_pages} pages</summary>
        <div className="field-stack">
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
        </div>
      </details>
    </>
  );
}

export function S3Settings({
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

export function NotionSettings({
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

export function ConfluenceSettings({
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
