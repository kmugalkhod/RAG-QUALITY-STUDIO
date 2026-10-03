import { ArrowRight, ChevronDown, Square, X } from 'lucide-react';

import { META } from '../../../components/parts';
import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import { Progress } from '../../../components/ui/progress';
import { cn } from '../../../lib/utils';
import { terminalIngestionStatuses as terminal } from '../editorModel';
import type { IngestionNodeExecutionStatus } from '../executionState';
import type { IngestionRun } from '../model';
import { executionStatusPresentation } from './IngestionPipelineCanvas';

// One line under the toolbar for the latest run: progress while it runs, then the outcome and
// where to use or inspect the published index. Item details open in the results drawer.
export function IngestionRunStrip({
  projectId,
  run,
  displayStatus,
  busy,
  detailsOpen,
  onCancel,
  onToggleDetails,
  onDismiss,
}: {
  projectId: string;
  run: IngestionRun;
  displayStatus: IngestionNodeExecutionStatus;
  busy: boolean;
  detailsOpen: boolean;
  onCancel: () => void;
  onToggleDetails: () => void;
  onDismiss: () => void;
}) {
  const presentation = executionStatusPresentation[displayStatus];
  const StatusIcon = presentation.icon;
  const finished = terminal.has(run.status);
  const published = run.status === 'succeeded' && run.published_index_id;
  const counted =
    run.new_count > 0 || run.changed_count > 0 || run.unchanged_count > 0 || run.removed_count > 0;
  return (
    <div
      id="ingestion-run"
      className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-surface px-4 py-2 md:px-6"
      aria-live="polite"
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-foreground-muted">Last run</span>
        <StatusBadge data-testid="ingestion-run-state" status={displayStatus}>
          <StatusIcon
            aria-hidden="true"
            className={cn(displayStatus === 'running' && 'motion-safe:animate-spin')}
          />
          {presentation.label}
        </StatusBadge>
        {!finished && (
          <strong className="text-xs font-semibold text-foreground tabular-nums">
            {run.progress}%
          </strong>
        )}
      </div>
      {!finished ? (
        <>
          <p
            title={run.knowledge_set_name}
            className="min-w-0 truncate text-xs font-medium text-foreground"
          >
            {run.knowledge_set_name}
          </p>
          <Progress
            className="w-full md:w-sidebar"
            aria-label="Ingestion run progress"
            value={run.progress}
          />
          <p className={cn(META, 'tabular-nums')}>
            {run.stage === 'indexing'
              ? `${run.embedded_count}/${run.chunk_count} chunks embedded`
              : run.stage === 'discovering' &&
                  Object.keys(run.fetch_policies ?? {}).length > 0 &&
                  run.discovered_count > 0
                ? `${run.processed_count} / ${run.discovered_count} discovered URLs checked`
                : `${run.stage} checkpoint`}
          </p>
          <span className="flex-1" />
          <Button variant="ghost" size="sm" disabled={busy} onClick={onCancel}>
            <Square aria-hidden="true" />
            Cancel run
          </Button>
        </>
      ) : (
        <>
          {counted && (
            <p className={cn(META, 'tabular-nums')}>
              {run.new_count} new · {run.changed_count} changed · {run.unchanged_count} unchanged ·{' '}
              {run.removed_count} removed
              {run.failed_count > 0 && (
                <span className="text-danger"> · {run.failed_count} failed</span>
              )}
            </p>
          )}
          {run.error && (
            <p
              role="alert"
              title={run.error}
              className="min-w-0 flex-1 truncate text-sm text-danger md:basis-0"
            >
              {run.error}
            </p>
          )}
          <span className="flex-1" />
          {published && (
            <div data-testid="published-index" className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-medium text-foreground">
                Index version {run.published_index_version} is ready to use
              </p>
              <Button size="sm" asChild>
                <a href={`#/projects/${projectId}/pipelines/new?index=${run.published_index_id}`}>
                  Use in answer pipeline
                  <ArrowRight aria-hidden="true" />
                </a>
              </Button>
              <Button size="sm" variant="outline" asChild>
                <a
                  href={`#/projects/${projectId}/knowledge-base?view=indexes&index=${run.published_index_id}`}
                >
                  Inspect published index
                </a>
              </Button>
            </div>
          )}
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              aria-expanded={detailsOpen}
              aria-controls="ingestion-results"
              onClick={onToggleDetails}
            >
              Run details
              <ChevronDown
                aria-hidden="true"
                className={cn(
                  'transition-transform duration-(--transition-fast)',
                  detailsOpen && 'rotate-180',
                )}
              />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon
              aria-label="Dismiss run summary"
              onClick={onDismiss}
            >
              <X aria-hidden="true" />
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
