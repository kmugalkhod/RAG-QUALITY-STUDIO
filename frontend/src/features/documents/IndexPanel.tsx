import { RetrievalSettingsForm } from '../retrieval/RetrievalSettingsForm';
import { defaultRetrieval, retrievalErrors, scoreText, type RetrievalSettings } from '../retrieval/settings';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button } from '../../components/ui/button';
import * as api from './indexApi';

const message = (e: unknown) => e instanceof Error ? e.message : 'Request failed. Please try again.';
const active = (index: api.IndexVersion) => ['queued', 'running'].includes(index.status);

export function IndexPanel({ projectId }: { projectId: string }) {
  const [page, setPage] = useState<api.IndexPage>();
  const [settings, setSettings] = useState<api.EmbeddingSettings>();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [hasActive, setHasActive] = useState(false);
  const [selected, setSelected] = useState<api.IndexVersion>();
  const [query, setQuery] = useState('');
  const [retrieval, setRetrieval] = useState<RetrievalSettings>(defaultRetrieval());
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [result, setResult] = useState<api.Retrieval>();
  const heading = useRef<HTMLHeadingElement>(null);
  const focusPage = useRef(false);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const [indexes, config, latest] = await Promise.all([api.listIndexes(projectId, offset), api.embeddingSettings(projectId), offset ? api.listIndexes(projectId) : Promise.resolve(undefined)]);
        if (!disposed) {
          setPage(indexes); setSettings(config); setLoadError('');
          setHasActive((latest || indexes).items.some(active));
          if (focusPage.current) { heading.current?.focus(); focusPage.current = false; }
        }
      } catch (e) { if (!disposed) setLoadError(message(e)); }
      if (!disposed) timer = setTimeout(() => void load(), 2000);
    }
    void load();
    return () => { disposed = true; clearTimeout(timer); };
  }, [projectId, offset, revision]);
  useEffect(() => {
    let disposed = false;
    let request = 0;
    const restore = () => {
      const seq = ++request;
      const id = new URLSearchParams(window.location.hash.split('?')[1]).get('index');
      setSelected(undefined); setResult(undefined); setSearchError('');
      if (id) void api.getIndex(projectId, id).then(index => {
        if (disposed || seq !== request) return;
        if (index.status === 'succeeded') setSelected(index);
        else setSearchError('These documents are still being prepared. Choose a version marked Ready for questions.');
      }).catch(e => { if (!disposed && seq === request) setSearchError(message(e)); });
    };
    restore();
    window.addEventListener('hashchange', restore);
    return () => { disposed = true; window.removeEventListener('hashchange', restore); };
  }, [projectId]);
  function selectIndex(index: api.IndexVersion) {
    setSelected(index); setResult(undefined); setSearchError('');
    const [path, search] = window.location.hash.split('?');
    const params = new URLSearchParams(search);
    params.set('view', 'indexes'); params.set('index', index.id);
    window.location.hash = `${path || `#/projects/${projectId}/knowledge-base`}?${params}`;
  }
  async function create() {
    setBusy(true); setError(''); setNotice('');
    try {
      const index = await api.createIndex(projectId);
      setNotice(`Document set version ${index.version} created with ${index.chunk_count} passages. Follow its status below.`);
      setHasActive(true); setOffset(0); setRevision(n => n + 1);
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  async function cancel(index: api.IndexVersion) {
    setBusy(true); setError('');
    try {
      const value = await api.cancelIndex(projectId, index.id);
      setNotice(value.status === 'cancelled' ? `Document set version ${index.version} cancelled. In-flight requests may finish, but cannot publish.` : `Document set version ${index.version} is already ${value.status}.`);
      setRevision(n => n + 1);
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  async function search(event: FormEvent) {
    event.preventDefault(); setSearchError(''); setResult(undefined);
    if (!selected || !query.trim() || query.trim().length > 8000 || retrievalErrors(retrieval).length > 0) {
      setSearchError('Choose a prepared document set, enter a query of 1–8,000 characters, and set results to an integer from 1 to 50.'); return;
    }
    setSearching(true);
    try { setResult(await api.retrieve(projectId, selected.id, query.trim(), retrieval)); }
    catch (e) { setSearchError(message(e)); }
    finally { setSearching(false); }
  }
  return <section className="inspector" aria-labelledby="index-title">
    <div className="section-heading"><h2 id="index-title">Prepare documents for questions</h2><Button onClick={() => void create()} disabled={busy || hasActive || !settings?.configured}>Prepare document set</Button></div>
    <p className="field-hint">A document set is a saved copy of your processed documents, prepared for questions. Create a new version after documents change; earlier versions stay available.</p>
    {settings?.config && <details className="source-metadata"><summary>Search model details</summary><p>{settings.config.provider} · {settings.config.model} · {settings.config.dimensions} dimensions</p></details>}
    {settings && !settings.configured && <p className="error-message">{settings.error}</p>}
    {loadError && <p role="alert" className="error-message">{loadError}</p>}
    {error && <p role="alert" className="error-message">{error}</p>}
    <p role="status" className="success-message">{notice}</p>
    <div className="section-heading"><h3 ref={heading} tabIndex={-1}>Document sets</h3><Button variant="outline" onClick={() => setRevision(n => n + 1)}>Refresh document sets</Button></div>
    {!page && !loadError && <p role="status">Loading document sets…</p>}
    {page?.total === 0 && <p>No document sets yet. Process a document first, then choose Prepare document set.</p>}
    <ul className="run-list">{page?.items.map(index => <li key={index.id}><div className="document-summary">
      <h3>Document set · Version {index.version} <span className={`run-status status-${index.status}`}>{index.status === 'succeeded' ? 'Ready for questions' : active(index) ? 'Preparing · ' + index.status : index.status}</span></h3>
      <p>{index.embedded_count} / {index.chunk_count} passages prepared</p>
      {active(index) && <progress aria-label={`Document set version ${index.version} progress`} value={index.embedded_count} max={index.chunk_count}/>}
      {index.error && <p className="error-message">{index.error}</p>}
      <details className="source-metadata"><summary>Technical details</summary><p>{index.id}</p><p>Created {new Date(index.created_at).toLocaleString()}</p><p>Model: {index.embedding_config.model} · {index.embedding_config.dimensions} dimensions</p><p>Provider: {index.embedding_config.provider} · Revision: {index.embedding_config.revision}</p></details>
    </div>{active(index) ? <Button variant="outline" disabled={busy} onClick={() => void cancel(index)}>Cancel document set {index.version}</Button> : index.status === 'succeeded' && <Button variant="outline" disabled={searching} aria-pressed={selected?.id === index.id} onClick={() => selectIndex(index)}>Use document set {index.version}</Button>}</li>)}</ul>
    {page && (page.total > 20 || offset > 0) && <nav className="pagination" aria-label="Document set pages"><Button variant="outline" disabled={!offset} onClick={() => { focusPage.current = true; setOffset(n => Math.max(0, n - 20)); }}>Previous document sets</Button><span>Page {offset / 20 + 1}</span><Button variant="outline" disabled={offset + 20 >= page.total} onClick={() => { focusPage.current = true; setOffset(n => n + 20); }}>Next document sets</Button></nav>}
    <details className="chunk-inspector" open={!!selected}><summary>Search documents only</summary>
      <p>{selected ? `Searching document set · Version ${selected.version}` : 'Choose “Use document set” above.'}</p>
      <form onSubmit={search} noValidate aria-busy={searching}>
        <label htmlFor="retrieval-query">Search query</label><textarea id="retrieval-query" rows={3} maxLength={8000} value={query} onChange={e => { setQuery(e.target.value); setResult(undefined); }} disabled={searching}/>
        <RetrievalSettingsForm value={retrieval} disabled={searching} onChange={value => { setRetrieval(value); setResult(undefined); }}/>
        <Button type="submit" disabled={searching || !selected || !!retrievalErrors(retrieval).length}>{searching ? 'Searching…' : 'Search documents only'}</Button>
        <p className="field-hint">Returns document passages only. It does not generate an answer.</p>
      </form>
      {searchError && <p role="alert" className="error-message">{searchError}</p>}
      {result && <section aria-label="Retrieval results"><p role="status">{result.items.length} passages from document set version {result.index_version}</p>
        {result.items.length === 0 && <p>No matching passages in this document set.</p>}
        <ol className="chunk-list">{result.items.map(item => <li key={`${item.run_id}-${item.ordinal}`}><h3>{item.rank}. {item.filename}</h3><p className="chunk-provenance">{scoreText(item)} · Processing version {item.processing_version} · Chunk {item.ordinal + 1} · {item.page_number ? `PDF page ${item.page_number} · ` : ''}Characters {item.start_char}–{item.end_char}</p><pre>{item.text}</pre><details className="source-metadata"><summary>Source identity</summary><p>Document: {item.document_id}</p><p>Processing run: {item.run_id}</p><p>SHA-256: {item.content_hash}</p></details></li>)}</ol>
      </section>}
    </details>
  </section>;
}
