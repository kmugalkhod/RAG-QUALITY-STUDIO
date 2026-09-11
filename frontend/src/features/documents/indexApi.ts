import { request } from '../../lib/api';
import type { Page, Run } from './api';
export interface EmbeddingConfig { provider: string; model: string; dimensions: number; endpoint_id: string; revision: string }
export interface EmbeddingSettings { configured: boolean; config: EmbeddingConfig | null; error: string | null }
export interface IndexVersion { id: string; project_id: string; version: number; embedding_config: EmbeddingConfig; status: Run['status']; chunk_count: number; embedded_count: number; attempts: number; failures: number; error: string | null; created_at: string }
export type IndexPage = Page<IndexVersion>;
export interface Evidence { rank: number; document_id: string; filename: string; content_hash: string; run_id: string; processing_version: number; ordinal: number; page_number: number | null; start_char: number; end_char: number; text: string; cosine_distance: number }
export interface Retrieval { index_id: string; index_version: number; embedding_config: EmbeddingConfig; items: Evidence[]; score_semantics: string }
const base = (project: string) => `/projects/${project}`;
export const embeddingSettings = (p: string) => request<EmbeddingSettings>(`${base(p)}/embedding-settings`);
export const listIndexes = (p: string, offset = 0) => request<IndexPage>(`${base(p)}/indexes?offset=${offset}`);
export const createIndex = (p: string) => request<IndexVersion>(`${base(p)}/indexes`, { method: 'POST' });
export const cancelIndex = (p: string, id: string) => request<IndexVersion>(`${base(p)}/indexes/${id}/cancel`, { method: 'POST' });
export const retrieve = (p: string, index_id: string, query: string, top_k: number) => request<Retrieval>(`${base(p)}/retrieval`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ index_id, query, top_k }) });

export const getIndex = (p: string, id: string) => request<IndexVersion>(`${base(p)}/indexes/${id}`);
