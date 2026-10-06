import { useId, useRef, useState, type ComponentProps } from 'react';

import { Callout, SUMMARY } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import { Checkbox } from '../../../components/ui/checkbox';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { Textarea } from '../../../components/ui/textarea';
import type { SourceConnection } from '../../connections/model';
import type { ConfluenceConfig, NotionConfig, S3Config, WebsiteConfig } from '../model';
import { derivedIncludePrefixes, folderStartUrl } from '../editorModel';
import {
  CHECK_ROW,
  DETAILS,
  FIELD_ERROR,
  FIELD_GRID,
  FIELDSET,
  HINT,
  STACK,
} from './settingsStyles';

const lines = (value: string) =>
  value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);

const websiteUrls = (selection: WebsiteConfig['selection']) =>
  selection.mode === 'url_list'
    ? selection.urls
    : [
        selection.mode === 'single_url'
          ? selection.url
          : selection.mode === 'crawl'
            ? selection.start_url
            : selection.sitemap_url,
      ];

const originsOf = (urls: string[]) =>
  Array.from(
    new Set(
      urls.flatMap((url) => {
        try {
          return [new URL(url).origin];
        } catch {
          return [];
        }
      }),
    ),
  );

const sameList = (left: string[], right: string[]) =>
  left.length === right.length && left.every((value, index) => value === right[index]);

/**
 * A one-per-line list field. It keeps the typed text, so Enter starts a new
 * line, and re-syncs only when the list changes outside the field.
 */
function LinesTextarea({
  value,
  onLines,
  ...props
}: { value: string[]; onLines: (value: string[]) => void } & Omit<
  ComponentProps<typeof Textarea>,
  'value' | 'onChange'
>) {
  const [text, setText] = useState(value.join('\n'));
  const [seen, setSeen] = useState(value);
  if (!sameList(seen, value)) {
    setSeen(value);
    if (!sameList(lines(text), value)) {
      setText(value.join('\n'));
    }
  }
  return (
    <Textarea
      {...props}
      value={text}
      onChange={(event) => {
        setText(event.target.value);
        onLines(lines(event.target.value));
      }}
    />
  );
}

const URL_LABEL = {
  single_url: 'Page URL',
  url_list: 'URLs (one per line)',
  crawl: 'Start URL',
  sitemap: 'Sitemap URL',
} as const;

const derivedPrefixes = (selection: WebsiteConfig['selection']) =>
  selection.mode === 'crawl' || selection.mode === 'sitemap'
    ? derivedIncludePrefixes(websiteUrls(selection)[0] ?? '')
    : [];

export function WebsiteSettings({
  config,
  update,
  fieldErrors = {},
}: {
  config: WebsiteConfig;
  update: (config: WebsiteConfig) => void;
  fieldErrors?: Record<string, string>;
}) {
  const fieldId = useId();
  const mode = config.selection.mode;
  const showPageLimit = mode !== 'single_url';
  const showPathFilters = mode === 'crawl' || mode === 'sitemap';
  // Without a trailing slash the derived scope is the parent folder, which is
  // usually wider than intended; say so while the prefix is still derived.
  const startUrl = mode === 'crawl' ? (websiteUrls(config.selection)[0] ?? '') : '';
  const slashedStart = folderStartUrl(startUrl);
  const widerScope =
    slashedStart !== null &&
    sameList(config.include_path_prefixes ?? [], derivedPrefixes(config.selection))
      ? (derivedPrefixes(config.selection)[0] ?? '/')
      : null;
  // Derived values follow the URL until the user edits them. The last derived
  // value is remembered, so a half-typed URL or a mode switch (which clears the
  // URL) does not count as an edit, and a deliberately cleared field stays so.
  // A config that arrives from outside (a saved version, Discard) re-seeds the
  // memory; the server returns origins with a trailing slash, so origins are
  // compared in normalized form.
  const derivedOrigins = useRef<string[] | null>(null);
  const derivedInclude = useRef<string[] | null>(null);
  const emitted = useRef<WebsiteConfig | null>(null);
  const seen = useRef<WebsiteConfig | null>(null);
  if (seen.current !== config) {
    if (emitted.current !== config) {
      const origins = originsOf(config.allowed_origins);
      derivedOrigins.current = sameList(origins, originsOf(websiteUrls(config.selection)))
        ? origins
        : null;
      const include = config.include_path_prefixes ?? [];
      derivedInclude.current = sameList(include, derivedPrefixes(config.selection))
        ? include
        : null;
    }
    seen.current = config;
  }
  const emit = (next: WebsiteConfig) => {
    emitted.current = next;
    update(next);
  };
  const setSelection = (selection: WebsiteConfig['selection']) => {
    const inferredOrigins = originsOf(websiteUrls(selection));
    const originsDerived =
      config.allowed_origins.length === 0 ||
      (derivedOrigins.current !== null &&
        sameList(originsOf(config.allowed_origins), derivedOrigins.current));
    const prefixesDerived =
      derivedInclude.current !== null &&
      sameList(config.include_path_prefixes ?? [], derivedInclude.current);
    let allowedOrigins = config.allowed_origins;
    if (originsDerived && inferredOrigins.length) {
      allowedOrigins = inferredOrigins;
      derivedOrigins.current = inferredOrigins;
    }
    let includePrefixes = config.include_path_prefixes;
    if (prefixesDerived) {
      includePrefixes = derivedPrefixes(selection);
      derivedInclude.current = includePrefixes;
    }
    emit({
      ...config,
      selection,
      allowed_origins: allowedOrigins,
      include_path_prefixes: includePrefixes,
    });
  };
  // The URL list field owns its text; this serves the single-URL input.
  const setUrlValue = (value: string) =>
    setSelection(
      mode === 'single_url'
        ? { mode: 'single_url', url: value }
        : mode === 'crawl'
          ? { mode: 'crawl', start_url: value }
          : { mode: 'sitemap', sitemap_url: value },
    );
  const numberField = (
    key: 'max_pages' | 'max_depth' | 'requests_per_second',
    label: string,
    bounds: { min: number; max: number; step?: number },
    hint?: string,
  ) => {
    const error = fieldErrors[`website.${key}`];
    const described = [hint && `${fieldId}-${key}-hint`, error && `${fieldId}-${key}-error`]
      .filter(Boolean)
      .join(' ');
    return (
      <div className="flex flex-col gap-2">
        <Label>
          {label}
          <Input
            type="number"
            min={bounds.min}
            max={bounds.max}
            step={bounds.step}
            aria-invalid={!!error}
            aria-describedby={described || undefined}
            value={config[key]}
            onChange={(event) => emit({ ...config, [key]: Number(event.target.value) })}
          />
        </Label>
        {hint && (
          <small id={`${fieldId}-${key}-hint`} className="text-xs text-foreground-muted">
            {hint}
          </small>
        )}
        {error && (
          <small id={`${fieldId}-${key}-error`} role="alert" className={FIELD_ERROR}>
            {error}
          </small>
        )}
      </div>
    );
  };

  return (
    <>
      <Label>
        Discovery mode
        <NativeSelect
          value={mode}
          onChange={(event) => {
            const next = event.target.value;
            setSelection(
              next === 'url_list'
                ? { mode: 'url_list', urls: [] }
                : next === 'single_url'
                  ? { mode: 'single_url', url: '' }
                  : next === 'sitemap'
                    ? { mode: 'sitemap', sitemap_url: '' }
                    : { mode: 'crawl', start_url: '' },
            );
          }}
        >
          <NativeSelectOption value="single_url">Single URL</NativeSelectOption>
          <NativeSelectOption value="url_list">URL list</NativeSelectOption>
          <NativeSelectOption value="crawl">Crawl from URL</NativeSelectOption>
          <NativeSelectOption value="sitemap">Sitemap</NativeSelectOption>
        </NativeSelect>
      </Label>
      <Label>
        {URL_LABEL[mode]}
        {mode === 'url_list' ? (
          <LinesTextarea
            value={websiteUrls(config.selection)}
            rows={4}
            onLines={(urls) => setSelection({ mode: 'url_list', urls })}
          />
        ) : (
          <Input
            type="url"
            value={websiteUrls(config.selection)[0]}
            aria-describedby={widerScope !== null ? `${fieldId}-slash` : undefined}
            onChange={(event) => setUrlValue(event.target.value)}
          />
        )}
      </Label>
      {widerScope !== null && slashedStart && (
        <div className="flex flex-col gap-2">
          <small id={`${fieldId}-slash`} role="status" className="text-xs text-warning">
            This URL has no trailing slash, so the crawl covers every page under{' '}
            <code>{widerScope}</code>. Add a slash to crawl only{' '}
            <code>{new URL(slashedStart).pathname}</code>.
          </small>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="self-start"
            onClick={() => setUrlValue(slashedStart)}
          >
            Add trailing slash
          </Button>
        </div>
      )}
      {showPageLimit && (
        <div className={FIELD_GRID}>
          {numberField('max_pages', 'Maximum pages', { min: 1, max: 1000 })}
          {mode === 'crawl' &&
            numberField(
              'max_depth',
              'Maximum crawl depth',
              { min: 0, max: 10 },
              'Link hops from the start URL; 0 fetches only that page.',
            )}
        </div>
      )}
      {showPathFilters && (
        <details className={DETAILS}>
          <summary className={SUMMARY}>Filter pages</summary>
          <div className={STACK}>
            <Label>
              Include path prefixes (one per line)
              <LinesTextarea
                value={config.include_path_prefixes ?? []}
                rows={3}
                onLines={(value) => emit({ ...config, include_path_prefixes: value })}
              />
            </Label>
            <small className="text-xs text-foreground-muted">
              Leave include empty to fetch every path on the allowed origins.
            </small>
            <Label>
              Exclude path prefixes (one per line)
              <LinesTextarea
                value={config.exclude_path_prefixes ?? []}
                rows={3}
                onLines={(value) => emit({ ...config, exclude_path_prefixes: value })}
              />
            </Label>
          </div>
        </details>
      )}
      <details className={DETAILS}>
        <summary className={SUMMARY}>Advanced</summary>
        <div className={STACK}>
          <Label>
            Allowed origins (one per line)
            <LinesTextarea
              value={config.allowed_origins}
              rows={3}
              onLines={(value) => emit({ ...config, allowed_origins: value })}
            />
          </Label>
          {showPageLimit &&
            numberField(
              'requests_per_second',
              'Crawl speed (requests per second)',
              { min: 0.1, max: 5, step: 0.1 },
              'Requests to the site never exceed this rate.',
            )}
        </div>
      </details>
      <details className={DETAILS}>
        <summary className={SUMMARY}>How website ingestion works</summary>
        <p className={HINT}>
          Choose the pages to ingest. Preview checks the scope; a run publishes an index after all
          required pages succeed. The server sets timeouts, byte budgets and robots.txt handling and
          shows the limits it used with each preview and run.
        </p>
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
      <Callout>
        <p>
          S3 reads only the selected bucket and prefix, accepts the explicitly selected supported
          formats, and publishes atomically after every required object succeeds.
        </p>
      </Callout>
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
        <p className={HINT}>
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
      <fieldset className={FIELDSET}>
        <legend>Allowed file types</legend>
        <div className="grid grid-cols-2 gap-x-4 md:grid-cols-3">
          {(['txt', 'pdf', 'md', 'html', 'docx', 'pptx', 'csv', 'tsv', 'xlsx'] as const).map(
            (kind) => (
              <label key={kind} className={CHECK_ROW}>
                <Checkbox
                  checked={config.allowed_file_types.includes(kind)}
                  onCheckedChange={(checked) =>
                    update({
                      ...config,
                      allowed_file_types:
                        checked === true
                          ? [...config.allowed_file_types, kind]
                          : config.allowed_file_types.filter((value) => value !== kind),
                    })
                  }
                />
                {kind.toUpperCase()}
              </label>
            ),
          )}
        </div>
      </fieldset>
      <div className={FIELD_GRID}>
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
      <Callout>
        <p>
          Notion reads only content shared with the selected integration, extracts supported text
          blocks, and publishes only after every required page succeeds.
        </p>
      </Callout>
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
        <p className={HINT}>
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
      <div className={FIELD_GRID}>
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
      <Callout>
        <p>
          Confluence reads only pages visible to the selected account. Credentials stay in the
          encrypted server vault, and a new index is published only after every included page
          succeeds.
        </p>
      </Callout>
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
        <p className={HINT}>
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
      <div className={FIELD_GRID}>
        {numberField('max_pages', 'Maximum pages', 1)}
        {numberField('max_api_pages', 'Maximum API requests', 1)}
        {numberField('max_response_bytes', 'Bytes per API response', 1024)}
        {numberField('max_text_chars', 'Text characters per page', 100)}
        {numberField('request_timeout_seconds', 'Request timeout (seconds)', 1)}
      </div>
    </>
  );
}
