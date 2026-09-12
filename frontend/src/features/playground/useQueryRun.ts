import { useEffect, useState } from 'react';
import { getQueryRun } from './api';
import { type QueryRun } from './model';

/** Owns the selected answer and polls one request at a time until it finishes. */
export function useQueryRun(projectId: string) {
  const [run, setRun] = useState<QueryRun>();
  const [pollError, setPollError] = useState('');
  const [completedRuns, setCompletedRuns] = useState(0);
  const runId = run?.id;
  const status = run?.status;

  useEffect(() => {
    setPollError('');
    if (!runId || status !== 'running') {
      return;
    }
    const selectedRunId = runId;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await getQueryRun(projectId, selectedRunId);
        if (disposed) {
          return;
        }
        setRun(next);
        setPollError('');
        if (next.status !== 'running') {
          setCompletedRuns((count) => count + 1);
          return;
        }
      } catch (error) {
        if (disposed) {
          return;
        }
        setPollError(
          error instanceof Error ? error.message : 'Could not refresh the answer. Retrying…',
        );
      }
      if (!disposed) {
        timer = setTimeout(() => void poll(), 1000);
      }
    }
    timer = setTimeout(() => void poll(), 1000);
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [projectId, runId, status]);

  return { run, setRun, pollError, completedRuns };
}
