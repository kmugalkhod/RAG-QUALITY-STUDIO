import { scoreText } from '../retrieval/settings';
import { useEffect } from 'react';
import { Sparkles } from 'lucide-react';
import { AnswerText } from '../../components/AnswerText';
import type * as api from './api';

export function RunResult({ run, onCitation }: { run: api.QueryRun; onCitation?: (label: string) => void }) {
  const s = run.snapshot;
  return <section className="query-result" aria-label="Query result">
    <div className="chat-question"><span className="field-hint">You</span><p>{run.question}</p></div>
    <h2 className="assistant-label"><Sparkles size={16}/>{run.status === 'insufficient_evidence' ? 'Insufficient evidence' : run.status === 'failed' ? 'Answer failed' : run.status === 'running' ? 'Run in progress' : 'Answer'}</h2>
    {run.error && <p role="alert" className="error-message">{run.error}</p>}
    {run.status === 'running' && <p role="status">Generating the answer…</p>}
    {run.answer && <div className="rag-answer"><AnswerText text={run.answer} citations={s.citations?.valid} onCitation={onCitation}/></div>}
    {!!s.citations?.invalid.length && <p role="alert" className="error-message">Invalid citation references: {s.citations.invalid.join(', ')}. These references were not supplied to the model.</p>}
    {s.citations?.missing && <p role="alert" className="error-message">The answer has no citation references. Review its claims against the evidence.</p>}
  </section>;
}

export function RunInspector({ run, mode, sourceLabel = '', focusRequest = 0 }: { run: api.QueryRun; mode: 'sources' | 'details'; sourceLabel?: string; focusRequest?: number }) {
  const s = run.snapshot;
  const duration = (n: number | null) => n == null ? 'Unavailable' : `${(n / 1000).toFixed(2)} s`;
  const firstSource = s.evidence[0]?.label === sourceLabel;
  useEffect(() => {
    if (mode !== 'sources' || !sourceLabel) return;
    const el = document.getElementById(`evidence-${sourceLabel}`);
    el?.focus({ preventScroll: true });
    const container = el?.closest('.answer-inspector');
    if (container && firstSource) container.scrollTop = 0;
    else el?.scrollIntoView?.({ block: 'start' });
  }, [run.id, mode, sourceLabel, firstSource, focusRequest]);
  return <section className="answer-inspector" aria-label={mode === 'sources' ? 'Supporting evidence' : 'Answer details'}>
    {mode === 'sources' ? <><h2>Sources ({s.evidence.length})</h2><p className="field-hint">Evidence used for this answer. Check that it supports the claims.</p>
    {s.evidence.map(e => <article key={e.label} id={`evidence-${e.label}`} tabIndex={-1}><h3>[{e.label}] {e.filename}</h3><p className="field-hint">{e.page_number ? `Page ${e.page_number} · ` : ''}Passage {e.ordinal + 1} · Rank {e.rank}</p><p className="rag-source-text">{e.text}</p><details className="source-metadata"><summary>Source metadata</summary><p>Processing version {e.processing_version} · {scoreText(e)}</p><p>Distance: lower is closer. Keyword and RRF scores: higher ranks first. Scores are not confidence.</p></details></article>)}
    {!s.evidence.length && <p>No evidence was sent.</p>}
    {!!s.omitted_count && <p className="field-hint">{s.omitted_count} chunks omitted for context capacity.</p>}
    </> : <><h2>Answer details</h2><p className="field-hint">{s.pipeline_preview ? `Test draft${s.base_version ? ` · Based on version ${s.base_version}` : ''}` : run.pipeline_version_id ? `Pipeline version ${s.pipeline_version}` : 'Default answer settings'} · {run.status.replaceAll('_', ' ')}</p><p>Document set version {run.index_version} · Up to {s.top_k} source passages</p><p>{s.actual_model || s.generation_config?.model || 'Model unavailable'}</p>
    <dl className="rag-metrics"><dt>Finding passages</dt><dd>{duration(s.retrieval_ms)}</dd><dt>Writing answer</dt><dd>{duration(s.generation_ms)}</dd><dt>Total</dt><dd>{duration(s.total_ms)}</dd><dt>Answer cost</dt><dd>{s.cost_usd == null ? 'Unavailable' : `$${s.cost_usd.toFixed(6)} (provider reported)`}</dd><dt>Model usage</dt><dd>{s.usage ? Object.entries(s.usage).map(([k,v]) => `${k.replaceAll('_', ' ')}: ${v}`).join(' · ') : 'Unavailable'}</dd></dl>
    {s.cost_basis && <p className="field-hint">{s.cost_basis}</p>}
    {s.retrieval && <details className="source-metadata"><summary>Retrieval settings and results</summary><pre className="rag-source-text">{JSON.stringify({ settings: s.retrieval, result: s.retrieval_result }, null, 2)}</pre></details>}
    {s.messages && <details className="source-metadata"><summary>Effective prompt and generation settings</summary><pre className="rag-source-text">{JSON.stringify({ messages: s.messages, generation: s.generation_config }, null, 2)}</pre></details>}
    <details className="source-metadata"><summary>Exact pipeline settings</summary><pre className="rag-source-text">{JSON.stringify(s.pipeline_execution, null, 2)}</pre></details><details className="source-metadata"><summary>Run identity</summary><p>Run {run.id}</p>{run.pipeline_version_id && <p>Pipeline version {run.pipeline_version_id}</p>}</details></>}
  </section>;
}
