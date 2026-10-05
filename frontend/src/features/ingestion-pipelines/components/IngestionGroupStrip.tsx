import { Square, X } from 'lucide-react';

import { LINK, META } from '../../../components/parts';
import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import { cn } from '../../../lib/utils';
import type { IngestionRun, IngestionRunGroup } from '../model';

const groupStatusLabels: Record<IngestionRunGroup['status'], string> = {
  queued: 'Queued',
  running: 'Running',
  succeeded: 'Complete',
  failed: 'Failed',
  cancelled: 'Cancelled',
  partial: 'Some indexes failed',
};

const runStatusLabels: Record<IngestionRun['status'], string> = {
  queued: 'Queued',
  running: 'Running',
  succeeded: 'Published',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

/** The latest run group of a one-index-per-source pipeline: one row per source's index. */
export function IngestionGroupStrip({
  projectId,
  group,
  busy,
  detailsRunId,
  label,
  onCancel,
  onShowDetails,
  onDismiss,
}: {
  projectId: string;
  group: IngestionRunGroup;
  busy: boolean;
  detailsRunId?: string;
  label: (sourceNodeId: string) => string;
  onCancel: () => void;
  onShowDetails: (run: IngestionRun) => void;
  onDismiss: () => void;
}) {
  const active = group.status === 'queued' || group.status === 'running';
  // `partial` and `cancelled` reuse the neutral and failed tones of the badge.
  const tone = group.status === 'partial' ? 'failed' : group.status;
  return (
    <div
      id="ingestion-run"
      data-testid="ingestion-run-group"
      className="flex shrink-0 flex-col gap-2 border-b border-border bg-surface px-4 py-2 md:px-6"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-xs font-medium text-foreground-muted">Last run</span>
        <StatusBadge status={tone}>{groupStatusLabels[group.status]}</StatusBadge>
        {group.completion === 'with_warnings' && (
          <span className="text-xs font-medium text-warning">with warnings</span>
        )}
        <p className={META}>
          {group.runs.length === 1 ? '1 index' : `${group.runs.length} indexes, one per source`}
        </p>
        <span className="flex-1" />
        {active ? (
          <Button variant="ghost" size="sm" disabled={busy} onClick={onCancel}>
            <Square aria-hidden="true" />
            Cancel run
          </Button>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            icon
            aria-label="Dismiss run summary"
            onClick={onDismiss}
          >
            <X aria-hidden="true" />
          </Button>
        )}
      </div>
      <ul className="flex flex-col gap-1" aria-label="Indexes in this run">
        {group.runs.map((run) => {
          const finished = !['queued', 'running'].includes(run.status);
          return (
            <li
              key={run.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-foreground"
            >
              <strong className="font-medium">
                {run.branch_source_node_id ? label(run.branch_source_node_id) : 'Source'}
              </strong>
              <StatusBadge status={run.status}>
                {runStatusLabels[run.status]}
                {!finished ? ` · ${run.progress}%` : ''}
              </StatusBadge>
              <span className={cn(META, 'min-w-0 truncate')} title={run.knowledge_set_name}>
                {run.knowledge_set_name}
                {run.published_index_version ? ` · version ${run.published_index_version}` : ''}
              </span>
              {run.error && (
                <span role="alert" className="min-w-0 truncate text-danger" title={run.error}>
                  {run.error}
                </span>
              )}
              {run.status === 'succeeded' && run.published_index_id && (
                <a
                  className={cn(LINK, 'text-xs')}
                  href={`#/projects/${projectId}/knowledge-base?view=indexes&index=${run.published_index_id}`}
                >
                  Inspect index
                </a>
              )}
              {finished && (
                <Button
                  size="sm"
                  variant="ghost"
                  aria-pressed={detailsRunId === run.id}
                  onClick={() => onShowDetails(run)}
                >
                  Run details
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
