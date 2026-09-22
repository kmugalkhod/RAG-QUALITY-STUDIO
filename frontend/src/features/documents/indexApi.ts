import { postJson, request } from '../../lib/api';
import type { RetrievalSettings } from '../../lib/retrieval';
import type {
  EmbeddingSettings,
  IndexPage,
  IndexRecordPage,
  IndexVersion,
  KnowledgeSet,
  Retrieval,
  SourceSnapshot,
  SourceSnapshotIndex,
  SourceSnapshotMember,
  SourceSnapshotPage,
} from './model';
import type { Page } from '../../lib/pagination';
import type { IngestionPipelineVersion } from '../ingestion-pipelines/model';
import type { Pipeline } from '../pipelines/model';

function projectPath(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}`;
}

export function getEmbeddingSettings(projectId: string): Promise<EmbeddingSettings> {
  return request<EmbeddingSettings>(`${projectPath(projectId)}/embedding-settings`);
}

export function listIndexes(projectId: string, offset = 0): Promise<IndexPage> {
  return request<IndexPage>(`${projectPath(projectId)}/indexes?offset=${offset}`);
}

export function listKnowledgeSets(projectId: string, offset = 0): Promise<Page<KnowledgeSet>> {
  return request<Page<KnowledgeSet>>(`${projectPath(projectId)}/knowledge-sets?offset=${offset}`);
}

export function listSourceSnapshots(projectId: string, offset = 0): Promise<SourceSnapshotPage> {
  return request<SourceSnapshotPage>(`${projectPath(projectId)}/source-snapshots?offset=${offset}`);
}

export function getSourceSnapshot(projectId: string, snapshotId: string): Promise<SourceSnapshot> {
  return request<SourceSnapshot>(
    `${projectPath(projectId)}/source-snapshots/${encodeURIComponent(snapshotId)}`,
  );
}

export function listSourceSnapshotItems(
  projectId: string,
  snapshotId: string,
  offset = 0,
): Promise<Page<SourceSnapshotMember>> {
  return request<Page<SourceSnapshotMember>>(
    `${projectPath(projectId)}/source-snapshots/${encodeURIComponent(snapshotId)}/items?offset=${offset}`,
  );
}

export function listSourceSnapshotIndexes(
  projectId: string,
  snapshotId: string,
  offset = 0,
): Promise<Page<SourceSnapshotIndex>> {
  return request<Page<SourceSnapshotIndex>>(
    `${projectPath(projectId)}/source-snapshots/${encodeURIComponent(snapshotId)}/indexes?offset=${offset}`,
  );
}

export function startSnapshotBuild(
  projectId: string,
  pipelineId: string,
  versionId: string,
  snapshotId: string,
  destination: { kind: 'new'; name: string } | { kind: 'existing'; knowledge_set_id: string },
) {
  return postJson<import('../ingestion-pipelines/model').IngestionRun>(
    `${projectPath(projectId)}/pipelines/${encodeURIComponent(pipelineId)}/versions/${encodeURIComponent(versionId)}/ingestion-runs`,
    {
      source_input: { kind: 'snapshot', source_snapshot_id: snapshotId },
      destination,
    },
  );
}

export function refreshSource(projectId: string, pipelineId: string, versionId: string) {
  return postJson<import('../ingestion-pipelines/model').IngestionRun>(
    `${projectPath(projectId)}/pipelines/${encodeURIComponent(pipelineId)}/versions/${encodeURIComponent(versionId)}/ingestion-runs`,
    { source_input: { kind: 'refresh' } },
  );
}

export function getIngestionRun(projectId: string, runId: string) {
  return request<import('../ingestion-pipelines/model').IngestionRun>(
    `${projectPath(projectId)}/ingestion-runs/${encodeURIComponent(runId)}`,
  );
}

export function listIngestionPipelines(projectId: string, offset = 0): Promise<Page<Pipeline>> {
  return request<Page<Pipeline>>(
    `${projectPath(projectId)}/pipelines?kind=ingestion&offset=${offset}`,
  );
}

export function listIngestionPipelineVersions(
  projectId: string,
  pipelineId: string,
  offset = 0,
): Promise<Page<IngestionPipelineVersion>> {
  return request<Page<IngestionPipelineVersion>>(
    `${projectPath(projectId)}/pipelines/${encodeURIComponent(pipelineId)}/versions?offset=${offset}`,
  );
}

export function getIndex(projectId: string, indexId: string): Promise<IndexVersion> {
  return request<IndexVersion>(`${projectPath(projectId)}/indexes/${encodeURIComponent(indexId)}`);
}

export function listIndexRecords(
  projectId: string,
  indexId: string,
  offset = 0,
): Promise<IndexRecordPage> {
  return request<IndexRecordPage>(
    `${projectPath(projectId)}/indexes/${encodeURIComponent(indexId)}/records?offset=${offset}`,
  );
}

export function createIndex(projectId: string): Promise<IndexVersion> {
  return request<IndexVersion>(`${projectPath(projectId)}/indexes`, { method: 'POST' });
}

export function cancelIndex(projectId: string, indexId: string): Promise<IndexVersion> {
  return request<IndexVersion>(
    `${projectPath(projectId)}/indexes/${encodeURIComponent(indexId)}/cancel`,
    { method: 'POST' },
  );
}

export function retrieve(
  projectId: string,
  indexId: string,
  query: string,
  retrieval: RetrievalSettings,
): Promise<Retrieval> {
  return postJson<Retrieval>(`${projectPath(projectId)}/retrieval`, {
    index_id: indexId,
    query,
    retrieval,
  });
}
