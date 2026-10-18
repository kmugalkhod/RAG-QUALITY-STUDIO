import type { Evidence } from '../documents/model';
import type { RetrievalSettings } from '../../lib/retrieval';
export interface QueryRun {
  pipeline_version_id?: string | null;
  id: string;
  project_id: string;
  index_id: string;
  index_version: number;
  question: string;
  answer: string | null;
  status: 'running' | 'succeeded' | 'insufficient_evidence' | 'failed';
  error: string | null;
  created_at: string;
  snapshot: {
    retrieval?: RetrievalSettings;
    retrieval_result?: unknown;
    pipeline_preview?: boolean;
    base_pipeline_id?: string | null;
    base_version_id?: string | null;
    base_version?: number | null;
    pipeline_name?: string | null;
    pipeline_version?: number;
    pipeline_execution?: { nodes: unknown[] };
    messages?: { role: string; content: string }[];
    prompt_template?: string;
    top_k: number;
    evidence: (Evidence & { label: string })[];
    omitted_count?: number;
    generation_config?: { model: string };
    actual_model?: string;
    prompt_version: string;
    citations?: { valid: string[]; invalid: string[]; missing: boolean; semantics: string };
    retrieval_ms: number | null;
    // Present when the pipeline has a Rerank step (spec 0015).
    rerank?: RerankRecord;
    rerank_ms?: number | null;
    generation_ms: number | null;
    total_ms: number | null;
    usage: Record<string, number> | null;
    cost_usd: number | null;
    cost_basis: string | null;
  };
}

export interface RerankRecord {
  node_id: string;
  model: string;
  actual_model: string | null;
  prompt_version: string;
  top_n: number;
  candidate_count: number;
  candidates_read: number;
  returned_count: number;
  status: 'reranked' | 'fallback' | 'skipped';
  message: string | null;
  cost_usd: number | null;
  cost_basis: string | null;
  rerank_ms: number | null;
}

export type PlaygroundMode = 'retrieval' | 'pipeline';
export type PlaygroundPanel = 'settings' | 'history' | 'sources' | 'details' | 'retrieval' | null;
