import { postJson, request } from '../../lib/api';
import type { RetrievalSettings } from '../../lib/retrieval';
import type { EmbeddingSettings, IndexPage, IndexVersion, Retrieval } from './model';

function projectPath(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}`;
}

export function getEmbeddingSettings(projectId: string): Promise<EmbeddingSettings> {
  return request<EmbeddingSettings>(`${projectPath(projectId)}/embedding-settings`);
}

export function listIndexes(projectId: string, offset = 0): Promise<IndexPage> {
  return request<IndexPage>(`${projectPath(projectId)}/indexes?offset=${offset}`);
}

export function getIndex(projectId: string, indexId: string): Promise<IndexVersion> {
  return request<IndexVersion>(`${projectPath(projectId)}/indexes/${encodeURIComponent(indexId)}`);
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
