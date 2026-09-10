import { request } from '../../lib/api';
import type { Page } from '../documents/api';
import type { QueryRun } from '../playground/api';
export const order = ['question', 'retriever', 'prompt', 'llm', 'answer'] as const;
export type Kind = typeof order[number];
export type ExecutionNode = { id: string; type: Kind; index_id?: string; top_k?: number; template?: string; model?: string; max_tokens?: number; temperature?: number };
export type Execution = { schema_version: 1; nodes: ExecutionNode[]; edges: { source: string; target: string }[] };
export type Draft = { name: string; execution: Execution; layout: { positions: Record<string, { x: number; y: number }> } };
export type Version = Draft & { id: string; pipeline_id: string; project_id: string; version: number; created_at: string };
export type Pipeline = { id: string; name: string };
export type Options = { models: string[]; template: string; max_tokens: number; context_tokens: number; error: string | null };
const base = (p: string) => `/projects/${p}/pipelines`;
export const options = (p: string) => request<Options>(`${base(p)}/options`);
export const list = (p: string, offset = 0) => request<Page<Pipeline>>(`${base(p)}?offset=${offset}`);
export const versions = (p: string, id: string, offset = 0) => request<Page<Version>>(`${base(p)}/${id}/versions?offset=${offset}`);
export const save = (p: string, draft: Draft, id?: string) => request<Version>(`${base(p)}${id ? `/${id}/versions` : ''}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(draft) });
export const run = (p: string, v: Version, question: string) => request<QueryRun>(`${base(p)}/${v.pipeline_id}/versions/${v.id}/runs`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) });
export const readRun = (p: string, id: string) => request<QueryRun>(`/projects/${p}/query-runs/${id}`);
export async function allPages<T>(fetch: (offset: number) => Promise<Page<T>>) {
  const all: T[] = [];
  for (let offset = 0;;) { const page = await fetch(offset); all.push(...page.items); offset += page.limit; if (offset >= page.total) return all; }
}
export function validate(execution: Execution, opts?: Options, readyIds?: string[]) {
  const errors: string[] = [];
  if (execution.nodes.length !== 5 || order.some(k => execution.nodes.filter(n => n.type === k).length !== 1)) errors.push('Require exactly one Question, Retriever, Prompt, LLM and Answer node.');
  const ids = order.map(k => execution.nodes.find(n => n.type === k)?.id);
  if (execution.edges.length !== 4 || order.slice(1).some((_, i) => !execution.edges.some(e => e.source === ids[i] && e.target === ids[i + 1]))) errors.push('Connect Question → Retriever → Prompt → LLM → Answer only; branches, cycles and disconnected nodes are unsupported.');
  for (const n of execution.nodes) {
    if (n.type === 'retriever') {
      if (!n.index_id || (readyIds && !readyIds.includes(n.index_id))) errors.push('Retriever: choose a ready index in Node settings.');
      if (!Number.isInteger(n.top_k) || n.top_k! < 1 || n.top_k! > 50) errors.push('Retriever: top k must be a whole number from 1 to 50.');
    }
    if (n.type === 'prompt' && (!n.template?.includes('{question}') || !n.template.includes('{context}') || /[{}]/.test(n.template.replaceAll('{question}', '').replaceAll('{context}', '')) || n.template.length > 8000)) errors.push('Prompt: include {question} and {context}; other braces or expressions are unsupported.');
    if (n.type === 'llm' && (!n.model || (opts && !opts.models.includes(n.model)) || !Number.isInteger(n.max_tokens) || n.max_tokens! < 128 || n.max_tokens! > 8192 || (opts && n.max_tokens! + 1024 >= opts.context_tokens) || !Number.isFinite(n.temperature) || n.temperature! < 0 || n.temperature! > 2)) errors.push('LLM: select a configured model, output tokens within the server budget and temperature from 0 to 2.');
  }
  return errors;
}

// PostgreSQL JSONB object key order is not meaningful; compare canonical data.
export function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value !== null && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(',')}}`;
  return JSON.stringify(value);
}
