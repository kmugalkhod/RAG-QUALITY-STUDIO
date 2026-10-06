import { useEffect, useState } from 'react';
import { listRecentIngestionRuns } from '../features/ingestion-pipelines/api';

const POLL_DELAY_MS = 10000;
const ACTIVE_STATUSES = new Set(['queued', 'running']);

/** The number of queued or running runs, null when the count failed, undefined before the first answer. */
export type ActiveRunCount = number | null | undefined;

// Spec 0003 top bar. Counts the queued and running ingestion runs among the project's
// most recent runs (the API cannot filter by status), one request at a time, polling 10
// seconds after each answer while the tab is visible.
export function useActiveRuns(projectId: string | undefined): ActiveRunCount {
  const [state, setState] = useState<{ projectId: string; count: number | null }>();

  useEffect(() => {
    if (!projectId) {
      return;
    }
    let disposed = false;
    let timer: number | undefined;
    const controller = new AbortController();
    const schedule = () => {
      if (!disposed) {
        timer = window.setTimeout(poll, POLL_DELAY_MS);
      }
    };
    async function poll() {
      if (document.hidden) {
        schedule();
        return;
      }
      try {
        const page = await listRecentIngestionRuns(projectId as string, controller.signal);
        if (!disposed) {
          const count = page.items.filter((run) => ACTIVE_STATUSES.has(run.status)).length;
          setState({ projectId: projectId as string, count });
        }
      } catch {
        if (!disposed) {
          setState({ projectId: projectId as string, count: null });
        }
      }
      schedule();
    }
    void poll();
    return () => {
      disposed = true;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [projectId]);

  return state && state.projectId === projectId ? state.count : undefined;
}
