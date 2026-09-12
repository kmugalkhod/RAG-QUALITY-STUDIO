export type RetrievalSettings =
  | { mode: 'vector'; top_k: number; max_vector_distance?: number | null }
  | { mode: 'keyword'; top_k: number }
  | { mode: 'hybrid'; top_k: number; max_vector_distance?: number | null; vector_candidates: number; keyword_candidates: number; vector_weight: number };

export const defaultRetrieval = (top_k = 5): RetrievalSettings => ({ mode: 'vector', top_k, max_vector_distance: null });
export const nodeRetrieval = (node?: { retrieval?: RetrievalSettings; top_k?: number }): RetrievalSettings => node?.retrieval ?? defaultRetrieval(node?.top_k ?? 5);
export const retrievalSummary = (s: RetrievalSettings) => `${s.mode[0].toUpperCase()}${s.mode.slice(1)} · Top ${s.top_k}`;
export function retrievalErrors(s: RetrievalSettings): string[] {
  const errors: string[] = [];
  if (!['vector', 'keyword', 'hybrid'].includes(s.mode)) errors.push('Choose a supported search method.');
  if (!Number.isInteger(s.top_k) || s.top_k < 1 || s.top_k > 50) errors.push('Top k must be a whole number from 1 to 50.');
  if (s.mode !== 'keyword' && s.max_vector_distance != null && (!Number.isFinite(s.max_vector_distance) || s.max_vector_distance < 0 || s.max_vector_distance > 2)) errors.push('Maximum vector distance must be from 0 to 2, or off.');
  if (s.mode === 'hybrid') {
    if ([s.vector_candidates, s.keyword_candidates].some(v => !Number.isInteger(v) || v < s.top_k || v > 200)) errors.push('Each candidate count must be a whole number between Top k and 200.');
    if (!Number.isFinite(s.vector_weight) || s.vector_weight < 0 || s.vector_weight > 1) errors.push('Vector weight must be from 0 to 1.');
  }
  return errors;
}

export function scoreText(item: { cosine_distance: number | null; lexical_score?: number | null; fusion_score?: number | null }): string {
  return [item.cosine_distance != null ? `Cosine distance ${item.cosine_distance.toFixed(4)}` : '', item.lexical_score != null ? `Keyword score ${item.lexical_score.toFixed(4)}` : '', item.fusion_score != null ? `RRF score ${item.fusion_score.toFixed(6)}` : ''].filter(Boolean).join(' · ');
}
