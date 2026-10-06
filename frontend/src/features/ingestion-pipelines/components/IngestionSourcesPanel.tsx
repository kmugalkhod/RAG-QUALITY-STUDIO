import { useState } from 'react';
import { Ellipsis, Plus, RefreshCw, Trash2 } from 'lucide-react';

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

// Value, accessible name, short visible label and the hint shown while it is chosen.
const outputs = [
  [
    'merged',
    'One combined index',
    'Combined',
    'All sites share one set of processing settings and one index. Pages found on two sites are indexed once.',
  ],
  [
    'per_source',
    'One index per source',
    'Per source',
    'Each site publishes its own index. Stages are shared, and any stage can be customized for one source.',
  ],
] as const;

/**
 * The pipeline's sources and its output choice: what a Website pipeline reads and whether
 * it publishes one combined index or one index per source. Each source is a three-line card;
 * its run and remove actions open in the card from its "⋯" button so the list stays short.
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
  const [actionsFor, setActionsFor] = useState<string>();
  return (
    <section
      aria-labelledby="ingestion-sources-heading"
      className="flex min-w-0 flex-col gap-4 border-b border-border bg-background p-4 md:p-6 desktop:w-panel desktop:shrink-0 desktop:overflow-y-auto desktop:overscroll-contain desktop:border-r desktop:border-b-0"
    >
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

      <fieldset className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
        <legend className="mb-2 text-xs font-medium text-foreground-muted">Output</legend>
        <RadioGroup
          aria-label="Output"
          value={indexLayout}
          disabled={!!layoutLocked}
          onValueChange={(value) => onLayoutChange(value as 'merged' | 'per_source')}
          className="grid grid-cols-2 gap-1 rounded-control border border-border bg-surface p-1"
        >
          {outputs.map(([value, title, short]) => (
            <label
              key={value}
              className={cn(
                'flex min-h-control-md cursor-pointer items-center gap-2 rounded-control px-2 text-xs font-medium pointer-coarse:min-h-control-lg',
                indexLayout === value
                  ? 'bg-surface-active text-foreground'
                  : 'text-foreground-muted hover:text-foreground',
              )}
            >
              <RadioGroupItem value={value} aria-label={title} />
              <span className="min-w-0">{short}</span>
            </label>
          ))}
        </RadioGroup>
        <p className={HINT}>
          {layoutLocked ?? outputs.find(([value]) => value === indexLayout)?.[3]}
        </p>
      </fieldset>

      <ul className="flex flex-col gap-2" aria-label="Sources in this pipeline">
        {sources.map((source) => {
          const selected = source.id === selectedSource;
          const summary = [source.host ?? 'No URL yet', source.status?.detail]
            .filter(Boolean)
            .join(' · ');
          return (
            <li
              key={source.id}
              className={cn(
                'flex flex-wrap items-start rounded-card border border-border bg-surface',
                selected && 'outline-2 -outline-offset-1 outline-accent',
              )}
            >
              <Button
                type="button"
                variant="ghost"
                aria-pressed={selected}
                aria-label={`${source.label} settings`}
                title={source.indexName ? `Index: ${source.indexName}` : undefined}
                className="h-auto min-w-0 flex-1 flex-col items-stretch justify-start gap-1 rounded-card py-2 pr-1 pl-3 text-left font-normal whitespace-normal pointer-coarse:h-auto"
                onClick={() => onSelect(source.id)}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <strong className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">
                    {source.label}
                  </strong>
                  {source.status && (
                    <StatusBadge status={source.status.tone}>{source.status.label}</StatusBadge>
                  )}
                </span>
                <span
                  className={cn(
                    'truncate text-xs',
                    source.status?.tone === 'failed' ? 'text-danger' : 'text-foreground-muted',
                  )}
                >
                  {summary}
                </span>
                {perSource && (
                  <span className="flex flex-wrap gap-1">
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
                      <span className="text-xs text-foreground-muted">Shared settings</span>
                    )}
                  </span>
                )}
              </Button>
              {several && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  icon
                  className="m-1"
                  aria-label={`Actions for ${source.label}`}
                  aria-expanded={actionsFor === source.id}
                  aria-controls={`source-actions-${source.id}`}
                  onClick={() => setActionsFor(actionsFor === source.id ? undefined : source.id)}
                >
                  <Ellipsis aria-hidden="true" />
                </Button>
              )}
              {several && actionsFor === source.id && (
                <div
                  id={`source-actions-${source.id}`}
                  className="flex w-full flex-wrap gap-1 border-t border-border px-2 py-1"
                >
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={!!refreshBlocked}
                    aria-describedby={refreshBlocked ? 'refresh-source-blocked' : undefined}
                    onClick={() => {
                      setActionsFor(undefined);
                      onRefresh(source.id);
                    }}
                  >
                    <RefreshCw aria-hidden="true" />
                    {refreshLabel} {source.label}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-danger"
                    onClick={() => {
                      if (
                        window.confirm(
                          `Remove ${source.label} from this draft? Discard brings it back until you save.`,
                        )
                      ) {
                        setActionsFor(undefined);
                        onRemove(source.id);
                      }
                    }}
                  >
                    <Trash2 aria-hidden="true" />
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
    </section>
  );
}
