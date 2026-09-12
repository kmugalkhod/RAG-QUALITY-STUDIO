import { postJson, request } from '../../lib/api';
import type { Page } from '../../lib/pagination';
import type { Dataset, Detail, Experiment, Metric, Preview } from './model';

export interface EvaluationOptions {
  model: string;
  metrics: Record<Metric, string>;
  error: string | null;
  max_rows: number;
  max_bytes: number;
}

function projectPath(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}`;
}

export function listDatasets(projectId: string, offset = 0): Promise<Page<Dataset>> {
  return request<Page<Dataset>>(`${projectPath(projectId)}/datasets?offset=${offset}`);
}

export function listExperiments(projectId: string, offset = 0): Promise<Page<Experiment>> {
  return request<Page<Experiment>>(`${projectPath(projectId)}/experiments?offset=${offset}`);
}

export function getExperiment(projectId: string, experimentId: string): Promise<Detail> {
  return request<Detail>(
    `${projectPath(projectId)}/experiments/${encodeURIComponent(experimentId)}`,
  );
}

export function getEvaluationOptions(projectId: string): Promise<EvaluationOptions> {
  return request<EvaluationOptions>(`${projectPath(projectId)}/experiments/options`);
}

export function previewDataset(projectId: string, file: File): Promise<Preview> {
  const body = new FormData();
  body.append('file', file);
  return request<Preview>(`${projectPath(projectId)}/datasets/preview`, { method: 'POST', body });
}

export function importDataset(
  projectId: string,
  file: File,
  name: string,
  contentHash: string,
  datasetId: string,
): Promise<Dataset> {
  const body = new FormData();
  body.append('file', file);
  body.append('name', name);
  body.append('content_hash', contentHash);
  if (datasetId) {
    body.append('dataset_id', datasetId);
  }
  return request<Dataset>(`${projectPath(projectId)}/datasets`, { method: 'POST', body });
}

export function startExperiment(
  projectId: string,
  name: string,
  datasetVersionId: string,
  pipelineVersionIds: string[],
  metrics: Metric[],
): Promise<Experiment> {
  return postJson<Experiment>(`${projectPath(projectId)}/experiments`, {
    name,
    dataset_version_id: datasetVersionId,
    pipeline_version_ids: pipelineVersionIds,
    metrics,
  });
}

export function cancelExperiment(projectId: string, experimentId: string): Promise<Experiment> {
  return postJson<Experiment>(
    `${projectPath(projectId)}/experiments/${encodeURIComponent(experimentId)}/cancel`,
    {},
  );
}
