import { useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, Box, Database, GitBranch, Globe2, Plus, Search } from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { Progress } from '../../../components/ui/progress';
import { StatusBadge } from '../../../components/StatusBadge';
import { Tabs, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import {
  createDefaultRetrievalSettings,
  validateRetrievalSettings,
  type RetrievalSettings,
} from '../../../lib/retrieval';
import * as api from '../indexApi';
import type { EmbeddingSettings, IndexPage, IndexVersion, Retrieval } from '../model';
import { IndexList } from './IndexList';
import { IndexRecords } from './IndexRecords';
import { IndexSearch } from './IndexSearch';
import { SourceSnapshotsPanel } from './SourceSnapshotsPanel';

const message = (cause: unknown) =>
  cause instanceof Error ? cause.message : 'Request failed. Please try again.';

export function IndexPanel({ projectId }: { projectId: string }) {
  const [mode, setModeState] = useState<'snapshots' | 'indexes'>(() =>
    new URLSearchParams(window.location.hash.split('?')[1]).get('mode') === 'snapshots'
      ? 'snapshots'
      : 'indexes',
  );
  const [page, setPage] = useState<IndexPage>();
  const [settings, setSettings] = useState<EmbeddingSettings>();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<IndexVersion>();
  const [query, setQuery] = useState('');
  const [retrieval, setRetrieval] = useState<RetrievalSettings>(createDefaultRetrievalSettings());
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [result, setResult] = useState<Retrieval>();

  function setMode(value: 'snapshots' | 'indexes') {
    setModeState(value);
    const [path, query] = window.location.hash.split('?');
    const params = new URLSearchParams(query);
    params.set('view', 'indexes');
    params.set('mode', value);
    if (value === 'snapshots') {
      params.delete('index');
    } else {
      params.delete('snapshot');
    }
    window.history.replaceState(null, '', `#${path}?${params}`);
  }

  useEffect(() => {
    const restoreMode = () =>
      setModeState(
        new URLSearchParams(window.location.hash.split('?')[1]).get('mode') === 'snapshots'
          ? 'snapshots'
          : 'indexes',
      );
    window.addEventListener('hashchange', restoreMode);
    return () => window.removeEventListener('hashchange', restoreMode);
  }, []);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const [indexes, config] = await Promise.all([
          api.listIndexes(projectId, offset),
          api.getEmbeddingSettings(projectId),
        ]);
        if (!disposed) {
          setPage(indexes);
          setSettings(config);
          setLoadError('');
          const linkedId = new URLSearchParams(window.location.hash.split('?')[1]).get('index');
          if (!selected && !linkedId) {
            const current = indexes.items
              .filter((index) => index.is_current && index.status === 'succeeded')
              .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
            if (current) {
              setSelected(current);
            }
          }
        }
      } catch (cause) {
        if (!disposed) {
          setLoadError(message(cause));
        }
      }
      if (!disposed) {
        timer = setTimeout(() => void load(), 2000);
      }
    }
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [projectId, offset, revision, selected]);

  useEffect(() => {
    let disposed = false;
    let request = 0;
    const restore = () => {
      const seq = ++request;
      const id = new URLSearchParams(window.location.hash.split('?')[1]).get('index');
      setResult(undefined);
      setSearchError('');
      if (!id) {
        return;
      }
      void api
        .getIndex(projectId, id)
        .then((index) => {
          if (disposed || seq !== request) {
            return;
          }
          setSelected(index);
        })
        .catch((cause) => !disposed && seq === request && setSearchError(message(cause)));
    };
    restore();
    window.addEventListener('hashchange', restore);
    return () => {
      disposed = true;
      window.removeEventListener('hashchange', restore);
    };
  }, [projectId]);

  function selectIndex(index: IndexVersion) {
    setSelected(index);
    setResult(undefined);
    setSearchError('');
    const [path, search] = window.location.hash.split('?');
    const params = new URLSearchParams(search);
    params.set('view', 'indexes');
    params.set('mode', 'indexes');
    params.set('index', index.id);
    params.delete('snapshot');
    window.history.replaceState(
      null,
      '',
      `#${path || `/projects/${projectId}/knowledge-base`}?${params}`,
    );
  }

  async function create() {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const index = await api.createIndex(projectId);
      setNotice(
        `Uploaded documents index version ${index.version} created with ${index.chunk_count} passages. Preparation has started.`,
      );
      setOffset(0);
      setRevision((value) => value + 1);
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  async function cancel(index: IndexVersion) {
    setBusy(true);
    setError('');
    try {
      const value = await api.cancelIndex(projectId, index.id);
      setNotice(`Index version ${index.version} ${value.status}.`);
      setRevision((current) => current + 1);
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  async function search(event: FormEvent) {
    event.preventDefault();
    setSearchError('');
    setResult(undefined);
    if (
      !selected ||
      !query.trim() ||
      query.trim().length > 8000 ||
      validateRetrievalSettings(retrieval).length > 0
    ) {
      setSearchError('Choose an index, enter a query, and correct the retrieval settings.');
      return;
    }
    setSearching(true);
    try {
      setResult(await api.retrieve(projectId, selected.id, query.trim(), retrieval));
    } catch (cause) {
      setSearchError(message(cause));
    } finally {
      setSearching(false);
    }
  }

  const hasActive = page?.items.some((index) => ['queued', 'running'].includes(index.status));

  function closeDetail() {
    setSelected(undefined);
    const [path, query] = window.location.hash.split('?');
    const params = new URLSearchParams(query);
    params.delete('index');
    window.history.replaceState(null, '', `#${path}?${params}`);
  }

  return (
    <section className="index-workspace" aria-labelledby="index-title">
      <header className="index-workspace-header">
        <div>
          <h2 id="index-title">Indexes</h2>
          <p>Trace collected Website content into exact searchable index versions.</p>
        </div>
        {mode === 'indexes' && (
          <Button
            onClick={() => void create()}
            disabled={busy || hasActive || !settings?.configured}
          >
            <Plus /> Prepare uploaded documents
          </Button>
        )}
      </header>
      <Tabs value={mode} onValueChange={(value) => setMode(value as typeof mode)}>
        <TabsList variant="line" aria-label="Index views" className="index-mode-tabs">
          <TabsTrigger value="snapshots">
            <Globe2 /> Source snapshots
          </TabsTrigger>
          <TabsTrigger value="indexes">
            <Database /> Indexes
          </TabsTrigger>
        </TabsList>
      </Tabs>
      {mode === 'snapshots' ? (
        <SourceSnapshotsPanel projectId={projectId} />
      ) : (
        <>
          {settings?.config && (
            <div className="embedding-summary" aria-label="Embedding configuration">
              <Database />
              <div>
                <span>Provider</span>
                <strong>{settings.config.provider}</strong>
              </div>
              <div>
                <span>Model</span>
                <strong>{settings.config.model}</strong>
              </div>
              <div>
                <span>Dimensions</span>
                <strong>{settings.config.dimensions.toLocaleString()}</strong>
              </div>
              <div>
                <span>Revision</span>
                <strong>{settings.config.revision}</strong>
              </div>
            </div>
          )}
          {settings && !settings.configured && <p className="error-message">{settings.error}</p>}
          {error && (
            <p role="alert" className="error-message">
              {error}
            </p>
          )}
          {notice && (
            <p role="status" className="success-message">
              {notice}
            </p>
          )}
          <div className="index-browser-layout" data-detail-open={selected ? 'true' : 'false'}>
            <IndexList
              page={page}
              offset={offset}
              selectedId={selected?.id}
              busy={busy}
              loadError={loadError}
              onRefresh={() => setRevision((value) => value + 1)}
              onPage={setOffset}
              onCancel={(index) => void cancel(index)}
              onSelect={selectIndex}
            />
            <section className="index-detail" aria-label="Selected index details">
              {!selected ? (
                <div className="index-detail-empty">
                  <Box />
                  <h2>Select an index version</h2>
                  <p>
                    Inspect stored vector records and run a retrieval test without generating an
                    answer.
                  </p>
                  <IndexSearch
                    selected={selected}
                    query={query}
                    settings={retrieval}
                    searching={searching}
                    error={searchError}
                    result={result}
                    onQueryChange={setQuery}
                    onSettingsChange={setRetrieval}
                    onSubmit={search}
                  />
                </div>
              ) : (
                <>
                  <Button variant="ghost" className="mobile-detail-back" onClick={closeDetail}>
                    <ArrowLeft /> Back to indexes
                  </Button>
                  <header className="index-detail-header">
                    <div>
                      <p>{selected.knowledge_set_name}</p>
                      <h2>Version {selected.version}</h2>
                    </div>
                    <StatusBadge status={selected.status}>
                      {selected.is_current ? 'Current index' : 'Historical index'}
                    </StatusBadge>
                  </header>
                  <div className="index-detail-actions">
                    {selected.status === 'succeeded' && (
                      <Button asChild>
                        <a href={`#/projects/${projectId}/pipelines/new?index=${selected.id}`}>
                          Use in answer pipeline
                        </a>
                      </Button>
                    )}
                    {selected.source_snapshot && (
                      <Button variant="outline" asChild>
                        <a
                          href={`#/projects/${projectId}/knowledge-base?view=indexes&mode=snapshots&snapshot=${selected.source_snapshot.id}`}
                        >
                          Build another variant
                        </a>
                      </Button>
                    )}
                  </div>
                  <section className="index-lineage" aria-labelledby="index-lineage-title">
                    <div className="retrieval-check-heading">
                      <GitBranch />
                      <div>
                        <h3 id="index-lineage-title">Build lineage</h3>
                        <p>The immutable source and saved configuration used for this index.</p>
                      </div>
                    </div>
                    {selected.source_snapshot ? (
                      <ol>
                        <li>
                          <strong>
                            Source snapshot {selected.source_snapshot.snapshot_number}
                          </strong>
                          <span>
                            {selected.source_snapshot.collected_at
                              ? new Intl.DateTimeFormat(undefined, {
                                  month: 'short',
                                  day: 'numeric',
                                  year: 'numeric',
                                }).format(new Date(selected.source_snapshot.collected_at))
                              : 'Collection time unavailable'}{' '}
                            · {selected.source_snapshot.included_count.toLocaleString()} pages
                          </span>
                        </li>
                        <li>
                          <strong>
                            {selected.ingestion_pipeline?.name || 'Ingestion pipeline unavailable'}
                          </strong>
                          <span>
                            {selected.ingestion_pipeline
                              ? `Version ${selected.ingestion_pipeline.version}`
                              : 'Legacy pipeline lineage unavailable'}
                            {selected.processing_summary
                              ? ` · ${selected.processing_summary.size.toLocaleString()} characters · ${selected.processing_summary.overlap.toLocaleString()} overlap`
                              : ''}
                          </span>
                        </li>
                        <li>
                          <strong>
                            {selected.knowledge_set_name} · Version {selected.version}
                          </strong>
                          <span>
                            {selected.chunk_count.toLocaleString()} passages ·{' '}
                            {selected.status === 'succeeded' ? 'Ready' : selected.status}
                          </span>
                        </li>
                      </ol>
                    ) : selected.source_kind === 'website' ? (
                      <p className="legacy-lineage-warning">
                        Legacy index — source snapshot unavailable. Historical equivalence was not
                        provable, so no snapshot was invented.
                      </p>
                    ) : (
                      <p className="legacy-lineage-warning">
                        Built from uploaded document processing runs; no Website snapshot applies.
                      </p>
                    )}
                  </section>
                  <dl className="index-detail-stats">
                    <div>
                      <dt>Stored passages</dt>
                      <dd>{selected.embedded_count.toLocaleString()}</dd>
                    </div>
                    <div>
                      <dt>Source revisions</dt>
                      <dd>{selected.processing_run_count.toLocaleString()}</dd>
                    </div>
                    <div>
                      <dt>Vector dimensions</dt>
                      <dd>{selected.embedding_config.dimensions.toLocaleString()}</dd>
                    </div>
                  </dl>
                  {selected.status === 'succeeded' ? (
                    <IndexRecords projectId={projectId} index={selected} />
                  ) : (
                    <div className="snapshot-run-progress" role="status">
                      <span>
                        {['queued', 'running'].includes(selected.status)
                          ? `Preparing ${selected.embedded_count.toLocaleString()} of ${selected.chunk_count.toLocaleString()} passages`
                          : `Index ${selected.status}`}
                      </span>
                      {['queued', 'running'].includes(selected.status) && (
                        <Progress
                          value={
                            selected.chunk_count
                              ? (selected.embedded_count / selected.chunk_count) * 100
                              : 0
                          }
                        />
                      )}
                      {selected.error && <p className="error-message">{selected.error}</p>}
                    </div>
                  )}
                  {selected.status === 'succeeded' && (
                    <>
                      <div className="retrieval-check-heading">
                        <Search />
                        <div>
                          <h3>Retrieval check</h3>
                          <p>
                            Confirm which passages a question will retrieve before using this index
                            in a pipeline.
                          </p>
                        </div>
                      </div>
                      <IndexSearch
                        selected={selected}
                        query={query}
                        settings={retrieval}
                        searching={searching}
                        error={searchError}
                        result={result}
                        onQueryChange={(value) => {
                          setQuery(value);
                          setResult(undefined);
                        }}
                        onSettingsChange={(value) => {
                          setRetrieval(value);
                          setResult(undefined);
                        }}
                        onSubmit={search}
                      />
                    </>
                  )}
                </>
              )}
            </section>
          </div>
        </>
      )}
    </section>
  );
}
