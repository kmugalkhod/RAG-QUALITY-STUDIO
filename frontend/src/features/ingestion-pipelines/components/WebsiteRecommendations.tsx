import { useId, useRef, type ReactNode } from 'react';

import { Callout, SUMMARY } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import type {
  RecommendationField,
  RecommendationPath,
  SettingRecommendation,
  SettingsProvenance,
  WebsiteConfig,
} from '../model';
import {
  PREFILLED_PATHS,
  RECOMMENDATION_LABELS,
  estimatedMinutes,
  evidenceCrawlDelay,
  formatRecommendedValue,
  notUsed,
  provenanceRows,
  recommendationDifferences,
  selectionUrls,
  wideningEdits,
} from '../recommendationsModel';
import { DETAILS, FACTS, FIELD_ERROR } from './settingsStyles';

const STEP_LABEL: Record<NonNullable<SettingRecommendation['progress_step']>, string> = {
  robots: 'reading robots.txt',
  start_page: 'reading the start page',
  sitemaps: 'reading sitemaps',
  sample_pages: 'sampling pages',
  validating: 'checking the settings',
};

const PURPOSE_LABEL: Record<string, string> = {
  robots: 'robots.txt',
  start_page: 'Start page',
  sitemaps: 'Sitemap',
  sample_pages: 'Sample page',
};

const NUMERIC_PATHS = new Set(['max_pages', 'max_depth', 'requests_per_second']);
const PATH_LIST_PATHS = new Set(['include_path_prefixes', 'exclude_path_prefixes']);
const monoPath = (path: string) => NUMERIC_PATHS.has(path) || PATH_LIST_PATHS.has(path);

const ACTIONS = 'flex flex-wrap items-center gap-2';

/** What the card shows for one Website source. */
export type RecommendationCardView =
  | { kind: 'analysing'; recommendation?: SettingRecommendation }
  | { kind: 'failed'; message: string }
  | { kind: 'cancelled' }
  | {
      kind: 'live';
      recommendation: SettingRecommendation;
      stale: boolean;
      expired: boolean;
    }
  | { kind: 'saved'; provenance: SettingsProvenance['nodes'][string]; version?: number };

/** "Analysed 2 min ago", "Analysed yesterday", "Analysed 3 days ago". */
export function analysedAgo(value: string | null, now = Date.now()): string {
  if (!value) {
    return 'Analysed';
  }
  const minutes = Math.round((now - new Date(value).getTime()) / 60000);
  if (minutes < 1) {
    return 'Analysed just now';
  }
  if (minutes < 60) {
    return `Analysed ${minutes} min ago`;
  }
  if (minutes < 24 * 60) {
    return `Analysed ${Math.round(minutes / 60)} h ago`;
  }
  const days = Math.floor(minutes / (24 * 60));
  return days === 1 ? 'Analysed yesterday' : `Analysed ${days} days ago`;
}

const shortDate = (value: string | null) =>
  value
    ? new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
    : 'an earlier date';

/** The row value: "Not used" when the setting does not apply, and the page limit's time. */
function rowValue(field: RecommendationField, recommendation: SettingRecommendation): string {
  if (notUsed(field.rationale_code)) {
    return 'Not used';
  }
  const value = formatRecommendedValue(field.path, field.value);
  const rps = recommendation.recommended?.requests_per_second;
  if (field.path !== 'max_pages' || typeof field.value !== 'number' || !rps) {
    return value;
  }
  const minutes = estimatedMinutes(field.value, rps, evidenceCrawlDelay(recommendation));
  return `${value} · about ${minutes} min at ${rps}/s`;
}

/** The sitemap a sitemap discovery reads, under its row. */
function sitemapOf(path: RecommendationPath, value: unknown): string | null {
  if (path !== 'selection' || !value || typeof value !== 'object') {
    return null;
  }
  const selection = value as WebsiteConfig['selection'];
  return selection.mode === 'sitemap' ? selection.sitemap_url : null;
}

function Row({
  label,
  path,
  value,
  mono,
  rationale,
  children,
}: {
  label: string;
  path: RecommendationPath;
  value: string;
  mono: boolean;
  rationale: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1" data-path={path}>
      <dt>{label}</dt>
      <dd className="flex flex-col gap-1">
        <span className={mono ? 'font-mono tabular-nums' : undefined}>{value}</span>
        <span className="text-xs text-foreground-muted">Why: {rationale}</span>
        {children}
      </dd>
    </div>
  );
}

/** The requests the analysis made, the sitemap it read and the pages it sampled. */
function WhatWasChecked({ recommendation }: { recommendation: SettingRecommendation }) {
  const requests = recommendation.evidence.requests ?? [];
  const sitemap = recommendation.evidence.sitemap;
  const samples = recommendation.evidence.sample_pages ?? [];
  return (
    <details className={DETAILS}>
      <summary className={SUMMARY}>What was checked</summary>
      <div className="flex flex-col gap-4 text-sm text-foreground">
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-foreground-muted">Requests</p>
          <ul className="flex flex-col gap-2">
            {requests.map((item, index) => (
              <li key={`${item.url}-${index}`} className="flex min-w-0 flex-col">
                <span>
                  {PURPOSE_LABEL[item.purpose] ?? item.purpose} ·{' '}
                  {item.status === null ? item.outcome : `HTTP ${item.status}`}
                </span>
                <span className="font-mono text-xs wrap-anywhere text-foreground-muted">
                  {item.url}
                </span>
              </li>
            ))}
          </ul>
        </div>
        {sitemap && (
          <p>
            {sitemap.found && sitemap.url ? (
              <>
                Sitemap found:{' '}
                <span className="font-mono text-xs wrap-anywhere">{sitemap.url}</span>, listing{' '}
                {sitemap.lower_bound ? 'at least ' : ''}
                {sitemap.in_scope} {sitemap.in_scope === 1 ? 'page' : 'pages'} in scope.
              </>
            ) : (
              'No sitemap was found.'
            )}
          </p>
        )}
        {samples.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-xs font-medium text-foreground-muted">Sample pages</p>
            <ul className="flex flex-col gap-2">
              {samples.map((page, index) => (
                <li key={`${page.url}-${index}`} className="flex min-w-0 flex-col">
                  <span className="font-mono text-xs wrap-anywhere">{page.url}</span>
                  <span className="text-xs text-foreground-muted">
                    {page.text_length === null
                      ? `Not read${page.status ? ` (HTTP ${page.status})` : ''}`
                      : `${page.text_length.toLocaleString('en-GB')} characters of text`}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}

/**
 * The "Recommended settings" card (spec 0011) for one Website source: the analysis
 * while it runs, its failure, or each recommended setting with its one-line reason,
 * read-only until Edit opens the existing form. A saved version shows the settings it
 * recorded. Viewers see the card without actions.
 */
export function WebsiteRecommendations({
  view,
  config,
  readOnly = false,
  editing,
  formId,
  onToggleEdit,
  onCancel,
  onRetry,
  onReanalyze,
  onReset,
}: {
  view: RecommendationCardView;
  config: WebsiteConfig;
  readOnly?: boolean;
  editing: boolean;
  /** The form Edit opens; without it the form is always shown and there is no Edit. */
  formId?: string;
  onToggleEdit: () => void;
  onCancel: () => void;
  onRetry: () => void;
  onReanalyze: () => void;
  onReset: () => void;
}) {
  const headingId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  // Focus moves to the heading when the control that was pressed goes away.
  const thenFocusHeading = (action: () => void) => () => {
    action();
    window.requestAnimationFrame(() => heading.current?.focus());
  };
  const reanalyze = !readOnly && (
    <Button type="button" variant="ghost" size="sm" onClick={onReanalyze}>
      Re-analyze
    </Button>
  );

  let body: ReactNode;
  let warnings: ReactNode = null;
  if (view.kind === 'analysing') {
    const step = view.recommendation?.progress_step
      ? STEP_LABEL[view.recommendation.progress_step]
      : 'waiting to start';
    body = (
      <>
        <p role="status" aria-live="polite" className="text-sm text-foreground-muted">
          Checking the site to recommend settings: {step}.
        </p>
        {!readOnly && (
          <div className={ACTIONS}>
            <Button type="button" variant="outline" size="sm" onClick={thenFocusHeading(onCancel)}>
              Cancel
            </Button>
          </div>
        )}
      </>
    );
  } else if (view.kind === 'failed') {
    body = (
      <>
        <p role="alert" className={FIELD_ERROR}>
          Settings could not be recommended. {view.message} You can still edit every setting below.
        </p>
        {!readOnly && (
          <div className={ACTIONS}>
            <Button type="button" variant="outline" size="sm" onClick={onRetry}>
              Retry
            </Button>
          </div>
        )}
      </>
    );
  } else if (view.kind === 'cancelled') {
    body = (
      <>
        <p role="status" aria-live="polite" className="text-sm text-foreground-muted">
          The analysis was cancelled. The settings below are unchanged.
        </p>
        {reanalyze && <div className={ACTIONS}>{reanalyze}</div>}
      </>
    );
  } else if (view.kind === 'saved') {
    const rows = provenanceRows(view.provenance);
    const changedCount = rows.filter((row) => row.changed).length;
    body = (
      <>
        <p className="text-xs text-foreground-muted">
          {view.version ? `Version ${view.version} · ` : ''}Recommended on{' '}
          {shortDate(view.provenance.analysed_at)} · {changedCount} changed by you
        </p>
        <dl className={FACTS}>
          {rows.map((row) => (
            <Row
              key={row.path}
              label={row.label}
              path={row.path}
              value={
                notUsed(row.rationaleCode)
                  ? 'Not used'
                  : formatRecommendedValue(row.path, row.value)
              }
              mono={monoPath(row.path) && !notUsed(row.rationaleCode)}
              rationale={row.rationale}
            >
              {row.changed && (
                <span className="text-xs text-foreground-muted">
                  Changed by you (recommended {formatRecommendedValue(row.path, row.recommended)})
                </span>
              )}
            </Row>
          ))}
        </dl>
        {reanalyze && <div className={ACTIONS}>{reanalyze}</div>}
      </>
    );
  } else {
    const { recommendation, stale, expired } = view;
    const current = !stale;
    const changed = current ? recommendationDifferences(config, recommendation) : new Set();
    // In the card's fixed order, whatever order the server listed the rows in.
    const shownChanges = PREFILLED_PATHS.flatMap((path) => {
      const field = recommendation.fields.find((item) => item.path === path);
      return field && changed.has(path) && !notUsed(field.rationale_code) ? [field] : [];
    });
    const widening = current ? wideningEdits(config, recommendation) : [];
    const wideningByPath = new Map(widening.map((item) => [item.path, item.consequence]));
    const requests = recommendation.evidence.requests?.length ?? 0;
    const analysedFor =
      recommendation.inputs.entered_url ?? selectionUrls(recommendation.inputs.selection)[0];
    warnings = recommendation.warnings.map((warning) => (
      <Callout key={warning.code} tone="warning" role="note">
        <p>{warning.message}</p>
      </Callout>
    ));
    body = (
      <>
        <p className="text-xs text-foreground-muted">
          {analysedAgo(recommendation.finished_at)} · {requests}{' '}
          {requests === 1 ? 'request' : 'requests'}
        </p>
        {stale && (
          <p role="status" className="text-xs wrap-anywhere text-warning">
            These recommendations are for <span className="font-mono">{analysedFor}</span>.
            Re-analyze to recommend settings for the current address and sources.
          </p>
        )}
        {expired && !stale && (
          <p className="text-xs text-warning">
            These recommendations are more than a day old. Re-analyze to check the site again.
          </p>
        )}
        <dl className={FACTS}>
          {recommendation.fields.map((field) => {
            const unused = notUsed(field.rationale_code);
            const sitemap = unused ? null : sitemapOf(field.path, field.value);
            const consequence = wideningByPath.get(field.path);
            return (
              <Row
                key={field.path}
                label={field.label}
                path={field.path}
                value={rowValue(field, recommendation)}
                mono={monoPath(field.path) && !unused}
                rationale={field.rationale}
              >
                {sitemap && (
                  <span className="font-mono text-xs wrap-anywhere text-foreground-muted">
                    {sitemap}
                  </span>
                )}
                {field.check && <span className="text-xs text-warning">Check this</span>}
                {changed.has(field.path) && !unused && (
                  <span className="text-xs text-foreground-muted">
                    Changed from recommended (was {formatRecommendedValue(field.path, field.value)})
                  </span>
                )}
                {consequence && <span className="text-xs text-warning">{consequence}</span>}
              </Row>
            );
          })}
        </dl>
        {widening.length > 0 && (
          <div role="note" className="flex flex-col gap-2 border-t border-border pt-4">
            <p className="text-sm font-medium text-warning">Wider than recommended</p>
            <ul className="flex flex-col gap-1 text-xs text-foreground">
              {widening.map((item) => (
                <li key={item.path}>
                  <span className="font-medium">{item.label}:</span> {item.consequence}
                </li>
              ))}
            </ul>
          </div>
        )}
        {!readOnly && shownChanges.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-xs text-foreground-muted">
              {shownChanges.length} {shownChanges.length === 1 ? 'setting' : 'settings'} changed
              from recommended:{' '}
              {shownChanges.map((field) => RECOMMENDATION_LABELS[field.path]).join(', ')}.
            </p>
            <div className={ACTIONS}>
              <Button type="button" variant="outline" size="sm" onClick={thenFocusHeading(onReset)}>
                Reset to recommended
              </Button>
            </div>
          </div>
        )}
        {!readOnly && (
          <div className={ACTIONS}>
            {formId && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                aria-expanded={editing}
                aria-controls={formId}
                onClick={onToggleEdit}
              >
                {editing ? 'Hide settings' : 'Edit'}
              </Button>
            )}
            {reanalyze}
          </div>
        )}
        <WhatWasChecked recommendation={recommendation} />
      </>
    );
  }

  return (
    <>
      {warnings}
      <section
        aria-labelledby={headingId}
        className="flex flex-col gap-4 rounded-card border border-border p-4"
      >
        <h3
          id={headingId}
          ref={heading}
          tabIndex={-1}
          className="text-sm font-semibold text-foreground"
        >
          Recommended settings
        </h3>
        {body}
      </section>
    </>
  );
}
