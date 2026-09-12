import { postJson, request } from '../../lib/api';
import type { Page } from '../../lib/pagination';
import type { Chunk, Document, Run } from './model';

export interface UploadSettings {
  max_upload_bytes: number;
}

function documentsPath(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}/documents`;
}

function documentPath(projectId: string, documentId: string): string {
  return `${documentsPath(projectId)}/${encodeURIComponent(documentId)}`;
}

export function getUploadSettings(projectId: string): Promise<UploadSettings> {
  return request<UploadSettings>(`/projects/${encodeURIComponent(projectId)}/upload-settings`);
}

export function listDocuments(projectId: string, offset = 0): Promise<Page<Document>> {
  return request<Page<Document>>(`${documentsPath(projectId)}?offset=${offset}`);
}

export function uploadDocument(projectId: string, file: File): Promise<Document> {
  const body = new FormData();
  body.append('file', file);
  return request<Document>(documentsPath(projectId), { method: 'POST', body });
}

export function listProcessingRuns(
  projectId: string,
  documentId: string,
  offset = 0,
): Promise<Page<Run>> {
  return request<Page<Run>>(`${documentPath(projectId, documentId)}/runs?offset=${offset}`);
}

export function startProcessingRun(
  projectId: string,
  documentId: string,
  chunkSize: number,
  overlap: number,
): Promise<Run> {
  return postJson<Run>(`${documentPath(projectId, documentId)}/runs`, {
    chunk_size: chunkSize,
    overlap,
  });
}

export function cancelProcessingRun(
  projectId: string,
  documentId: string,
  runId: string,
): Promise<Run> {
  return request<Run>(
    `${documentPath(projectId, documentId)}/runs/${encodeURIComponent(runId)}/cancel`,
    { method: 'POST' },
  );
}

export function listDocumentChunks(
  projectId: string,
  documentId: string,
  runId: string,
  offset = 0,
): Promise<Page<Chunk>> {
  return request<Page<Chunk>>(
    `${documentPath(projectId, documentId)}/runs/${encodeURIComponent(runId)}/chunks?offset=${offset}`,
  );
}
