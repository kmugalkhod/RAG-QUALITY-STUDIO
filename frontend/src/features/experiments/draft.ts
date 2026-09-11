import type { Metric } from './api';
export type ExperimentDraft = { name: string; dataset: string; a: string; b: string; metrics: Metric[] };
const metrics: Metric[] = ['faithfulness', 'response_relevancy', 'context_recall'];
export const emptyDraft = (): ExperimentDraft => ({ name: '', dataset: '', a: '', b: '', metrics: [...metrics] });
const key = (project: string) => `experiment-draft:v1:${project}`;
export function readDraft(project: string): ExperimentDraft {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(key(project)) || 'null');
    if (!value || typeof value !== 'object') return emptyDraft();
    const d = value as Record<string, unknown>;
    const string = (name: string, max: number) => typeof d[name] === 'string' ? d[name].slice(0, max) : '';
    const a = string('a', 36); const b = string('b', 36);
    return { name: string('name', 120), dataset: string('dataset', 36), a, b: b === a ? '' : b, metrics: Array.isArray(d.metrics) ? metrics.filter(m => d.metrics instanceof Array && d.metrics.includes(m)) : [...metrics] };
  } catch { return emptyDraft(); }
}
export function saveDraft(project: string, draft: ExperimentDraft): boolean {
  try { sessionStorage.setItem(key(project), JSON.stringify(draft)); return true; }
  catch { return false; }
}
