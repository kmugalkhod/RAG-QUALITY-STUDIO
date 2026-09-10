import { useEffect, useState, type FormEvent } from 'react';
import { Button } from '../../components/ui/button';
import { listIndexes, type IndexVersion } from '../documents/indexApi';
import * as api from './api';

const errorText = (e: unknown) => e instanceof Error ? e.message : 'Request failed.';
export function Playground({ projectId }: { projectId: string }) {
  const [indexes, setIndexes] = useState<IndexVersion[]>([]);
  const [indexId, setIndexId] = useState('');
  const [question, setQuestion] = useState('');
  const [topK, setTopK] = useState(5);
  const [runs, setRuns] = useState<api.QueryRun[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [run, setRun] = useState<api.QueryRun>();
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState('');
  useEffect(() => {
    let disposed = false;
    setLoading(true);
    async function load() {
      const all: IndexVersion[] = [];
      let start = 0;
      do {
        const page = await listIndexes(projectId, start);
        all.push(...page.items.filter(i => i.status === 'succeeded'));
        start += page.limit;
        if (start >= page.total) break;
      } while (!disposed);
      const history = await api.listRuns(projectId, offset);
      if (!disposed) { setIndexes(all); setRuns(history.items); setTotal(history.total); setLoadError(''); }
    }
    void load().catch(e => { if (!disposed) setLoadError(errorText(e)); }).finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [projectId, offset, revision]);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setRun(undefined); setBusy(true);
    try { setRun(await api.ask(projectId, indexId, question.trim(), topK)); setOffset(0); setRevision(r => r + 1); }
    catch (e) { setError(`${errorText(e)} Refresh query history before retrying; an interrupted response may already have a saved run.`); }
    finally { setBusy(false); }
  }
  return <>
    <a className="back-link" href={`#/projects/${projectId}`}>Back to Knowledge Base</a>
    <div className="page-heading"><div><h1>RAG playground</h1><p>Ask a question and inspect the evidence used in the answer.</p></div></div>
    <section className="create-panel" aria-labelledby="question-title"><h2 id="question-title">Ask your documents</h2>
      <p className="field-hint">Each question is independent. Previous questions and answers are never included.</p>
      {loading && <p role="status">Loading indexes and history…</p>}
      {loadError && <p role="alert" className="error-message">{loadError}</p>}
      {!loading && !loadError && !indexes.length && <p>No ready indexes. Process and index documents in the Knowledge Base first.</p>}
      <form onSubmit={submit} aria-busy={busy}>
        <div className="rag-settings"><div><label htmlFor="rag-index">Ready index</label><select id="rag-index" required value={indexId} disabled={busy} onChange={e => setIndexId(e.target.value)}><option value="">Select a ready version</option>{indexes.map(i => <option key={i.id} value={i.id}>Index {i.version} · {i.chunk_count} chunks</option>)}</select></div>
        <div><label htmlFor="rag-top-k">Top k</label><input id="rag-top-k" type="number" min={1} max={50} required value={topK} disabled={busy} onChange={e => setTopK(e.target.valueAsNumber)}/></div></div>
        <label htmlFor="rag-question">Question</label><textarea id="rag-question" required maxLength={8000} rows={3} value={question} disabled={busy} onChange={e => setQuestion(e.target.value)}/>
        <Button type="submit" disabled={busy || !indexId || !question.trim()}>{busy ? 'Generating answer…' : 'Ask question'}</Button>
      </form>
      {busy && <p role="status">Retrieving evidence and generating an answer…</p>}
      {error && <p role="alert" className="error-message">{error}</p>}
    </section>
    {run && <RunResult run={run}/>}
    <section className="project-section" aria-labelledby="history-title"><div className="section-heading"><h2 id="history-title">Query history</h2><Button variant="outline" disabled={busy || loading} onClick={() => setRevision(r => r + 1)}>Refresh history</Button></div>
      {!loading && !runs.length && <p>No saved questions yet.</p>}
      <ul className="document-list">{runs.map(item => <li key={item.id}><div><button className="document-name" disabled={busy} onClick={() => setRun(item)}>{item.question}</button><p>Index {item.index_version} · {item.status.replaceAll('_', ' ')} · {new Date(item.created_at).toLocaleString()}</p></div></li>)}</ul>
      <nav className="pagination" aria-label="Query history pages"><Button variant="outline" disabled={busy || loading || offset === 0} onClick={() => setOffset(o => o - 20)}>Previous queries</Button><span>Page {offset / 20 + 1}</span><Button variant="outline" disabled={busy || loading || offset + 20 >= total} onClick={() => setOffset(o => o + 20)}>Next queries</Button></nav>
    </section>
  </>;
}

export function RunResult({ run }: { run: api.QueryRun }) {
  const s = run.snapshot;
  const focusSource = (label: string) => { const el = document.getElementById(`evidence-${label}`); el?.focus(); el?.scrollIntoView({ block: 'center' }); };
  const duration = (n: number | null) => n == null ? 'Unavailable' : `${(n / 1000).toFixed(2)} s`;
  return <section className="project-section" aria-label="Query result">
    <h2>{run.status === 'insufficient_evidence' ? 'Insufficient evidence' : run.status === 'failed' ? 'Answer failed' : run.status === 'running' ? 'Run in progress' : 'Answer'}</h2>
    <p className="field-hint">Saved index {run.index_version} · Top k {s.top_k} · {s.actual_model || s.generation_config?.model || 'Model unavailable'}</p>
    <p><strong>{run.question}</strong></p>
    {run.error && <p role="alert" className="error-message">{run.error}</p>}
    {run.status === 'running' && <p role="status">Refresh history to check this run. Interrupted runs are marked failed after five minutes.</p>}
    <div className="rag-result"><div>
      {run.answer && <p className="rag-answer">{run.answer.split(/(\[[^\]\n[]+\])/g).map((part, i) => /^\[.*\]$/.test(part) && s.citations?.valid.includes(part.slice(1, -1)) ? <button className="citation-link" key={i} onClick={() => focusSource(part.slice(1, -1))}>{part}</button> : <span key={i}>{part}</span>)}</p>}
      {!!s.citations?.invalid.length && <p role="alert" className="error-message">Invalid citation references: {s.citations.invalid.join(', ')}. These references were not supplied to the model.</p>}
      {s.citations?.missing && <p role="alert" className="error-message">The answer has no citation references. Review its claims against the evidence.</p>}
      <p className="field-hint">Citation checks validate source references only. They do not establish whether the source supports the answer. Prompts do not guarantee grounding or prevent prompt injection.</p>
      <dl className="rag-metrics"><dt>Retrieval</dt><dd>{duration(s.retrieval_ms)}</dd><dt>Generation</dt><dd>{duration(s.generation_ms)}</dd><dt>Total</dt><dd>{duration(s.total_ms)}</dd><dt>Generation cost</dt><dd>{s.cost_usd == null ? 'Unavailable' : `$${s.cost_usd.toFixed(6)} (provider reported)`}</dd><dt>Token usage</dt><dd>{s.usage ? Object.entries(s.usage).map(([k,v]) => `${k.replaceAll('_', ' ')}: ${v}`).join(' · ') : 'Unavailable'}</dd></dl>
      {s.cost_basis && <p className="field-hint">{s.cost_basis}</p>}
    </div><aside className="rag-evidence" aria-label="Supporting evidence"><h3>Evidence sent to the model</h3><p className="field-hint">{s.evidence.length} included · {s.omitted_count ?? 0} omitted for context capacity. Cosine distance is not confidence; lower is closer.</p>
      {!s.evidence.length && <p>No evidence was sent.</p>}
      {s.evidence.map(e => <article key={e.label} id={`evidence-${e.label}`} tabIndex={-1}><h4>[{e.label}] {e.filename}</h4><p className="field-hint">{e.page_number ? `Page ${e.page_number} · ` : ''}Chunk {e.ordinal} · Processing version {e.processing_version} · Rank {e.rank} · Distance {e.cosine_distance.toFixed(4)}</p><p className="rag-source-text">{e.text}</p></article>)}
    </aside></div>
  </section>;
}
