import { useId } from 'react';

import { Callout } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import type { RecommendationField, SettingRecommendation, WebsiteConfig } from '../model';
import {
  estimatedMinutes,
  evidenceCrawlDelay,
  formatRecommendedValue,
  notUsed,
  recommendationDifferences,
} from '../recommendationsModel';
import { FACTS, FIELD_ERROR } from './settingsStyles';

const STEP_LABEL: Record<NonNullable<SettingRecommendation['progress_step']>, string> = {
  robots: 'reading robots.txt',
  start_page: 'reading the start page',
  sitemaps: 'reading sitemaps',
  sample_pages: 'sampling pages',
  validating: 'checking the settings',
};

const NUMERIC_PATHS = new Set(['max_pages', 'max_depth', 'requests_per_second']);
const PATH_LIST_PATHS = new Set(['include_path_prefixes', 'exclude_path_prefixes']);

function analysedAgo(value: string | null): string {
  if (!value) {
    return 'Analysed';
  }
  const minutes = Math.round((Date.now() - new Date(value).getTime()) / 60000);
  if (minutes < 1) {
    return 'Analysed just now';
  }
  if (minutes < 60) {
    return `Analysed ${minutes} min ago`;
  }
  return `Analysed ${Math.round(minutes / 60)} h ago`;
}

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

/**
 * The "Recommended settings" card (spec 0011): each recommended Website setting with its
 * one-line reason, read-only until Edit opens the existing form. Warnings appear above it.
 */
export function WebsiteRecommendations({
  config,
  recommendation,
  error,
  analysing,
  editing,
  formId,
  onToggleEdit,
}: {
  config: WebsiteConfig;
  recommendation?: SettingRecommendation;
  error: string;
  analysing: boolean;
  editing: boolean;
  formId: string;
  onToggleEdit: () => void;
}) {
  const headingId = useId();
  if (error) {
    return (
      <p role="alert" className={FIELD_ERROR}>
        Settings could not be recommended. {error}
      </p>
    );
  }
  if (!recommendation) {
    return null;
  }
  if (analysing) {
    const step = recommendation.progress_step
      ? STEP_LABEL[recommendation.progress_step]
      : 'waiting to start';
    return (
      <p role="status" aria-live="polite" className="text-sm text-foreground-muted">
        Checking the site to recommend settings: {step}.
      </p>
    );
  }
  if (recommendation.status !== 'succeeded' && recommendation.status !== 'expired') {
    if (recommendation.status === 'cancelled') {
      return null;
    }
    return (
      <p role="alert" className={FIELD_ERROR}>
        Settings could not be recommended.{' '}
        {recommendation.error ?? 'The site check did not finish.'} You can still edit every setting
        below.
      </p>
    );
  }
  const changed = recommendationDifferences(config, recommendation);
  const requests = recommendation.evidence.requests?.length ?? 0;
  return (
    <>
      {recommendation.warnings.map((warning) => (
        <Callout key={warning.code} tone="warning" role="note">
          <p>{warning.message}</p>
        </Callout>
      ))}
      <section
        aria-labelledby={headingId}
        className="flex flex-col gap-4 rounded-card border border-border p-4"
      >
        <div className="flex flex-col gap-1">
          <h3 id={headingId} className="text-sm font-semibold text-foreground">
            Recommended settings
          </h3>
          <p className="text-xs text-foreground-muted">
            {analysedAgo(recommendation.finished_at)} · {requests}{' '}
            {requests === 1 ? 'request' : 'requests'}
          </p>
        </div>
        <dl className={FACTS}>
          {recommendation.fields.map((field) => {
            const mono = NUMERIC_PATHS.has(field.path) || PATH_LIST_PATHS.has(field.path);
            return (
              <div key={field.path} className="flex min-w-0 flex-col gap-1">
                <dt>{field.label}</dt>
                <dd className="flex flex-col gap-1">
                  <span
                    className={
                      mono && !notUsed(field.rationale_code) ? 'font-mono tabular-nums' : undefined
                    }
                  >
                    {rowValue(field, recommendation)}
                  </span>
                  <span className="text-xs text-foreground-muted">Why: {field.rationale}</span>
                  {field.check && <span className="text-xs text-warning">Check this</span>}
                  {changed.has(field.path) && !notUsed(field.rationale_code) && (
                    <span className="text-xs text-foreground-muted">
                      Changed from recommended (was{' '}
                      {formatRecommendedValue(field.path, field.value)})
                    </span>
                  )}
                </dd>
              </div>
            );
          })}
        </dl>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          aria-expanded={editing}
          aria-controls={formId}
          onClick={onToggleEdit}
        >
          {editing ? 'Hide settings' : 'Edit'}
        </Button>
      </section>
    </>
  );
}
