import { IndexPanel } from "./IndexPanel";
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowLeft, FileText, Upload } from 'lucide-react';
import { Button } from '../../components/ui/button';
import * as api from './api';

const message = (error: unknown) => error instanceof Error ? error.message : 'Request failed. Please try again.';
const active = (run: api.Run | null) => run?.status === 'queued' || run?.status === 'running';
const date = (value: string) => new Date(value).toLocaleString();
const bytes = (value: number) => `${new Intl.NumberFormat().format(value)} bytes`;

function Pagination({ offset, total, onChange, label, busy = false }: { offset: number; total: number; onChange: (n: number) => void; label: string; busy?: boolean }) {
  return total > 20 || offset > 0 ? <nav className="pagination" aria-label={label}><Button variant="outline" disabled={busy || !offset} onClick={() => onChange(Math.max(0, offset - 20))}>Previous</Button><span>Page {offset / 20 + 1}</span><Button variant="outline" disabled={busy || offset + 20 >= total} onClick={() => onChange(offset + 20)}>Next</Button></nav> : null;
}

export function KnowledgeBase({ projectId }: { projectId: string }) {
  const [projectName, setProjectName] = useState('');
  const [limit, setLimit] = useState<number>();
  const [page, setPage] = useState<api.Page<api.Document>>();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [settingsError, setSettingsError] = useState('');
  const [loading, setLoading] = useState(true);
  const listTitle = useRef<HTMLHeadingElement>(null);
  const focusPage = useRef(false);
  const [uploadError, setUploadError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState('');
  const [selected, setSelected] = useState<api.Document>();
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    let disposed = false;
    void Promise.all([api.getProject(projectId), api.getSettings(projectId)]).then(([project, settings]) => {
      if (!disposed) { setProjectName(project.name); setLimit(settings.max_upload_bytes); setSettingsError(''); }
    }).catch(err => { if (!disposed) setSettingsError(message(err)); });
    return () => { disposed = true; };
  }, [projectId, revision]);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const result = await api.listDocuments(projectId, offset);
        if (!disposed) { setPage(result); setError(''); setLoading(false); if (focusPage.current) { listTitle.current?.focus(); focusPage.current = false; } }
      } catch (err) { if (!disposed) { setError(message(err)); setLoading(false); } }
      if (!disposed) timer = setTimeout(() => void load(), 2000);
    }
    setLoading(true);
    void load();
    return () => { disposed = true; clearTimeout(timer); };
  }, [projectId, offset, revision]);
  async function upload(event: FormEvent) {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    setUploadError(''); setNotice('');
    if (!file) { setUploadError('Choose a PDF or UTF-8 TXT file.'); return; }
    if (!/\.(pdf|txt)$/i.test(file.name) || !file.size || (limit && file.size > limit)) {
      setUploadError('Choose a nonempty PDF or UTF-8 TXT within the upload limit.'); return;
    }
    setUploading(true);
    try {
      const result = await api.uploadDocument(projectId, file);
      setNotice(`“${result.filename}” uploaded. Select chunk settings and start processing.`);
      if (fileInput.current) fileInput.current.value = '';
      setSelected(result); setOffset(0); setRevision(n => n + 1);
    } catch (err) { setUploadError(`${message(err)} Refresh the list before retrying an interrupted upload; repeated uploads create separate documents.`); }
    finally { setUploading(false); }
  }
  return <>
    <a className="back-link" href="#"><ArrowLeft size={16}/>All projects</a>
    <div className="page-heading"><div><h1>Knowledge Base</h1><a className="back-link" href={`#/projects/${projectId}/playground`}>Open RAG playground</a><a className="back-link" href={`#/projects/${projectId}/pipelines`}>Open pipeline editor</a><p>{projectName || 'Loading project…'}</p></div></div>
    <p className="page-intro">Upload source documents, process their text and inspect each chunk. Index processed documents to search their source chunks.</p>
    <section className="create-panel" aria-labelledby="upload-title"><h2 id="upload-title">Add a document</h2>
      <form className="upload-form" onSubmit={upload} aria-busy={uploading}>
        <div><label htmlFor="document-file">PDF or UTF-8 TXT</label><input ref={fileInput} id="document-file" type="file" accept=".pdf,.txt" disabled={uploading || !limit} aria-describedby="upload-hint"/><p className="field-hint" id="upload-hint">One file per upload. {limit ? `Maximum ${bytes(limit)}.` : 'Loading upload limit…'} Scanned PDFs require OCR and are unsupported.</p></div>
        <Button disabled={uploading || !limit} type="submit"><Upload size={16}/>{uploading ? 'Uploading…' : 'Upload document'}</Button>
      </form>
      {settingsError && <div><p role="alert" className="error-message">{settingsError}</p><Button variant="outline" onClick={() => setRevision(n => n + 1)}>Retry upload settings</Button></div>}
      {uploadError && <p role="alert" className="error-message">{uploadError}</p>}
      <p role="status" className="success-message">{notice}</p>
    </section>
    <section className="project-section" aria-labelledby="documents-title"><div className="section-heading"><h2 ref={listTitle} tabIndex={-1} id="documents-title">Documents {page && <span className="count">{page.total}</span>}</h2><Button variant="outline" onClick={() => setRevision(n => n + 1)}>Refresh</Button></div>
      {error && <p role="alert" className="error-message">{error}</p>}
      {loading && page && <p role="status">Loading documents…</p>}
      {!page && !error ? <p role="status" className="loading-state">Loading documents…</p> : page?.items.length === 0 ? <div className="empty-state"><FileText size={32}/><h3>No documents yet</h3><p>Upload a source file to begin inspecting its text.</p></div> : <ul className="document-list">{page?.items.map(doc => <li key={doc.id} className={selected?.id === doc.id ? 'document-selected' : ''}>
        <div className="document-summary"><h3><button className="document-name" onClick={() => setSelected(doc)}>{doc.filename}</button></h3><p>{bytes(doc.size_bytes)} · Uploaded {date(doc.created_at)}</p><span className={`run-status status-${doc.latest_run?.status || 'uploaded'}`}>{doc.latest_run ? doc.latest_run.status === 'succeeded' ? 'Processed' : doc.latest_run.status : 'Uploaded'}</span>{active(doc.latest_run) && <span> · {doc.latest_run?.progress}% · attempt {doc.latest_run?.attempts}/3</span>}{doc.latest_run?.error && <p className="error-message">{doc.latest_run.error}</p>}</div>
        <Button variant="outline" onClick={() => setSelected(doc)} aria-label={`Manage ${doc.filename}`}>{selected?.id === doc.id ? 'Selected' : 'Process / inspect'}</Button>
      </li>)}</ul>}
      {page && <Pagination offset={offset} total={page.total} onChange={value => { focusPage.current = true; setOffset(value); }} busy={loading} label="Document pages"/>}
    </section>
    {selected && <DocumentInspector key={selected.id} projectId={projectId} document={selected} onChange={() => setRevision(n => n + 1)}/>}
    <IndexPanel key={projectId} projectId={projectId}/>
  </>;
}

function DocumentInspector({ projectId, document, onChange }: { projectId: string; document: api.Document; onChange: () => void }) {
  const [size, setSize] = useState('1000');
  const [overlap, setOverlap] = useState('200');
  const [runs, setRuns] = useState<api.Page<api.Run>>();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [selectedRun, setSelectedRun] = useState<api.Run>();
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const historyTitle = useRef<HTMLHeadingElement>(null);
  const focusPage = useRef(false);
  const [notice, setNotice] = useState('');
  const [activeRun, setActiveRun] = useState(false);
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => { title.current?.focus(); }, []);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const result = await api.listRuns(projectId, document.id, offset);
        const latest = offset === 0 ? result : await api.listRuns(projectId, document.id);
        if (!disposed) { setRuns(result); setActiveRun(latest.items.some(active)); setLoadError(''); setLoading(false); if (focusPage.current) { historyTitle.current?.focus(); focusPage.current = false; } }
      } catch (err) { if (!disposed) { setLoadError(message(err)); setLoading(false); } }
      if (!disposed) timer = setTimeout(() => void load(), 2000);
    }
    setLoading(true); void load();
    return () => { disposed = true; clearTimeout(timer); };
  }, [projectId, document.id, offset, revision]);
  async function start(event: FormEvent) {
    event.preventDefault(); setNotice(''); setError('');
    const chunkSize = Number(size), chunkOverlap = Number(overlap);
    if (!size || !overlap || !Number.isInteger(chunkSize) || !Number.isInteger(chunkOverlap) || chunkSize <= 0 || chunkSize > 100000 || chunkOverlap < 0 || chunkOverlap >= chunkSize) {
      setError('Chunk size must be 1–100,000 characters. Overlap must be zero or more and smaller than chunk size.'); return;
    }
    setBusy(true);
    try {
      const result = await api.startRun(projectId, document.id, chunkSize, chunkOverlap);
      setNotice(`Version ${result.version} queued. Processing will start when a worker is available.`);
      setActiveRun(true); setOffset(0); setRevision(n => n + 1); onChange();
    } catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  }
  async function cancel(run: api.Run) {
    setBusy(true); setError('');
    try { const result = await api.cancelRun(projectId, document.id, run.id); setNotice(result.status === 'cancelled' ? 'Run cancelled. In-flight parsing stops at its next checkpoint; no chunks will be published.' : `Run is already ${result.status}.`); setRevision(n => n + 1); onChange(); }
    catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  }
  return <section className="inspector" aria-labelledby="inspector-title">
    <h2 ref={title} tabIndex={-1} id="inspector-title">Process: {document.filename}</h2>
    <details className="source-metadata"><summary>Source metadata</summary><p>Document ID: {document.id}</p><p>SHA-256: {document.content_hash}</p></details>
    <form onSubmit={start} noValidate><div className="chunk-settings"><div><label htmlFor="chunk-size">Chunk size (characters)</label><input id="chunk-size" type="number" min="1" max="100000" value={size} onChange={e => setSize(e.target.value)} disabled={busy}/></div><div><label htmlFor="chunk-overlap">Overlap (characters)</label><input id="chunk-overlap" type="number" min="0" value={overlap} onChange={e => setOverlap(e.target.value)} disabled={busy}/></div><Button disabled={busy || activeRun || !runs} type="submit">{busy ? 'Saving…' : 'Start processing'}</Button></div>
      <p className="field-hint">Each start saves a new version. Fixed character windows preserve whitespace and never cross PDF pages. A failed or cancelled run can be retried by starting a new version.</p>
    </form>
    {loadError && <p role="alert" className="error-message">{loadError}</p>}
    {error && <p role="alert" className="error-message">{error}</p>}
    <p role="status" className="success-message">{notice}</p>
    <div className="section-heading"><h3 ref={historyTitle} tabIndex={-1}>Processing history</h3><Button variant="outline" size="sm" onClick={() => setRevision(n => n + 1)}>Refresh history</Button></div>
    {loading && runs && <p role="status">Loading processing history…</p>}
    {!runs ? <p role="status">Loading processing history…</p> : !runs.total ? <p>No processing runs yet. Choose your settings above.</p> : <ul className="run-list">{runs.items.map(run => <li key={run.id}><div><h3>Version {run.version} <span className={`run-status status-${run.status}`}>{run.status}</span></h3><p>{run.chunk_size} characters · {run.overlap} overlap · {date(run.created_at)}</p><p className="field-hint">{run.parser_version} · {run.config_version}</p>{active(run) && <p role="status">{run.status === 'queued' ? 'Waiting for a worker' : 'Processing text'} · {run.progress}% · attempt {run.attempts}/3</p>}{run.error && <p className="error-message">{run.error}</p>}</div><div>{active(run) && <Button variant="outline" disabled={busy} onClick={() => void cancel(run)}>Cancel run</Button>}{run.status === 'succeeded' && <Button variant="outline" onClick={() => setSelectedRun(run)}>Inspect {run.chunk_count} chunks</Button>}</div></li>)}</ul>}
    {runs && <Pagination offset={offset} total={runs.total} onChange={value => { focusPage.current = true; setOffset(value); }} busy={loading} label="Processing history pages"/>}
    {selectedRun && <ChunkInspector key={selectedRun.id} projectId={projectId} documentId={document.id} run={selectedRun}/>}
  </section>;
}

function ChunkInspector({ projectId, documentId, run }: { projectId: string; documentId: string; run: api.Run }) {
  const [page, setPage] = useState<api.Page<api.Chunk>>();
  const [loading, setLoading] = useState(true);
  const focusPage = useRef(false);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => { title.current?.focus(); }, []);
  useEffect(() => {
    let disposed = false;
    setLoading(true); setError('');
    void api.listChunks(projectId, documentId, run.id, offset).then(result => { if (!disposed) { setPage(result); setLoading(false); if (focusPage.current) { title.current?.focus(); focusPage.current = false; } } }).catch(err => { if (!disposed) { setError(message(err)); setLoading(false); } });
    return () => { disposed = true; };
  }, [projectId, documentId, run.id, offset, revision]);
  return <section className="chunk-inspector" aria-labelledby="chunks-title"><h3 id="chunks-title" tabIndex={-1} ref={title}>Chunks · Version {run.version}</h3><p>{run.chunk_size} characters · {run.overlap} overlap · {run.chunk_count} chunks</p>
    {loading && page && <p role="status">Loading chunks…</p>}
    {error ? <div><p role="alert" className="error-message">{error}</p><Button variant="outline" onClick={() => setRevision(n => n + 1)}>Retry loading chunks</Button></div> : !page ? <p role="status">Loading chunks…</p> : <ol className="chunk-list" start={offset + 1}>{page.items.map(chunk => <li key={chunk.ordinal}><p className="chunk-provenance">Chunk {chunk.ordinal + 1} · {chunk.page_number ? `PDF page ${chunk.page_number}` : 'TXT source'} · characters {chunk.start_char}–{chunk.end_char} (end exclusive)</p><pre>{chunk.text}</pre></li>)}</ol>}
    {page && <Pagination offset={offset} total={page.total} onChange={value => { focusPage.current = true; setOffset(value); }} busy={loading} label="Chunk pages"/>}
  </section>;
}
