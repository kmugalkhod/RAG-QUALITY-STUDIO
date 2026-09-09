import { request, type Project } from '../../lib/api';
export interface Page<T> { items: T[]; total: number; limit: number; offset: number }
export interface Run {
  id: string; document_id: string; version: number; chunk_size: number; overlap: number;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  progress: number; error: string | null; chunk_count: number; attempts: number;
  config_version: string; parser_version: string; created_at: string;
}
export interface Document { id: string; filename: string; size_bytes: number; content_hash: string; created_at: string; latest_run: Run | null }
export interface Chunk { ordinal: number; page_number: number | null; start_char: number; end_char: number; text: string }
const base = (project: string) => `/projects/${project}`;
const doc = (project: string, document: string) => `${base(project)}/documents/${document}`;
export const getProject = (p: string) => request<Project>(base(p));
export const getSettings = (p: string) => request<{ max_upload_bytes: number }>(`${base(p)}/upload-settings`);
export const listDocuments = (p: string, offset = 0) => request<Page<Document>>(`${base(p)}/documents?offset=${offset}`);
export const uploadDocument = (p: string, file: File) => { const body = new FormData(); body.append('file', file); return request<Document>(`${base(p)}/documents`, { method: 'POST', body }); };
export const listRuns = (p: string, d: string, offset = 0) => request<Page<Run>>(`${doc(p, d)}/runs?offset=${offset}`);
export const startRun = (p: string, d: string, chunk_size: number, overlap: number) => request<Run>(`${doc(p, d)}/runs`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ chunk_size, overlap }) });
export const cancelRun = (p: string, d: string, r: string) => request<Run>(`${doc(p, d)}/runs/${r}/cancel`, { method: 'POST' });
export const listChunks = (p: string, d: string, r: string, offset = 0) => request<Page<Chunk>>(`${doc(p, d)}/runs/${r}/chunks?offset=${offset}`);
