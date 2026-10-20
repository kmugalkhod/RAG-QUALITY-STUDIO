import { postJson, request } from '../../lib/api';
import type { Page } from '../../lib/pagination';

import { type QueryRun } from '../playground/model';
import type {
  PipelineDraft,
  PipelineExecution,
  PipelineOptions,
  Pipeline,
  PipelineKind,
  PipelineOutcome,
  PipelineVersion,
} from './model';

function pipelinesPath(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}/pipelines`;
}

function pipelinePath(projectId: string, pipelineId: string): string {
  return `${pipelinesPath(projectId)}/${encodeURIComponent(pipelineId)}`;
}

export function getPipeline(projectId: string, pipelineId: string): Promise<Pipeline> {
  return request<Pipeline>(pipelinePath(projectId, pipelineId));
}

export function getPipelineOptions(projectId: string): Promise<PipelineOptions> {
  return request<PipelineOptions>(`${pipelinesPath(projectId)}/options`);
}

export function listPipelines(
  projectId: string,
  kind: PipelineKind,
  offset = 0,
): Promise<Page<Pipeline>> {
  return request<Page<Pipeline>>(`${pipelinesPath(projectId)}?kind=${kind}&offset=${offset}`);
}

export const PIPELINE_PAGE_SIZE = 25;

/** One page of the pipeline list, searched and filtered by the last run (spec 0015 U1). */
export function listPipelinePage(
  projectId: string,
  kind: PipelineKind,
  { offset = 0, q = '', outcome }: { offset?: number; q?: string; outcome?: PipelineOutcome },
): Promise<Page<Pipeline>> {
  const query = new URLSearchParams({
    kind,
    limit: String(PIPELINE_PAGE_SIZE),
    offset: String(offset),
  });
  if (q.trim()) {
    query.set('q', q.trim());
  }
  if (outcome) {
    query.set('outcome', outcome);
  }
  return request<Page<Pipeline>>(`${pipelinesPath(projectId)}?${query}`);
}

export function listPipelineVersions(
  projectId: string,
  pipelineId: string,
  offset = 0,
): Promise<Page<PipelineVersion>> {
  return request<Page<PipelineVersion>>(
    `${pipelinePath(projectId, pipelineId)}/versions?offset=${offset}`,
  );
}

/** Creates a pipeline and its first immutable version. */
export function createPipeline(projectId: string, draft: PipelineDraft): Promise<PipelineVersion> {
  return postJson<PipelineVersion>(pipelinesPath(projectId), draft);
}

export function createPipelineVersion(
  projectId: string,
  pipelineId: string,
  draft: PipelineDraft,
): Promise<PipelineVersion> {
  return postJson<PipelineVersion>(`${pipelinePath(projectId, pipelineId)}/versions`, draft);
}

export function runPipelineVersion(
  projectId: string,
  pipelineId: string,
  versionId: string,
  question: string,
): Promise<QueryRun> {
  return postJson<QueryRun>(
    `${pipelinePath(projectId, pipelineId)}/versions/${encodeURIComponent(versionId)}/runs`,
    { question },
  );
}

/** Executes a draft without creating a saved pipeline version. */
export function previewPipeline(
  projectId: string,
  execution: PipelineExecution,
  question: string,
  baseVersion?: Pick<PipelineVersion, 'pipeline_id' | 'id'>,
): Promise<QueryRun> {
  return postJson<QueryRun>(`${pipelinesPath(projectId)}/preview-runs`, {
    execution,
    question,
    base_pipeline_id: baseVersion?.pipeline_id,
    base_version_id: baseVersion?.id,
  });
}
