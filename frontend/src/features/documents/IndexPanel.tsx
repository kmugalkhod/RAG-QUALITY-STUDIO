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
  const [topK, setTopK] = useState('5');
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
  async function create() {
    setBusy(true); setError(''); setNotice('');
    try {
      const index = await api.createIndex(projectId);
      setNotice(`Index version ${index.version} queued with ${index.chunk_count} chunks.`);
      setHasActive(true); setOffset(0); setRevision(n => n + 1);
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  async function cancel(index: api.IndexVersion) {
    setBusy(true); setError('');
    try {
      const value = await api.cancelIndex(projectId, index.id);
      setNotice(value.status === 'cancelled' ? `Index version ${index.version} cancelled. In-flight requests may finish, but cannot publish.` : `Index version ${index.version} is already ${value.status}.`);
      setRevision(n => n + 1);
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  async function search(event: FormEvent) {
    event.preventDefault(); setSearchError(''); setResult(undefined);
    const count = Number(topK);
    if (!selected || !query.trim() || query.trim().length > 8000 || !Number.isInteger(count) || count < 1 || count > 50) {
      setSearchError('Choose a ready index, enter a query of 1–8,000 characters, and set results to an integer from 1 to 50.'); return;
    }
    setSearching(true);
    try { setResult(await api.retrieve(projectId, selected.id, query.trim(), count)); }
    catch (e) { setSearchError(message(e)); }
    finally { setSearching(false); }
  }
  return <section className="inspector" aria-labelledby="index-title">
    <div className="section-heading"><h2 id="index-title">Index &amp; test retrieval</h2><Button onClick={() => void create()} disabled={busy || hasActive || !settings?.configured}>Index documents</Button></div>
    <p className="field-hint">Index the latest successful processing version of each document. Older ready indexes remain searchable while a new version builds. Starting a new index retries failed or cancelled builds.</p>
    {settings?.config && <p className="index-config">{settings.config.provider} · {settings.config.model} · {settings.config.dimensions} dimensions</p>}
    {settings && !settings.configured && <p className="error-message">{settings.error}</p>}
    {loadError && <p role="alert" className="error-message">{loadError}</p>}
    {error && <p role="alert" className="error-message">{error}</p>}
    <p role="status" className="success-message">{notice}</p>
    <div className="section-heading"><h3 ref={heading} tabIndex={-1}>Index history</h3><Button variant="outline" onClick={() => setRevision(n => n + 1)}>Refresh indexes</Button></div>
    {!page && !loadError && <p role="status">Loading indexes…</p>}
    {page?.total === 0 && <p>No indexes yet. Process a document, then index its chunks to enable retrieval.</p>}
    <ul className="run-list">{page?.items.map(index => <li key={index.id}><div className="document-summary">
      <h3>Index version {index.version} <span className={`run-status status-${index.status}`}>{index.status === 'succeeded' ? 'Indexed · ready' : active(index) ? 'Indexing · ' + index.status : index.status}</span></h3>
      <p>{index.embedded_count} / {index.chunk_count} chunks embedded · {index.embedding_config.model} · {index.embedding_config.dimensions} dimensions</p>
      {active(index) && <progress aria-label={`Index version ${index.version} progress`} value={index.embedded_count} max={index.chunk_count}/>}
      {index.error && <p className="error-message">{index.error}</p>}
      <details className="source-metadata"><summary>Index identity and configuration</summary><p>{index.id}</p><p>Created {new Date(index.created_at).toLocaleString()}</p><p>Provider: {index.embedding_config.provider} · Revision: {index.embedding_config.revision}</p></details>
    </div>{active(index) ? <Button variant="outline" disabled={busy} onClick={() => void cancel(index)}>Cancel index {index.version}</Button> : index.status === 'succeeded' && <Button variant="outline" disabled={searching} onClick={() => { setSelected(index); setResult(undefined); setSearchError(''); }}>Use index {index.version}</Button>}</li>)}</ul>
    {page && (page.total > 20 || offset > 0) && <nav className="pagination" aria-label="Index pages"><Button variant="outline" disabled={!offset} onClick={() => { focusPage.current = true; setOffset(n => Math.max(0, n - 20)); }}>Previous indexes</Button><span>Page {offset / 20 + 1}</span><Button variant="outline" disabled={offset + 20 >= page.total} onClick={() => { focusPage.current = true; setOffset(n => n + 20); }}>Next indexes</Button></nav>}
    <details className="chunk-inspector" open={!!selected}><summary>Test retrieval</summary>
      <p>{selected ? `Selected: index version ${selected.version} · ${selected.id}` : 'Choose “Use index” on a ready version above.'}</p>
      <form onSubmit={search} noValidate aria-busy={searching}>
        <label htmlFor="retrieval-query">Search query</label><textarea id="retrieval-query" rows={3} maxLength={8000} value={query} onChange={e => { setQuery(e.target.value); setResult(undefined); }} disabled={searching}/>
        <div className="chunk-settings retrieval-actions"><div><label htmlFor="retrieval-count">Number of results</label><input id="retrieval-count" type="number" min={1} max={50} value={topK} onChange={e => { setTopK(e.target.value); setResult(undefined); }} disabled={searching}/></div><Button type="submit" disabled={searching || !selected}>{searching ? 'Searching…' : 'Test retrieval'}</Button></div>
        <p className="field-hint">Cosine distance: lower is closer; this is not confidence. Returns source chunks without generating an answer.</p>
      </form>
      {searchError && <p role="alert" className="error-message">{searchError}</p>}
      {result && <section aria-label="Retrieval results"><p role="status">{result.items.length} results from index version {result.index_version} · {result.index_id}</p>
        {result.items.length === 0 && <p>No matching chunks in this index.</p>}
        <ol className="chunk-list">{result.items.map(item => <li key={`${item.run_id}-${item.ordinal}`}><h3>{item.rank}. {item.filename}</h3><p className="chunk-provenance">Cosine distance {item.cosine_distance.toFixed(4)} · Processing version {item.processing_version} · Chunk {item.ordinal + 1} · {item.page_number ? `PDF page ${item.page_number} · ` : ''}Characters {item.start_char}–{item.end_char}</p><pre>{item.text}</pre><details className="source-metadata"><summary>Source identity</summary><p>Document: {item.document_id}</p><p>Processing run: {item.run_id}</p><p>SHA-256: {item.content_hash}</p></details></li>)}</ol>
      </section>}
    </details>
  </section>;
}
