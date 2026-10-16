import { useEffect, useId, useRef, useState, type ComponentProps, type ReactNode } from 'react';

import { Callout, SUMMARY } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import { Checkbox } from '../../../components/ui/checkbox';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { Textarea } from '../../../components/ui/textarea';
import type { SourceConnection } from '../../connections/model';
import type {
  ConfluenceConfig,
  NotionConfig,
  S3Config,
  SettingRecommendation,
  SettingsProvenance,
  WebsiteConfig,
  WebsiteSelection,
} from '../model';
import { derivedIncludePrefixes, folderStartUrl } from '../editorModel';
import {
  addressSelection,
  analysableSelection,
  applyRecommendation,
  effectiveStatus,
  enteredSelection,
  isStale,
  recommendationMatches,
  resetToRecommended,
  selectionKey,
  selectionUrls,
} from '../recommendationsModel';
import { useWebsiteRecommendation } from '../useWebsiteRecommendation';
import { WebsiteRecommendations, type RecommendationCardView } from './WebsiteRecommendations';
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

/**
 * Recommended settings for one Website source (spec 0011). Passed only while the server
 * enables them; without it the form is exactly the manual one.
 */
export type WebsiteRecommendationContext = {
  projectId: string;
  nodeId: string;
  /** Maximum pages of the draft's other Website sources. */
  otherSourcesMaxPages: number;
  /** The recommendation already applied to this source in the draft. */
  applied?: SettingRecommendation;
  onApplied: (recommendation: SettingRecommendation) => void;
  /** A viewer sees recommendations but cannot start, cancel or apply them. */
  readOnly?: boolean;
  /** What the open saved version recorded for this source, when it recorded anything. */
  provenance?: SettingsProvenance['nodes'][string];
  savedVersion?: number;
  /** Changes when another saved version opens, so the card starts again from it. */
  versionKey?: string;
};

const ADDRESS_HINT =
  'Enter a page, a section or a sitemap. Settings are recommended from the site.';

const finished = (value?: SettingRecommendation): value is SettingRecommendation =>
  value?.status === 'succeeded' || value?.status === 'expired';

export function WebsiteSettings({
  config,
  update,
  fieldErrors = {},
  recommendations,
}: {
  config: WebsiteConfig;
  update: (config: WebsiteConfig) => void;
  fieldErrors?: Record<string, string>;
  recommendations?: WebsiteRecommendationContext;
}) {
  const fieldId = useId();
  const formId = `${fieldId}-settings`;
  const formRef = useRef<HTMLDivElement>(null);
  const [editing, setEditing] = useState(false);
  const analysis = useWebsiteRecommendation(
    recommendations?.projectId ?? '',
    recommendations?.nodeId ?? '',
  );
  const lastAnalysed = useRef<string | null>(null);
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
  // Pre-fill once per succeeded recommendation for the address now in the form.
  const appliedId = useRef(recommendations?.applied?.id ?? null);
  const latest = analysis.recommendation;
  useEffect(() => {
    if (
      !recommendations ||
      !latest ||
      latest.status !== 'succeeded' ||
      appliedId.current === latest.id ||
      !recommendationMatches(config, latest)
    ) {
      return;
    }
    appliedId.current = latest.id;
    emit(applyRecommendation(config, latest, recommendations.applied));
    recommendations.onApplied(latest);
    // Runs when a new recommendation arrives; config is read at that moment.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latest]);

  // What the card shows: the running analysis, its failure, the recommendation this
  // source uses (the latest finished one, else the one applied in the draft), or what
  // the saved version recorded.
  const readOnly = !!recommendations?.readOnly;
  const otherPages = recommendations?.otherSourcesMaxPages ?? 0;
  const described = recommendations ? [latest, recommendations.applied].find(finished) : undefined;
  const stale = !!described && isStale(config, described, otherPages);
  let view: RecommendationCardView | null = null;
  if (recommendations) {
    if (analysis.analysing) {
      view = { kind: 'analysing', recommendation: latest };
    } else if (analysis.error) {
      view = { kind: 'failed', message: analysis.error };
    } else if (latest?.status === 'failed') {
      view = { kind: 'failed', message: latest.error ?? 'The site check did not finish.' };
    } else if (latest?.status === 'cancelled') {
      view = { kind: 'cancelled' };
    } else if (described) {
      view = {
        kind: 'live',
        recommendation: described,
        stale,
        expired: effectiveStatus(described) === 'expired',
      };
    } else if (recommendations.provenance?.status === 'applied') {
      view = {
        kind: 'saved',
        provenance: recommendations.provenance,
        version: recommendations.savedVersion,
      };
    }
  }
  const current = view?.kind === 'live' && !stale;
  const hasFieldErrors = Object.keys(fieldErrors).some((key) => key.startsWith('website.'));
  // The form folds behind Edit only while a current recommendation fills it; a server
  // error on one of its fields keeps it open.
  const collapsible = current && !readOnly && !hasFieldErrors;
  const formHidden = collapsible && !editing;
  // The address the user entered: the analysed input while the draft reads the
  // sitemap the recommendation chose for it.
  const entered = recommendations ? enteredSelection(config, described) : config.selection;
  const analyse = (
    selection: WebsiteSelection,
    { force = false, refresh = false }: { force?: boolean; refresh?: boolean } = {},
  ) => {
    const valid = analysableSelection(selection);
    if (!recommendations || readOnly || !valid) {
      return;
    }
    const key = `${selectionKey(valid)}|${otherPages}`;
    if (!force) {
      const describedKey = described
        ? `${selectionKey(described.inputs.selection)}|${described.inputs.other_sources_max_pages}`
        : null;
      const recorded = recommendations.provenance?.entered_url;
      if (
        key === lastAnalysed.current ||
        key === describedKey ||
        (!described &&
          !!recorded &&
          selectionKey(valid) === selectionKey(addressSelection(recorded)))
      ) {
        return;
      }
    }
    lastAnalysed.current = key;
    void analysis.start(valid, otherPages, refresh);
  };
  // Analysis starts when a valid address is committed: blur, Enter or paste.
  const urlHandlers: Partial<ComponentProps<typeof Input>> = recommendations
    ? {
        onBlur: (event) => analyse(addressSelection(event.target.value, entered.mode)),
        onKeyDown: (event) => {
          if (event.key === 'Enter') {
            analyse(addressSelection(event.currentTarget.value, entered.mode));
          }
        },
        onPaste: (event) => {
          const text = event.clipboardData.getData('text');
          const pasted = addressSelection(text, entered.mode);
          if (pasted.mode === 'url_list') {
            // A multi-line paste is a URL list; a one-line field would drop the breaks.
            event.preventDefault();
            setSelection(pasted);
          }
          analyse(pasted);
        },
      }
    : {};
  const toggleEdit = () => {
    const opening = !editing;
    setEditing(opening);
    if (opening) {
      window.requestAnimationFrame(() =>
        formRef.current?.querySelector<HTMLElement>('input, textarea, select')?.focus(),
      );
    }
  };
  // With recommendations on, the fields below the address form one region that the
  // card's Edit button opens; otherwise they render exactly as before.
  const settingsRegion = (children: ReactNode) =>
    recommendations ? (
      <div id={formId} ref={formRef} hidden={formHidden} className="flex flex-col gap-6">
        {children}
      </div>
    ) : (
      children
    );
  function setSelection(selection: WebsiteConfig['selection']) {
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
  }
  // The URL list field owns its text; this serves the single-URL input.
  const setUrlValue = (value: string) =>
    setSelection(
      mode === 'single_url'
        ? { mode: 'single_url', url: value }
        : mode === 'crawl'
          ? { mode: 'crawl', start_url: value }
          : { mode: 'sitemap', sitemap_url: value },
    );
  // Recommendations on: a discovery change keeps the entered address.
  const discoveryFor = (next: string): WebsiteSelection => {
    const urls = selectionUrls(entered).filter(Boolean);
    const recommended = described?.recommended?.selection;
    if (next === 'url_list') {
      return { mode: 'url_list', urls };
    }
    if (next === 'single_url') {
      return { mode: 'single_url', url: urls[0] ?? '' };
    }
    if (next === 'sitemap') {
      return {
        mode: 'sitemap',
        sitemap_url: recommended?.mode === 'sitemap' ? recommended.sitemap_url : (urls[0] ?? ''),
      };
    }
    return { mode: 'crawl', start_url: urls[0] ?? '' };
  };
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

  const discoverySelect = (
    <Label>
      Discovery mode
      <NativeSelect
        value={mode}
        onChange={(event) => {
          const next = event.target.value;
          if (recommendations) {
            setSelection(discoveryFor(next));
            return;
          }
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
  );
  const slashAdvisory = widerScope !== null && slashedStart && !current && (
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
  );
  const slashId = slashAdvisory ? `${fieldId}-slash` : undefined;
  const addressHintId = `${fieldId}-address-hint`;
  const addressDescribedBy = [addressHintId, slashId].filter(Boolean).join(' ');

  return (
    <>
      {recommendations ? (
        <div className="flex flex-col gap-2">
          <Label>
            Website address
            {entered.mode === 'url_list' ? (
              <LinesTextarea
                value={entered.urls}
                rows={4}
                aria-describedby={addressDescribedBy}
                onLines={(urls) => setSelection({ mode: 'url_list', urls })}
                onBlur={(event) => analyse(addressSelection(event.target.value, 'url_list'))}
              />
            ) : (
              <Input
                type="url"
                value={selectionUrls(entered)[0]}
                aria-describedby={addressDescribedBy}
                onChange={(event) =>
                  setSelection(addressSelection(event.target.value, entered.mode))
                }
                {...urlHandlers}
              />
            )}
          </Label>
          <small id={addressHintId} className="text-xs text-foreground-muted">
            {ADDRESS_HINT}
          </small>
        </div>
      ) : (
        <>
          {discoverySelect}
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
                aria-describedby={slashId}
                onChange={(event) => setUrlValue(event.target.value)}
              />
            )}
          </Label>
        </>
      )}
      {slashAdvisory}
      {view && (
        <WebsiteRecommendations
          view={view}
          config={config}
          readOnly={readOnly}
          editing={editing}
          formId={collapsible ? formId : undefined}
          onToggleEdit={toggleEdit}
          onCancel={() => void analysis.cancel()}
          onRetry={() => analyse(entered, { force: true })}
          onReanalyze={() => analyse(entered, { force: true, refresh: true })}
          onReset={() => {
            if (described) {
              emit(resetToRecommended(config, described));
            }
          }}
        />
      )}
      {settingsRegion(
        <>
          {recommendations && discoverySelect}
          {recommendations &&
            config.selection.mode === 'sitemap' &&
            entered !== config.selection && (
              <Label>
                Sitemap URL
                <Input
                  type="url"
                  value={config.selection.sitemap_url}
                  onChange={(event) => setUrlValue(event.target.value)}
                />
              </Label>
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
        </>,
      )}
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
