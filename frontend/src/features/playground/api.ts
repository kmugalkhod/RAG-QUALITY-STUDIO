import { request } from '../../lib/api';
import type { Page } from '../../lib/pagination';
import type { QueryRun } from './model';

export function listRuns(projectId: string, offset = 0): Promise<Page<QueryRun>> {
  return request<Page<QueryRun>>(
    `/projects/${encodeURIComponent(projectId)}/query-runs?offset=${offset}`,
  );
}

export function getQueryRun(projectId: string, runId: string): Promise<QueryRun> {
  return request<QueryRun>(
    `/projects/${encodeURIComponent(projectId)}/query-runs/${encodeURIComponent(runId)}`,
  );
}
