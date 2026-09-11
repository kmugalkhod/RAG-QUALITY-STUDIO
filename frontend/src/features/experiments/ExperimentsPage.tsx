import { useEffect, useRef, useState } from 'react';
import { Button } from '../../components/ui/button';
import { allPages, list, versions, type Version } from '../pipelines/api';
import * as api from './api';
import './experiments.css';

const metrics = Object.keys(api.metricLabel) as api.Metric[];
const number = (n: number | null | undefined, digits = 3) => n == null ? 'Unavailable' : n.toLocaleString(undefined, { maximumFractionDigits: digits });
const readable = (text: string) => text.replaceAll('_', ' ');
const money = (n: number | null | undefined) => n == null ? 'Unavailable' : `$${n.toFixed(6)}`;
function Questions({ rows }: { rows: api.Row[] }) {
  return <div className="experiment-table" tabIndex={0} aria-label="Dataset questions"><table><thead><tr><th scope="col">Question</th><th scope="col">Reference answer</th></tr></thead><tbody>{rows.map((r, i) => <tr key={i}><td>{r.question}</td><td>{r.reference_answer || 'No reference — context recall unavailable'}</td></tr>)}</tbody></table></div>;
}
function Configuration({ version }: { version: Version | api.Candidate }) {
  const retriever = version.execution.nodes.find(n => n.type === 'retriever');
  const llm = version.execution.nodes.find(n => n.type === 'llm');
  return <p className="candidate-settings"><strong>{version.name} · v{version.version}</strong><br/>{llm?.model} · top k {retriever?.top_k} · temperature {llm?.temperature} · max output {llm?.max_tokens}<br/>Index {'index_version' in version ? `${version.index_version} · ` : ''}<span>{retriever?.index_id}</span></p>;
}
export function ExperimentsPage({ projectId, experimentId }: { projectId: string; experimentId?: string }) {
  const [datasets, setDatasets] = useState<api.Dataset[]>([]);
  const [pipelines, setPipelines] = useState<Version[]>([]);
  const [history, setHistory] = useState<api.Experiment[]>([]);
  const [options, setOptions] = useState<Awaited<ReturnType<typeof api.options>>>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [dataset, setDataset] = useState('');
  const [a, setA] = useState('');
  const [b, setB] = useState('');
  const [selected, setSelected] = useState<api.Metric[]>(metrics);
  const [name, setName] = useState('');
  const [file, setFile] = useState<File>();
  const [datasetName, setDatasetName] = useState('');
  const [datasetIdentity, setDatasetIdentity] = useState('');
  const [preview, setPreview] = useState<api.Preview>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const alive = useRef(true);
  const previewRequest = useRef(0);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    let disposed = false;
    setLoading(true); setError('');
    void Promise.all([allPages(o => api.datasets(projectId, o)), allPages(o => api.history(projectId, o)), api.options(projectId), allPages(o => list(projectId, o)).then(ps => Promise.all(ps.map(p => allPages(o => versions(projectId, p.id, o))))).then(vs => vs.flat())]).then(([ds, hs, opts, vs]) => {
      if (!disposed) { setDatasets(ds); setHistory(hs); setOptions(opts); setPipelines(vs); }
    }).catch(e => { if (!disposed) setError((e as Error).message); }).finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [projectId, revision]);
  async function action(work: () => Promise<void>) {
    setBusy(true); setError(''); setMessage('');
    try { await work(); } catch (e) { if (alive.current) setError((e as Error).message); }
    finally { if (alive.current) setBusy(false); }
  }
  if (experimentId) return <Comparison projectId={projectId} experimentId={experimentId}/>;
  return <section className="experiments"><header className="experiment-heading"><div><h1>Experiments</h1><p>Compare saved pipelines against the same reviewed questions.</p></div></header>
    {error && <div role="alert">{error} <Button variant="outline" onClick={() => setRevision(v => v + 1)}>Retry loading</Button></div>}
    {message && <p role="status">{message}</p>}
    {loading ? <p role="status">Loading datasets and saved versions…</p> : <>
      <details className="experiment-section" open={!datasets.length}><summary>Import evaluation dataset</summary><p>UTF-8 CSV: question required, reference_answer optional. Up to {options?.max_rows} questions and {number((options?.max_bytes || 0) / 1024 / 1024)} MiB. Review all questions before import.</p><a href={`/api/projects/${projectId}/datasets/example.csv`} download>Download example CSV</a>
        <div className="experiment-fields"><label>Dataset name<input maxLength={120} value={datasetName} onChange={e => setDatasetName(e.target.value)}/></label><label>Version destination<select value={datasetIdentity} onChange={e => setDatasetIdentity(e.target.value)}><option value="">Create a new dataset</option>{datasets.filter((d,i,ds) => ds.findIndex(x => x.dataset_id === d.dataset_id) === i).map(d => <option key={d.dataset_id} value={d.dataset_id}>New version of {d.name}</option>)}</select></label><label>CSV file<input type="file" accept=".csv,text/csv" disabled={busy} onChange={e => { previewRequest.current++; setFile(e.target.files?.[0]); setPreview(undefined); }}/></label></div>
        <Button variant="outline" disabled={!file || busy} onClick={() => void action(async () => { const seq = ++previewRequest.current; const result = await api.preview(projectId, file!); if (alive.current && seq === previewRequest.current) setPreview(result); })}>Preview CSV</Button>
        {preview && <><h3>Preview · {preview.rows.length} questions</h3>{preview.errors.length > 0 && <ul role="alert">{preview.errors.map((e,i) => <li key={i}>Row {e.row}: {e.message}</li>)}</ul>}<Questions rows={preview.rows}/><Button disabled={busy || preview.errors.length > 0 || !datasetName.trim()} onClick={() => void action(async () => { const result = await api.importDataset(projectId, file!, datasetName, preview.content_hash, datasetIdentity); if (alive.current) { setDataset(result.id); setPreview(undefined); setMessage(`Imported ${result.name} version ${result.version}.`); setRevision(v => v + 1); } })}>Import reviewed dataset</Button></>}
      </details>
      <section className="experiment-section"><h2>Run an experiment</h2>{options?.error && <p role="alert">{options.error}</p>}{!pipelines.length && <p>Save a pipeline in <a href={`#/projects/${projectId}/pipelines`}>Pipelines</a> before running an experiment.</p>}
        <form onSubmit={e => { e.preventDefault(); void action(async () => { const run = await api.start(projectId, name, dataset, [a, b].filter(Boolean), selected); if (alive.current) window.location.hash = `/projects/${projectId}/experiments/${run.id}`; }); }}>
          <div className="experiment-fields"><label>Experiment name<input required maxLength={120} value={name} onChange={e => setName(e.target.value)}/></label><label>Dataset version<select required value={dataset} onChange={e => setDataset(e.target.value)}><option value="">Select reviewed questions</option>{datasets.map(d => <option key={d.id} value={d.id}>{d.name} · v{d.version} · {d.rows.length} questions</option>)}</select></label></div>
          {dataset && <details><summary>Inspect dataset questions</summary><Questions rows={datasets.find(d => d.id === dataset)?.rows || []}/></details>}
          <div className="experiment-fields">{(['A', 'B'] as const).map((label,i) => <div key={label}><label>Candidate {label}{i === 1 ? ' (optional)' : ''}<select required={i === 0} value={i ? b : a} onChange={e => (i ? setB : setA)(e.target.value)}><option value="">{i ? 'Single candidate' : 'Select a saved pipeline version'}</option>{pipelines.filter(v => v.id !== (i ? a : b)).map(v => <option key={v.id} value={v.id}>{v.name} · v{v.version}</option>)}</select></label>{pipelines.find(v => v.id === (i ? b : a)) && <Configuration version={pipelines.find(v => v.id === (i ? b : a))!}/>}</div>)}</div>
          <fieldset><legend>Evaluation metrics</legend>{metrics.map(m => <label className="metric-choice" key={m}><input type="checkbox" checked={selected.includes(m)} onChange={e => setSelected(v => e.target.checked ? [...v, m] : v.filter(x => x !== m))}/><span><strong>{api.metricLabel[m]}</strong><small>{options?.metrics[m]}</small></span></label>)}</fieldset>
          <p>Evaluator: <strong>{options?.model || 'Not configured'}</strong>. LLM-based scores are estimates requiring human review. Evaluation uses paid model calls and is separate from query generation.</p>
          <Button disabled={busy || !!options?.error || !dataset || !a || !selected.length || !name.trim()}>{busy ? 'Submitting…' : 'Run experiment'}</Button>
        </form>
      </section>
      <section className="experiment-section"><h2>Experiment history</h2>{!history.length ? <p>No experiments yet. Import a dataset and select saved pipeline versions to begin.</p> : <div className="experiment-table"><table><thead><tr><th>Name</th><th>Dataset</th><th>Status</th><th>Completed questions × candidates</th></tr></thead><tbody>{history.map(h => <tr key={h.id}><td><a href={`#/projects/${projectId}/experiments/${h.id}`}>{h.name}</a><small>{new Date(h.created_at).toLocaleString()}</small></td><td>{h.snapshot.dataset.name} · v{h.snapshot.dataset.version}</td><td>{h.status}</td><td>{h.progress} / {h.total}</td></tr>)}</tbody></table></div>}</section>
    </>}
  </section>;
}
function Comparison({ projectId, experimentId }: { projectId: string; experimentId: string }) {
  const [run, setRun] = useState<api.Detail>();
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [question, setQuestion] = useState<number>();
  const [cancelling, setCancelling] = useState(false);
  useEffect(() => { if (question !== undefined) document.getElementById("experiment-evidence")?.focus(); }, [question]);
  useEffect(() => {
    let disposed = false; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => { try { const next = await api.detail(projectId, experimentId); if (!disposed) { setRun(next); setError(''); if (['queued','running'].includes(next.status)) timer = setTimeout(() => void poll(), 2000); } } catch (e) { if (!disposed) setError((e as Error).message); } };
    void poll(); return () => { disposed = true; clearTimeout(timer); };
  }, [projectId, experimentId, revision]);
  const selected = run?.snapshot.evaluator.metrics || [];
  return <section className="experiments"><a href={`#/projects/${projectId}/experiments`}>All experiments</a>{error && <p role="alert">{error} <Button variant="outline" onClick={() => setRevision(v => v + 1)}>Retry</Button></p>}{!run ? <p role="status">Loading experiment…</p> : <>
    <header className="experiment-heading"><div><h1>{run.name}</h1><p role="status">{run.status} · {run.progress} / {run.total} question/candidate results completed{run.cancel_requested ? ' · Cancellation requested' : ''}</p></div><a href={`/api/projects/${projectId}/experiments/${run.id}/export.csv`} download>Export CSV</a></header>
    {['queued','running'].includes(run.status) && <><progress max={run.total} value={run.progress} aria-label="Experiment progress"/><Button variant="outline" disabled={cancelling || run.cancel_requested} onClick={() => { setCancelling(true); void api.cancel(projectId, run.id).then(() => setRevision(v => v + 1)).catch(e => setError((e as Error).message)).finally(() => setCancelling(false)); }}>Cancel experiment</Button><p>Cancellation stops further calls. An in-flight call may finish and be billed; its result will be retained.</p></>}
    {run.error && <p role="alert">{run.error}</p>}
    <p>Dataset: {run.snapshot.dataset.name} · v{run.snapshot.dataset.version}. Evaluator: {run.snapshot.evaluator.model} · RAGAS {run.snapshot.evaluator.ragas_version}. LLM-based scores are estimates requiring human review.</p>
    <div className="candidate-columns">{run.snapshot.candidates.map((v,i) => <section key={v.id}><h2>Candidate {i ? 'B' : 'A'}</h2><Configuration version={v}/></section>)}</div>
    {run.snapshot.candidates.length === 2 && run.snapshot.candidates[0].index_id !== run.snapshot.candidates[1].index_id && <p className="index-difference">Different index/source versions: these candidates do not use the same indexed source snapshot. Inspect evidence before attributing differences to pipeline settings.</p>}
    <section className="experiment-section"><h2>Candidate summaries</h2><p>Means include successful scores only; counts below expose excluded and pending items. Faithfulness measures support in supplied context, not overall accuracy.</p><div className="experiment-table" tabIndex={0} aria-label="Candidate summaries"><table><thead><tr><th>Measurement</th>{run.summary.candidates.map(s => <th key={s.candidate}>Candidate {s.candidate ? 'B' : 'A'}</th>)}</tr></thead><tbody>
      {selected.map(m => <tr key={m}><th>{api.metricLabel[m]}</th>{run.summary.candidates.map(s => { const v = s.metrics[m]; return <td key={s.candidate}><strong>{number(v.mean)}</strong> · n={v.scored}/{s.total}<small>{v.failed} failed · {v.skipped} skipped · {v.unavailable} unavailable ({v.missing_reference} missing reference) · {v.pending} pending</small></td>; })}</tr>)}
      <tr><th>Query latency</th>{run.summary.candidates.map(s => <td key={s.candidate}>{number(s.query_latency_ms.mean)} ms · n={s.query_latency_ms.count}</td>)}</tr>
      <tr><th>Query tokens</th>{run.summary.candidates.map(s => <td key={s.candidate}>{number(s.query_tokens.known_sum,0)}<small>Known for {s.query_tokens.known_count}/{s.query_tokens.total} queries</small></td>)}</tr>
      <tr><th>Generation cost (excludes embeddings)</th>{run.summary.candidates.map(s => <td key={s.candidate}>{money(s.generation_cost_usd.known_sum)}<small>Known for {s.generation_cost_usd.known_count}/{s.total} queries</small></td>)}</tr>
      <tr><th>Evaluation cost</th>{run.summary.candidates.map(s => <td key={s.candidate}>{money(s.evaluation_cost_usd.known_sum)}<small>Known for {s.evaluation_cost_usd.known_count}/{s.evaluation_cost_usd.total} metric results. Relevancy embedding charges unavailable.</small></td>)}</tr>
      <tr><th>Generation failures / skipped items</th>{run.summary.candidates.map(s => <td key={s.candidate}>{s.generation_failures} / {s.skipped}</td>)}</tr>
    </tbody></table></div></section>
    {run.snapshot.candidates.length === 2 && <section className="experiment-section"><h2>Paired comparison</h2><p>Only questions successfully scored for both candidates contribute to each difference. No combined winner score.</p><div className="experiment-table"><table><thead><tr><th>Metric</th><th>Shared sample</th><th>A mean</th><th>B mean</th><th>B − A</th></tr></thead><tbody>{selected.map(m => { const p = run.summary.paired[m]!; return <tr key={m}><th>{api.metricLabel[m]}</th><td>{p.count}</td><td>{number(p.a_mean)}</td><td>{number(p.b_mean)}</td><td>{p.b_minus_a != null && p.b_minus_a !== 0 && Math.abs(p.b_minus_a) < 0.001 ? p.b_minus_a.toExponential(2) : number(p.b_minus_a)}</td></tr>; })}</tbody></table></div></section>}
    <section className="experiment-section"><h2>Per-question comparison</h2><div className="experiment-table" tabIndex={0} aria-label="Per-question comparison"><table><thead><tr><th>Question</th>{run.snapshot.candidates.map((c,i) => <th key={c.id}>Candidate {i ? 'B' : 'A'}</th>)}</tr></thead><tbody>{run.snapshot.dataset.rows.map((row,i) => <tr key={i}><th><button className="question-link" onClick={() => setQuestion(i)}>{row.question}</button></th>{run.snapshot.candidates.map((c,ci) => { const item = run.items.find(x => x.ordinal === i && x.candidate === ci)!; return <td key={c.id}>{item.output.status === 'insufficient_evidence' ? 'Insufficient evidence' : readable(item.status)}<small>{selected.map(m => `${api.metricLabel[m]}: ${item.metrics[m]?.status === 'succeeded' ? number(item.metrics[m]?.value) : readable(item.metrics[m]?.reason || item.metrics[m]?.status || 'pending')}`).join(' · ')}</small><small>{number(item.output.snapshot?.total_ms)} ms · {number(item.output.snapshot?.usage?.total_tokens,0)} tokens · generation {money(item.output.snapshot?.cost_usd)}</small></td>; })}</tr>)}</tbody></table></div></section>
    {question !== undefined && <section id="experiment-evidence" tabIndex={-1} className="experiment-section evidence-comparison" aria-label="Question evidence"><div className="experiment-heading"><h2>{run.snapshot.dataset.rows[question].question}</h2><Button variant="outline" onClick={() => setQuestion(undefined)}>Close evidence</Button></div><p>Reference: {run.snapshot.dataset.rows[question].reference_answer || 'Unavailable'}</p><div className="candidate-columns">{run.snapshot.candidates.map((candidate,ci) => { const item = run.items.find(i => i.ordinal === question && i.candidate === ci)!; return <article key={candidate.id}><h3>Candidate {ci ? 'B' : 'A'}</h3><p className="answer-text">{item.output.answer || item.error || 'No answer available.'}</p><p>Query run: {item.query_run_id || 'Not started'}</p>{item.output.snapshot?.evidence?.map(e => <details key={e.label} open><summary>{e.label} · {e.filename} · rank {e.rank}</summary><p className="answer-text">{e.text}</p><small>Source {e.document_id} · page {e.page_number ?? 'n/a'}</small></details>)}{selected.map(m => <details key={m}><summary>{api.metricLabel[m]} · {item.metrics[m]?.status || 'pending'}</summary><p>{readable(item.metrics[m]?.reason || "")}</p><pre>{JSON.stringify(item.metrics[m]?.calls?.map(c => ({ model: c.model, explanation: c.structured_output, usage: c.usage })) || [], null, 2)}</pre></details>)}</article>; })}</div></section>}
    <details className="experiment-section"><summary>Immutable run configuration</summary><pre>{JSON.stringify(run.snapshot, null, 2)}</pre></details>
  </>}</section>;
}
