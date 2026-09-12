import { postJson } from '../../lib/api';
import type { IngestionPipelineDraft, IngestionPipelineVersion } from './model';

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
