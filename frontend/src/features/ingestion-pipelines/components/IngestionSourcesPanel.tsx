import { Plus } from 'lucide-react';

import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import { RadioGroup, RadioGroupItem } from '../../../components/ui/radio-group';
import { cn } from '../../../lib/utils';
import type { SourceRunStatus } from '../sourcesView';
import { FIELD_ERROR, HINT } from './settingsStyles';

export type SourceCard = {
  id: string;
  label: string;
  host: string | null;
  status?: SourceRunStatus;
  /** Its index name in a one-index-per-source layout. */
  indexName?: string;
  /** Stages this source customizes, such as "Custom chunking". */
  customized: string[];
};

const LEGEND = 'text-sm font-semibold text-foreground';

/**
 * The pipeline's sources and its output choice: what a Website pipeline reads and whether
 * it publishes one combined index or one index per source.
 */
export function IngestionSourcesPanel({
  sources,
  selectedSource,
  indexLayout,
  layoutLocked,
  maxSources,
  pageTotal,
  maxPages,
  addBlocked,
  refreshLabel,
  refreshBlocked,
  onSelect,
  onAdd,
  onRemove,
  onRefresh,
  onLayoutChange,
}: {
  sources: SourceCard[];
  selectedSource?: string;
  indexLayout: 'merged' | 'per_source';
  /** Why the output cannot change, or null when it can. */
  layoutLocked: string | null;
  maxSources: number;
  pageTotal: number;
  maxPages: number;
  addBlocked: string | null;
  refreshLabel: string;
  refreshBlocked: string | null;
  onSelect: (sourceId: string) => void;
  onAdd: () => void;
  onRemove: (sourceId: string) => void;
  onRefresh: (sourceId: string) => void;
  onLayoutChange: (layout: 'merged' | 'per_source') => void;
}) {
  const perSource = indexLayout === 'per_source';
  const several = sources.length > 1;
  return (
    <section
      aria-labelledby="ingestion-sources-heading"
      className="flex min-w-0 flex-col gap-6 border-b border-border bg-background p-4 md:p-6 desktop:w-panel desktop:shrink-0 desktop:overflow-y-auto desktop:overscroll-contain desktop:border-r desktop:border-b-0"
    >
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <h2 id="ingestion-sources-heading" className={LEGEND}>
            Sources
          </h2>
          <span className="text-xs text-foreground-muted">
            {sources.length} of {maxSources}
          </span>
          <span className="flex-1" />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!!addBlocked}
            aria-describedby={addBlocked ? 'add-source-blocked' : undefined}
            onClick={onAdd}
          >
            <Plus aria-hidden="true" />
            Add website
          </Button>
        </div>
        {addBlocked && (
          <p id="add-source-blocked" className={HINT}>
            {addBlocked}
          </p>
        )}
        <ul className="flex flex-col gap-3" aria-label="Sources in this pipeline">
          {sources.map((source) => {
            const selected = source.id === selectedSource;
            return (
              <li
                key={source.id}
                className={cn(
                  'flex flex-col rounded-card border border-border bg-surface',
                  selected && 'outline-2 -outline-offset-1 outline-accent',
                )}
              >
                <Button
                  type="button"
                  variant="ghost"
                  aria-pressed={selected}
                  aria-label={`${source.label} settings`}
                  className="h-auto min-w-0 flex-col items-stretch justify-start gap-1 rounded-card px-4 pt-3 pb-2 text-left font-normal whitespace-normal pointer-coarse:h-auto"
                  onClick={() => onSelect(source.id)}
                >
                  <span className="flex items-center gap-2">
                    <strong className="flex-1 text-sm font-semibold text-foreground">
                      {source.label}
                    </strong>
                    {source.status && (
                      <StatusBadge status={source.status.tone}>{source.status.label}</StatusBadge>
                    )}
                  </span>
                  <span className="truncate text-sm text-foreground-muted">
                    {source.host ?? 'No URL yet'}
                  </span>
                  {source.status && (
                    <span
                      className={cn(
                        'text-xs wrap-anywhere',
                        source.status.tone === 'failed' ? 'text-danger' : 'text-foreground-muted',
                      )}
                    >
                      {source.status.detail}
                    </span>
                  )}
                  {perSource && (
                    <span className="mt-1 flex flex-wrap gap-1">
                      {source.indexName && (
                        <span className="rounded-control bg-surface-hover px-2 text-xs text-foreground-muted">
                          Index: {source.indexName}
                        </span>
                      )}
                      {source.customized.length ? (
                        source.customized.map((stage) => (
                          <span
                            key={stage}
                            className="rounded-control border border-warning px-2 text-xs text-warning"
                          >
                            {stage}
                          </span>
                        ))
                      ) : (
                        <span className="rounded-control bg-surface-hover px-2 text-xs text-foreground-muted">
                          Shared settings
                        </span>
                      )}
                    </span>
                  )}
                </Button>
                {several && (
                  <div className="flex flex-wrap gap-1 px-2 pb-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={!!refreshBlocked}
                      aria-describedby={refreshBlocked ? 'refresh-source-blocked' : undefined}
                      onClick={() => onRefresh(source.id)}
                    >
                      {refreshLabel} {source.label}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-danger"
                      onClick={() => onRemove(source.id)}
                    >
                      Remove {source.label}
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        {several && refreshBlocked && (
          <p id="refresh-source-blocked" className={HINT}>
            {refreshBlocked}
          </p>
        )}
        {several && (
          <p
            className={pageTotal > maxPages ? FIELD_ERROR : 'text-xs text-foreground-muted'}
            role={pageTotal > maxPages ? 'alert' : undefined}
          >
            Maximum pages across sources: {pageTotal.toLocaleString('en-US')} of{' '}
            {maxPages.toLocaleString('en-US')}.
          </p>
        )}
      </div>

      <fieldset className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
        <legend className={cn(LEGEND, 'mb-3')}>Output</legend>
        <RadioGroup
          aria-label="Output"
          value={indexLayout}
          disabled={!!layoutLocked}
          onValueChange={(value) => onLayoutChange(value as 'merged' | 'per_source')}
          className="flex flex-col gap-3"
        >
          {(
            [
              [
                'merged',
                'One combined index',
                'All sites share one set of processing settings and one index. Pages found on two sites are indexed once.',
              ],
              [
                'per_source',
                'One index per source',
                'Each site publishes its own index. Stages are shared, and any stage can be customized for one source.',
              ],
            ] as const
          ).map(([value, title, description]) => (
            <label
              key={value}
              className={cn(
                'flex cursor-pointer items-start gap-3 rounded-card border border-border bg-surface p-4 text-sm',
                indexLayout === value && 'border-accent',
              )}
            >
              <RadioGroupItem value={value} className="mt-1" />
              <span className="flex min-w-0 flex-col gap-1">
                <span className="font-medium text-foreground">{title}</span>
                <span className="text-xs text-foreground-muted">{description}</span>
              </span>
            </label>
          ))}
        </RadioGroup>
        {layoutLocked && <p className={HINT}>{layoutLocked}</p>}
      </fieldset>
    </section>
  );
}
