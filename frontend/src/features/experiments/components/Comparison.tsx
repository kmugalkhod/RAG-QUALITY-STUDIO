import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui/button';
import { StatusBadge } from '../../../components/StatusBadge';
import { Progress } from '../../../components/ui/progress';
import * as api from '../api';
import type { Detail } from '../model';
import { ComparisonSummary } from './ComparisonSummary';
import { QuestionComparison } from './QuestionComparison';

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

  return (
    <section className="experiments max-w-300">
      <a href={`#/projects/${projectId}/experiments`}>All experiments</a>
      {error && (
        <p role="alert">
          {error}{' '}
          <Button variant="outline" onClick={() => setRevision((value) => value + 1)}>
            Retry
          </Button>
        </p>
      )}
      {!run ? (
        <p role="status">Loading experiment…</p>
      ) : (
        <>
          <header className="experiment-heading">
            <div>
              <h1>{run.name}</h1>
              <p role="status">
                <StatusBadge status={run.status} /> {run.progress} / {run.total} results completed
                {run.cancel_requested ? ' · Cancellation requested' : ''}
              </p>
            </div>
            <Button variant="outline" asChild>
              <a href={`/api/projects/${projectId}/experiments/${run.id}/export.csv`} download>
                Export CSV
              </a>
            </Button>
          </header>
          {['queued', 'running'].includes(run.status) && (
            <div className="my-5">
              <Progress
                value={run.total ? (run.progress / run.total) * 100 : 0}
                aria-label="Experiment progress"
              />
              <Button
                variant="outline"
                disabled={cancelling || run.cancel_requested}
                onClick={() => void cancel()}
              >
                {cancelling ? 'Cancelling…' : 'Cancel experiment'}
              </Button>
              <p>Cancellation stops future calls; an in-flight result may still finish.</p>
            </div>
          )}
          {run.error && <p role="alert">{run.error}</p>}
          <ComparisonSummary run={run} />
          <QuestionComparison run={run} />
          <details className="experiment-section">
            <summary>Immutable run configuration</summary>
            <pre>{JSON.stringify(run.snapshot, null, 2)}</pre>
          </details>
        </>
      )}
    </section>
  );
}
