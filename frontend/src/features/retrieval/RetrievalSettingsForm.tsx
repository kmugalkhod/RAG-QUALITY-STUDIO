import { useId } from 'react';
import { retrievalErrors, type RetrievalSettings } from './settings';
import './retrieval.css';

export function RetrievalSettingsForm({ value, onChange, disabled = false }: { value: RetrievalSettings; onChange: (value: RetrievalSettings) => void; disabled?: boolean }) {
  const id = useId();
  const errors = retrievalErrors(value);
  const cutoff = value.mode !== 'keyword' ? value.max_vector_distance : null;
  return <fieldset className="retrieval-settings-form" disabled={disabled} aria-describedby={errors.length ? `${id}-errors` : undefined}>
    <legend>Search settings</legend>
    <label>Search method<select value={value.mode} onChange={e => {
      const mode = e.target.value as RetrievalSettings['mode'];
      onChange(mode === 'keyword' ? { mode, top_k: value.top_k } : mode === 'vector' ? { mode, top_k: value.top_k, max_vector_distance: cutoff ?? null } : { mode, top_k: value.top_k, max_vector_distance: cutoff ?? null, vector_candidates: 50, keyword_candidates: 50, vector_weight: 0.5 });
    }}><option value="vector">Vector</option><option value="keyword">Keyword</option><option value="hybrid">Hybrid</option></select></label>
    <label>Top k<input type="number" min={1} max={50} step={1} value={Number.isFinite(value.top_k) ? value.top_k : ''} onChange={e => onChange({ ...value, top_k: e.target.valueAsNumber })}/></label>
    <p className="field-hint">Maximum chunks returned to the next node. Search can return fewer matches.</p>
    {value.mode !== 'keyword' && <details className="retrieval-advanced"><summary>Advanced search settings</summary>
      <label>Maximum vector distance (optional)<input type="number" min={0} max={2} step="any" placeholder="Off" value={cutoff != null && Number.isFinite(cutoff) ? cutoff : ''} onChange={e => onChange({ ...value, max_vector_distance: e.target.value === '' ? null : e.target.valueAsNumber })}/></label>
      <p className="field-hint">Leave blank for no cutoff. Lower distance is closer, not confidence.{value.mode === 'hybrid' ? ' Limits the vector branch only; keyword matches can still appear.' : ''}</p>
      {value.mode === 'hybrid' && <>
        <label>Vector candidate count<input type="number" min={value.top_k} max={200} step={1} value={Number.isFinite(value.vector_candidates) ? value.vector_candidates : ''} onChange={e => onChange({ ...value, vector_candidates: e.target.valueAsNumber })}/></label>
        <label>Keyword candidate count<input type="number" min={value.top_k} max={200} step={1} value={Number.isFinite(value.keyword_candidates) ? value.keyword_candidates : ''} onChange={e => onChange({ ...value, keyword_candidates: e.target.valueAsNumber })}/></label>
        <p className="field-hint">Candidates gathered by each branch before merging. Each count must be at least Top k.</p>
        <label>Vector weight<input type="number" min={0} max={1} step="any" value={Number.isFinite(value.vector_weight) ? value.vector_weight : ''} onChange={e => onChange({ ...value, vector_weight: e.target.valueAsNumber })}/></label>
        <p className="field-hint">Keyword weight: {Number.isFinite(value.vector_weight) ? Number((1 - value.vector_weight).toFixed(4)) : '—'}. Weights influence rank fusion, not the percentage of results. A zero-weight branch is skipped.</p>
      </>}
    </details>}
    {value.mode === 'keyword' && <p className="field-hint">Searches words and phrases in the prepared chunks. No query embedding is needed.</p>}
    {!!errors.length && <ul id={`${id}-errors`} className="error-message" aria-live="polite">{errors.map(error => <li key={error}>{error}</li>)}</ul>}
  </fieldset>;
}
