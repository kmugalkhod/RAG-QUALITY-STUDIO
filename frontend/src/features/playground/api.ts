import { request } from '../../lib/api';
import type { Evidence } from '../documents/indexApi';
import type { Page } from '../documents/api';
export interface QueryRun {
  pipeline_version_id?: string | null;
  id: string; project_id: string; index_id: string; index_version: number; question: string;
  answer: string | null; status: 'running' | 'succeeded' | 'insufficient_evidence' | 'failed'; error: string | null; created_at: string;
  snapshot: { pipeline_version?: number; pipeline_execution?: { nodes: unknown[] }; messages?: { role: string; content: string }[]; prompt_template?: string; top_k: number; evidence: (Evidence & { label: string })[]; omitted_count?: number;
    generation_config?: { model: string }; actual_model?: string; prompt_version: string;
    citations?: { valid: string[]; invalid: string[]; missing: boolean; semantics: string };
    retrieval_ms: number | null; generation_ms: number | null; total_ms: number | null;
    usage: Record<string, number> | null; cost_usd: number | null; cost_basis: string | null };
}
export const listRuns = (p: string, offset = 0) => request<Page<QueryRun>>(`/projects/${p}/query-runs?offset=${offset}`);
export const ask = (p: string, index_id: string, question: string, top_k: number) => request<QueryRun>(`/projects/${p}/query-runs`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ index_id, question, top_k }) }, 180000);
