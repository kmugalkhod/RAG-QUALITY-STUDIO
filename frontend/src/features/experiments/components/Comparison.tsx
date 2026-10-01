import { useEffect, useState } from 'react';
import { ArrowLeft, ChevronRight, Download } from 'lucide-react';
import { CARD, InlineError, PRE, SUMMARY } from '../../../components/parts';
import { PageHeader } from '../../../components/PageHeader';
import { ErrorState } from '../../../components/states/ErrorState';
import { LoadingState } from '../../../components/states/LoadingState';
import { Button } from '../../../components/ui/button';
import { StatusBadge } from '../../../components/StatusBadge';
import { Progress } from '../../../components/ui/progress';
import * as api from '../api';
import type { Detail } from '../model';
import { ComparisonSummary } from './ComparisonSummary';
import { QuestionComparison } from './QuestionComparison';
import { downloadFile } from '../../../lib/api';

export function Comparison({
  projectId,
  experimentId,
}: {
  projectId: string;
  experimentId: string;
}) {
  const [run, setRun] = useState<Detail>();
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api.getExperiment(projectId, experimentId);
        if (disposed) {
          return;
        }
        setRun(next);
        setError('');
        if (['queued', 'running'].includes(next.status)) {
          timer = setTimeout(() => void poll(), 2000);
        }
      } catch (cause) {
        if (!disposed) {
          setError((cause as Error).message);
          timer = setTimeout(() => void poll(), 2000);
        }
      }
    }
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [projectId, experimentId, revision]);

  async function cancel() {
    if (!run) {
      return;
    }
    setCancelling(true);
    try {
      await api.cancelExperiment(projectId, run.id);
      setRevision((value) => value + 1);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setCancelling(false);
    }
  }

  const active = !!run && ['queued', 'running'].includes(run.status);
  return (
    <div className="flex flex-col gap-6">
      <Button variant="ghost" size="sm" className="self-start" asChild>
        <a href={`#/projects/${projectId}/experiments`}>
          <ArrowLeft aria-hidden="true" />
          All experiments
        </a>
      </Button>
      {!run ? (
        error ? (
          <ErrorState
            headingLevel="h1"
            title="We couldn’t load this experiment"
            message={error}
            onRetry={() => setRevision((value) => value + 1)}
          />
        ) : (
          <LoadingState label="Loading experiment…" rows={4} />
        )
      ) : (
        <>
          <PageHeader
            title={run.name}
            meta={
              <span role="status" className="flex flex-wrap items-center gap-2">
                <StatusBadge status={run.status} /> {run.progress} / {run.total} results completed
                {run.cancel_requested ? ' · Cancellation requested' : ''}
              </span>
            }
            action={
              <Button
                variant="outline"
                onClick={() =>
                  void downloadFile(
                    `/projects/${projectId}/experiments/${run.id}/export.csv`,
                    `experiment-${run.id}.csv`,
                  ).catch((cause) => setError((cause as Error).message))
                }
              >
                <Download aria-hidden="true" />
                Export CSV
              </Button>
            }
          />
          {error && (
            <InlineError onRetry={() => setRevision((value) => value + 1)}>{error}</InlineError>
          )}
          {active && (
            <div className={`${CARD} flex flex-col gap-3 p-4 md:flex-row md:items-center md:gap-6`}>
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                <Progress
                  value={run.total ? (run.progress / run.total) * 100 : 0}
                  aria-label="Experiment progress"
                />
                <p className="text-xs text-foreground-muted">
                  Cancellation stops future calls; an in-flight result may still finish.
                </p>
              </div>
              <Button
                variant="outline"
                className="max-md:w-full md:shrink-0"
                loading={cancelling}
                disabled={cancelling || run.cancel_requested}
                onClick={() => void cancel()}
              >
                Cancel experiment
              </Button>
            </div>
          )}
          {run.error && <InlineError>{run.error}</InlineError>}
          <ComparisonSummary run={run} />
          <QuestionComparison run={run} />
          <details className={`${CARD} group px-4 md:px-6`}>
            <summary className={SUMMARY}>
              <ChevronRight
                aria-hidden="true"
                className="transition-transform duration-(--transition-fast) group-open:rotate-90"
              />
              Immutable run configuration
            </summary>
            <pre className={`${PRE} mb-4`}>{JSON.stringify(run.snapshot, null, 2)}</pre>
          </details>
        </>
      )}
    </div>
  );
}
