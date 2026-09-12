import { postJson, request } from '../../lib/api';
import type { Page } from '../../lib/pagination';
import type {
  IngestionPipelineDraft,
  IngestionPipelineVersion,
  IngestionPreview,
  IngestionRun,
  IngestionRunItem,
} from './model';

function pipelinesPath(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}/pipelines`;
}

export function createIngestionPipeline(
  projectId: string,
  draft: IngestionPipelineDraft,
): Promise<IngestionPipelineVersion> {
  return postJson<IngestionPipelineVersion>(pipelinesPath(projectId), draft);
}

export function createIngestionPipelineVersion(
  projectId: string,
  pipelineId: string,
  draft: IngestionPipelineDraft,
): Promise<IngestionPipelineVersion> {
  return postJson<IngestionPipelineVersion>(
    `${pipelinesPath(projectId)}/${encodeURIComponent(pipelineId)}/versions`,
    draft,
  );
}

export function listIngestionPipelineVersions(
  projectId: string,
  pipelineId: string,
  offset = 0,
): Promise<Page<IngestionPipelineVersion>> {
  return request<Page<IngestionPipelineVersion>>(
    `${pipelinesPath(projectId)}/${encodeURIComponent(pipelineId)}/versions?offset=${offset}`,
  );
}

export function previewIngestion(
  projectId: string,
  execution: IngestionPipelineDraft['execution'],
): Promise<IngestionPreview> {
  return postJson<IngestionPreview>(
    `/projects/${encodeURIComponent(projectId)}/ingestion-previews`,
    { execution },
  );
}

export function startIngestionRun(
  projectId: string,
  pipelineId: string,
  versionId: string,
): Promise<IngestionRun> {
  return request<IngestionRun>(
    `${pipelinesPath(projectId)}/${encodeURIComponent(pipelineId)}/versions/${encodeURIComponent(versionId)}/ingestion-runs`,
    { method: 'POST' },
  );
}

export function getIngestionRun(projectId: string, runId: string): Promise<IngestionRun> {
  return request<IngestionRun>(
    `/projects/${encodeURIComponent(projectId)}/ingestion-runs/${encodeURIComponent(runId)}`,
  );
}

export function listIngestionRunItems(
  projectId: string,
  runId: string,
  offset = 0,
): Promise<Page<IngestionRunItem>> {
  return request<Page<IngestionRunItem>>(
    `/projects/${encodeURIComponent(projectId)}/ingestion-runs/${encodeURIComponent(runId)}/items?offset=${offset}`,
  );
}

export function cancelIngestionRun(projectId: string, runId: string): Promise<IngestionRun> {
  return request<IngestionRun>(
    `/projects/${encodeURIComponent(projectId)}/ingestion-runs/${encodeURIComponent(runId)}/cancel`,
    { method: 'POST' },
  );
}
