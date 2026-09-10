import { IndexPanel } from "./IndexPanel";
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { FileText, Upload, Plus, X, PanelRight, Files, Database, RotateCw } from 'lucide-react';
import { Button } from '../../components/ui/button';
import * as api from './api';
import { allPages } from '../pipelines/api';

const message = (error: unknown) => error instanceof Error ? error.message : 'Request failed. Please try again.';
const active = (run: api.Run | null) => run?.status === 'queued' || run?.status === 'running';
const date = (value: string) => new Date(value).toLocaleString();
const bytes = (value: number) => `${new Intl.NumberFormat().format(value)} bytes`;

function Pagination({ offset, total, onChange, label, busy = false }: { offset: number; total: number; onChange: (n: number) => void; label: string; busy?: boolean }) {
  return total > 20 || offset > 0 ? <nav className="pagination" aria-label={label}><Button variant="outline" disabled={busy || !offset} onClick={() => onChange(Math.max(0, offset - 20))}>Previous</Button><span>Page {offset / 20 + 1}</span><Button variant="outline" disabled={busy || offset + 20 >= total} onClick={() => onChange(offset + 20)}>Next</Button></nav> : null;
}

export function KnowledgeBase({ projectId, documentId = '' }: { projectId: string; documentId?: string }) {
  const [tab, setTabState] = useState<'documents' | 'indexes'>(() => new URLSearchParams(window.location.hash.split('?')[1]).get('view') === 'indexes' ? 'indexes' : 'documents');
  function setTab(value: 'documents' | 'indexes') {
    setTabState(value);
    const [path, search] = window.location.hash.split('?');
    const query = new URLSearchParams(search);
    if (value === 'indexes') query.set('view', value); else query.delete('view');
    window.location.hash = `${path || `/projects/${projectId}/knowledge-base`}${query.size ? `?${query}` : ''}`;
  }
  useEffect(() => {
    const update = () => setTabState(new URLSearchParams(window.location.hash.split('?')[1]).get('view') === 'indexes' ? 'indexes' : 'documents');
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  const [showUpload, setShowUpload] = useState(false);
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
  useEffect(() => { if (showUpload) fileInput.current?.focus(); }, [showUpload]);
  function selectDocument(document?: api.Document) {
    setSelected(document);
    window.location.hash = `/projects/${projectId}/knowledge-base${document ? `?document=${document.id}` : ''}`;
  }
  useEffect(() => {
    let disposed = false;
    if (!documentId) { setSelected(undefined); return; }
    void allPages(o => api.listDocuments(projectId, o)).then(documents => {
      if (!disposed) { const found = documents.find(d => d.id === documentId); setSelected(found); if (!found) setError('This document is unavailable in this project.'); }
    }).catch(e => { if (!disposed) setError(message(e)); });
    return () => { disposed = true; };
  }, [projectId, documentId]);
  useEffect(() => {
    let disposed = false;
    void Promise.all([api.getProject(projectId), api.getSettings(projectId)]).then(([, settings]) => {
      if (!disposed) { setLimit(settings.max_upload_bytes); setSettingsError(''); }
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
      setShowUpload(false); selectDocument(result); setOffset(0); setRevision(n => n + 1);
    } catch (err) { setUploadError(`${message(err)} Refresh the list before retrying an interrupted upload; repeated uploads create separate documents.`); }
    finally { setUploading(false); }
  }
  return <div className="knowledge-page">
    <div className="knowledge-heading"><div><h1>Knowledge Base</h1><p>Source documents and searchable indexes.</p></div><Button variant={selected || showUpload ? 'outline' : 'default'} onClick={() => { setTab('documents'); setShowUpload(v => !v); }} aria-expanded={showUpload} aria-controls="upload-panel"><Plus size={15}/>Add document</Button></div>
    <nav className="knowledge-tabs" aria-label="Knowledge Base views"><button aria-current={tab === 'documents' ? 'page' : undefined} onClick={() => setTab('documents')}><Files size={15}/>Documents {page && <span>{page.total}</span>}</button><button aria-current={tab === 'indexes' ? 'page' : undefined} onClick={() => setTab('indexes')}><Database size={15}/>Indexes</button></nav>
    {showUpload && <section id="upload-panel" className="create-panel upload-panel" aria-labelledby="upload-title"><h2 id="upload-title">Add a document</h2>
      <form className="upload-form" onSubmit={upload} aria-busy={uploading}>
        <div><label htmlFor="document-file">PDF or UTF-8 TXT</label><input ref={fileInput} id="document-file" type="file" accept=".pdf,.txt" disabled={uploading || !limit} aria-describedby="upload-hint"/><p className="field-hint" id="upload-hint">One file per upload. {limit ? `Maximum ${bytes(limit)}.` : 'Loading upload limit…'} Scanned PDFs require OCR and are unsupported.</p></div>
        <Button disabled={uploading || !limit} type="submit"><Upload size={16}/>{uploading ? 'Uploading…' : 'Upload document'}</Button>
      </form>
      {settingsError && <div><p role="alert" className="error-message">{settingsError}</p><Button variant="outline" onClick={() => setRevision(n => n + 1)}>Retry upload settings</Button></div>}
      {uploadError && <p role="alert" className="error-message">{uploadError}</p>}
      <p role="status" className="success-message">{notice}</p>
    </section>}
    {!showUpload && settingsError && <p role="alert" className="error-message">{settingsError}</p>}
    <div className={`knowledge-split ${selected && tab === 'documents' ? 'has-inspector' : ''}`}><div className="knowledge-body">
    {tab === 'documents' && <section className="project-section" aria-labelledby="documents-title"><div className="section-heading"><h2 ref={listTitle} tabIndex={-1} id="documents-title">All documents</h2><Button variant="outline" onClick={() => setRevision(n => n + 1)}><RotateCw size={13}/>Refresh</Button></div>
      {error && <p role="alert" className="error-message">{error}</p>}
      {loading && page && <p role="status">Loading documents…</p>}
      {!page && !error ? <p role="status" className="loading-state">Loading documents…</p> : page?.items.length === 0 ? <div className="empty-state"><FileText size={32}/><h3>No documents yet</h3><p>Upload a source file to begin inspecting its text.</p></div> : <div className="source-table-wrap"><table className="source-table"><thead><tr><th scope="col">Name</th><th scope="col">Status</th><th scope="col">Size</th><th scope="col">Added</th><th scope="col"><span className="sr-only">Details</span></th></tr></thead><tbody>{page?.items.map(doc => <tr key={doc.id} className={selected?.id === doc.id ? 'document-selected' : ''}>
        <td><div className="source-name"><FileText size={16}/><button className="document-name" onClick={() => selectDocument(doc)}>{doc.filename}</button></div>{doc.latest_run?.error && <p className="error-message">{doc.latest_run.error}</p>}</td>
        <td><span className={`run-status status-${doc.latest_run?.status || 'uploaded'}`}>{doc.latest_run ? doc.latest_run.status === 'succeeded' ? 'Processed' : active(doc.latest_run) ? 'Processing' : doc.latest_run.status : 'Uploaded'}</span>{active(doc.latest_run) && <small> {doc.latest_run?.progress}%</small>}</td>
        <td>{doc.size_bytes < 1024 ? `${doc.size_bytes} B` : `${(doc.size_bytes / 1024).toFixed(1)} KB`}</td><td><time dateTime={doc.created_at}>{new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(new Date(doc.created_at))}</time></td>
        <td><button className="icon-button" onClick={() => selectDocument(doc)} aria-label={`Manage ${doc.filename}`}><PanelRight size={15}/></button></td>
      </tr>)}</tbody></table><p className="table-note">Processed documents are ready to index. Only ready indexes can answer questions.</p></div>}
      {page && <Pagination offset={offset} total={page.total} onChange={value => { focusPage.current = true; setOffset(value); }} busy={loading} label="Document pages"/>}
    </section>}
    {tab === 'indexes' && <IndexPanel key={projectId} projectId={projectId}/>}
    </div>
    {selected && tab === 'documents' && <aside className="document-detail" aria-label="Document details"><div className="detail-toolbar"><span><FileText size={15}/>Document details</span><button className="icon-button" onClick={() => selectDocument()} aria-label="Close document details"><X size={17}/></button></div><DocumentInspector key={selected.id} projectId={projectId} document={selected} onChange={() => setRevision(n => n + 1)}/></aside>}
    </div>
  </div>;

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
    <form onSubmit={start} noValidate><details className="source-metadata"><summary>Advanced processing options</summary><div className="chunk-settings"><div><label htmlFor="chunk-size">Chunk size (characters)</label><input id="chunk-size" type="number" min="1" max="100000" value={size} onChange={e => setSize(e.target.value)} disabled={busy}/></div><div><label htmlFor="chunk-overlap">Overlap (characters)</label><input id="chunk-overlap" type="number" min="0" value={overlap} onChange={e => setOverlap(e.target.value)} disabled={busy}/></div></div></details><Button disabled={busy || activeRun || !runs} type="submit">{busy ? 'Saving…' : 'Start processing'}</Button>
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
    {error ? <div><p role="alert" className="error-message">{error}</p><Button variant="outline" onClick={() => setRevision(n => n + 1)}>Retry loading chunks</Button></div> : !page ? <p role="status">Loading chunks…</p> : <ol className="chunk-list document-chunks" tabIndex={0} aria-label="Document chunks" start={offset + 1}>{page.items.map(chunk => <li key={chunk.ordinal}><p className="chunk-provenance">Chunk {chunk.ordinal + 1} · {chunk.page_number ? `PDF page ${chunk.page_number}` : 'TXT source'} · characters {chunk.start_char}–{chunk.end_char} (end exclusive)</p><pre>{chunk.text}</pre></li>)}</ol>}
    {page && <Pagination offset={offset} total={page.total} onChange={value => { focusPage.current = true; setOffset(value); }} busy={loading} label="Chunk pages"/>}
  </section>;
}
