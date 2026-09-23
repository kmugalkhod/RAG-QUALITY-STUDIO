import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import {
  ArrowLeft,
  BookOpen,
  Box,
  Braces,
  Database,
  FileStack,
  GitBranch,
  Info,
  Layers3,
  Plus,
  Search,
} from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { Progress } from '../../../components/ui/progress';
import { StatusBadge } from '../../../components/StatusBadge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import {
  createDefaultRetrievalSettings,
  validateRetrievalSettings,
  type RetrievalSettings,
} from '../../../lib/retrieval';
import { allPages } from '../../../lib/pagination';
import * as api from '../indexApi';
import type { EmbeddingSettings, IndexVersion, Retrieval } from '../model';
import { collectionGroups, IndexList } from './IndexList';
import { IndexRecords } from './IndexRecords';
import { IndexSearch } from './IndexSearch';

const message = (cause: unknown) =>
  cause instanceof Error ? cause.message : 'Request failed. Please try again.';

type DetailSection = 'overview' | 'sources' | 'versions' | 'passages' | 'retrieval';

const detailSections = new Set<DetailSection>([
  'overview',
  'sources',
  'versions',
  'passages',
  'retrieval',
]);
const COLLECTION_PAGE_SIZE = 20;

function readParams() {
  return new URLSearchParams(window.location.hash.split('?')[1]);
}

function readSection(): DetailSection {
  const value = readParams().get('section') as DetailSection | null;
  return value && detailSections.has(value) ? value : 'overview';
}

function sourceSummary(index: IndexVersion) {
  const unit = index.source_snapshot_id ? 'prepared source revision' : 'prepared document version';
  return `${index.processing_run_count.toLocaleString()} ${unit}${index.processing_run_count === 1 ? '' : 's'}`;
}

function friendlyStatus(index: IndexVersion) {
  if (index.status === 'succeeded') {
    return 'Ready';
  }
  if (['queued', 'running'].includes(index.status)) {
    return 'Publishing';
  }
  return index.status;
}

export function IndexPanel({ projectId }: { projectId: string }) {
  const [section, setSectionState] = useState<DetailSection>(readSection);
  const [indexes, setIndexes] = useState<IndexVersion[]>();
  const [settings, setSettings] = useState<EmbeddingSettings>();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [selectionError, setSelectionError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<IndexVersion>();
  const [query, setQuery] = useState('');
  const [retrieval, setRetrieval] = useState<RetrievalSettings>(createDefaultRetrievalSettings());
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [result, setResult] = useState<Retrieval>();
  const initialSelectionResolved = useRef(false);

  function writeParams(mutator: (params: URLSearchParams) => void, replace = false) {
    const [rawPath, search] = window.location.hash.split('?');
    const path = rawPath.replace(/^#+/, '');
    const params = new URLSearchParams(search);
    mutator(params);
    const next = `#${path || `/projects/${projectId}/knowledge-base`}${params.size ? `?${params}` : ''}`;
    window.history[replace ? 'replaceState' : 'pushState'](null, '', next);
  }

  function setSection(value: DetailSection) {
    setSectionState(value);
    setResult(undefined);
    setSearchError('');
    writeParams((params) => {
      params.set('view', 'indexes');
      params.set('mode', 'indexes');
      if (selected) {
        params.set('index', selected.id);
      }
      params.set('section', value);
    });
  }

  useEffect(() => {
    const restoreView = () => {
      setSectionState(readSection());
    };
    window.addEventListener('hashchange', restoreView);
    window.addEventListener('popstate', restoreView);
    return () => {
      window.removeEventListener('hashchange', restoreView);
      window.removeEventListener('popstate', restoreView);
    };
  }, []);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      let nextDelay = 10_000;
      try {
        const [nextIndexes, config] = await Promise.all([
          allPages((nextOffset) => api.listIndexes(projectId, nextOffset)),
          api.getEmbeddingSettings(projectId),
        ]);
        if (nextIndexes.some((index) => ['queued', 'running'].includes(index.status))) {
          nextDelay = 2_000;
        }
        if (!disposed) {
          setIndexes(nextIndexes);
          setSettings(config);
          setLoadError('');
          setSelected((currentSelected) => {
            if (currentSelected) {
              return (
                nextIndexes.find((index) => index.id === currentSelected.id) ?? currentSelected
              );
            }
            return currentSelected;
          });
        }
      } catch (cause) {
        nextDelay = 5_000;
        if (!disposed) {
          setLoadError(message(cause));
        }
      }
      if (!disposed) {
        timer = setTimeout(() => void load(), nextDelay);
      }
    }
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [projectId, revision]);

  useEffect(() => {
    let disposed = false;
    let request = 0;
    const restore = () => {
      const seq = ++request;
      const id = readParams().get('index');
      setResult(undefined);
      setSearchError('');
      if (!id) {
        setSelected(undefined);
        setSelectionError('');
        return;
      }
      void api
        .getIndex(projectId, id)
        .then((index) => {
          if (disposed || seq !== request) {
            return;
          }
          setSelected(index);
          setSelectionError('');
        })
        .catch((cause) => {
          if (disposed || seq !== request) {
            return;
          }
          setSelected(undefined);
          setSelectionError(
            `That collection version is no longer available in this project. ${message(cause)}`,
          );
        });
    };
    restore();
    window.addEventListener('hashchange', restore);
    window.addEventListener('popstate', restore);
    return () => {
      disposed = true;
      window.removeEventListener('hashchange', restore);
      window.removeEventListener('popstate', restore);
    };
  }, [projectId]);

  useEffect(() => {
    if (
      initialSelectionResolved.current ||
      selected ||
      !indexes?.length ||
      readParams().get('index')
    ) {
      return;
    }
    initialSelectionResolved.current = true;
    setSelected(
      indexes.find((index) => index.is_current && index.status === 'succeeded') ?? indexes[0],
    );
  }, [indexes, selected]);

  useEffect(() => {
    if (!selected || readParams().get('index')) {
      return;
    }
    const [rawPath, search] = window.location.hash.split('?');
    const path = rawPath.replace(/^#+/, '');
    const params = new URLSearchParams(search);
    params.set('view', 'indexes');
    params.set('mode', 'indexes');
    params.set('index', selected.id);
    params.set('section', section);
    window.history.replaceState(null, '', `#${path}?${params}`);
  }, [section, selected]);

  function selectIndex(index: IndexVersion, nextSection: DetailSection = 'overview') {
    setSelected(index);
    setSectionState(nextSection);
    setResult(undefined);
    setSearchError('');
    setSelectionError('');
    writeParams((params) => {
      params.set('view', 'indexes');
      params.set('mode', 'indexes');
      params.set('index', index.id);
      params.set('section', nextSection);
      params.delete('snapshot');
    });
  }

  async function create() {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const index = await api.createIndex(projectId);
      setNotice(
        `${index.knowledge_set_name} version ${index.version} is queued for publication with ${index.chunk_count.toLocaleString()} passages.`,
      );
      setOffset(0);
      selectIndex(index);
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
      setNotice(`${value.knowledge_set_name} version ${value.version} is ${value.status}.`);
      if (selected?.id === value.id) {
        setSelected(value);
      }
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
      setSearchError('Choose a ready collection version, enter a query, and correct the settings.');
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

  const groups = useMemo(() => collectionGroups(indexes), [indexes]);
  const visibleGroups = groups.slice(offset, offset + COLLECTION_PAGE_SIZE);
  const selectedGroup = groups.find((group) => group.id === selected?.knowledge_set_id);
  const versions = useMemo(() => {
    if (!selected) {
      return [];
    }
    const values = [...(selectedGroup?.versions ?? [])];
    if (!values.some((value) => value.id === selected.id)) {
      values.push(selected);
    }
    return values.sort((a, b) => b.version - a.version);
  }, [selected, selectedGroup]);
  const hasActive = indexes?.some((index) => ['queued', 'running'].includes(index.status));

  useEffect(() => {
    if (offset > 0 && offset >= groups.length) {
      setOffset(0);
    }
  }, [groups.length, offset]);

  function closeDetail() {
    initialSelectionResolved.current = true;
    setSelected(undefined);
    setSelectionError('');
    setSectionState('overview');
    writeParams((params) => {
      params.delete('index');
      params.delete('section');
    });
  }

  return (
    <section className="index-workspace" aria-labelledby="index-title">
      <header className="index-workspace-header">
        <div>
          <h2 id="index-title">Searchable collections</h2>
          <p>Publish prepared content into an immutable version that retrieval can use.</p>
        </div>
        <Button onClick={() => void create()} disabled={busy || hasActive || !settings?.configured}>
          <Plus /> Publish prepared documents
        </Button>
      </header>
      <>
        {settings && !settings.configured && (
          <div className="inline-error index-config-error" role="alert">
            <div>
              <strong>Publishing is unavailable</strong>
              <p>{settings.error}</p>
            </div>
          </div>
        )}
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
        <div
          className={`index-browser-layout ${selected || selectionError ? 'has-selection' : ''}`}
          data-detail-open={selected || selectionError ? 'true' : 'false'}
        >
          <IndexList
            groups={indexes ? visibleGroups : undefined}
            total={groups.length}
            pageSize={COLLECTION_PAGE_SIZE}
            offset={offset}
            selected={selected}
            loadError={loadError}
            onRefresh={() => setRevision((value) => value + 1)}
            onPage={setOffset}
            onSelect={selectIndex}
          />
          <section className="index-detail" aria-label="Selected collection details">
            {selectionError ? (
              <div className="index-detail-empty stale-selection" role="alert">
                <Info />
                <h2>Version unavailable</h2>
                <p>{selectionError}</p>
                <Button variant="outline" onClick={closeDetail}>
                  Back to collections
                </Button>
              </div>
            ) : !selected ? (
              <div className="index-detail-empty">
                <Box />
                <h2>Select a collection</h2>
                <p>
                  Choose a collection to see exactly what it contains and which immutable version is
                  in use.
                </p>
              </div>
            ) : (
              <>
                <Button variant="ghost" className="mobile-detail-back" onClick={closeDetail}>
                  <ArrowLeft /> Back to collections
                </Button>
                <header className="collection-context">
                  <div className="collection-context-copy">
                    <p>Selected collection</p>
                    <h2>{selected.knowledge_set_name}</h2>
                    <div className="collection-version-line">
                      <strong>Version {selected.version}</strong>
                      <StatusBadge status={selected.status}>{friendlyStatus(selected)}</StatusBadge>
                      {selected.is_current && (
                        <StatusBadge status="configured">Current</StatusBadge>
                      )}
                    </div>
                  </div>
                  <div className="collection-use-state">
                    {selected.is_current && selected.status === 'succeeded' ? (
                      <>
                        <FileStack />
                        <span>
                          <strong>Ready for retrieval</strong>This is the collection’s current
                          immutable version.
                        </span>
                      </>
                    ) : selected.status === 'succeeded' ? (
                      <>
                        <Layers3 />
                        <span>
                          <strong>Historical version</strong>Retrieval tests and pipelines use it
                          only when explicitly selected.
                        </span>
                      </>
                    ) : (
                      <>
                        <Info />
                        <span>
                          <strong>Not ready yet</strong>This version cannot be used for retrieval
                          until publication succeeds.
                        </span>
                      </>
                    )}
                  </div>
                </header>
                <div className="index-detail-actions">
                  {selected.status === 'succeeded' && (
                    <Button asChild>
                      <a href={`#/projects/${projectId}/pipelines/new?index=${selected.id}`}>
                        Use version {selected.version} in a pipeline
                      </a>
                    </Button>
                  )}
                  {selected.source_snapshot_id && (
                    <Button variant="outline" asChild>
                      <a
                        href={`#/projects/${projectId}/knowledge-base?view=indexes&mode=snapshots&snapshot=${selected.source_snapshot_id}`}
                      >
                        Open source snapshot
                      </a>
                    </Button>
                  )}
                </div>
                <Tabs value={section} onValueChange={(value) => setSection(value as DetailSection)}>
                  <TabsList
                    variant="line"
                    className="collection-detail-tabs"
                    aria-label="Collection details"
                  >
                    <TabsTrigger value="overview">
                      <BookOpen /> Overview
                    </TabsTrigger>
                    <TabsTrigger value="sources">
                      <GitBranch /> Sources
                    </TabsTrigger>
                    <TabsTrigger value="versions">
                      <Layers3 /> Versions
                    </TabsTrigger>
                    <TabsTrigger value="passages" disabled={selected.status !== 'succeeded'}>
                      <Braces /> Passages
                    </TabsTrigger>
                    <TabsTrigger value="retrieval" disabled={selected.status !== 'succeeded'}>
                      <Search /> Test retrieval
                    </TabsTrigger>
                  </TabsList>
                  <TabsContent value="overview" className="collection-detail-section">
                    <section aria-labelledby="collection-overview-title">
                      <div className="collection-section-heading">
                        <div>
                          <h3 id="collection-overview-title">What this version contains</h3>
                          <p>A plain-language summary before build and embedding details.</p>
                        </div>
                      </div>
                      <dl className="collection-summary-grid">
                        <div>
                          <dt>Source content</dt>
                          <dd>{sourceSummary(selected)}</dd>
                        </div>
                        <div>
                          <dt>Stored passages</dt>
                          <dd>{selected.embedded_count.toLocaleString()}</dd>
                        </div>
                        <div>
                          <dt>Published</dt>
                          <dd>
                            <time dateTime={selected.created_at}>
                              {new Intl.DateTimeFormat(undefined, {
                                month: 'short',
                                day: 'numeric',
                                year: 'numeric',
                              }).format(new Date(selected.created_at))}
                            </time>
                          </dd>
                        </div>
                        <div>
                          <dt>Pipeline default</dt>
                          <dd>
                            {selected.is_current && selected.status === 'succeeded'
                              ? 'Current version'
                              : 'Explicit selection only'}
                          </dd>
                        </div>
                      </dl>
                      {['queued', 'running'].includes(selected.status) && (
                        <div className="snapshot-run-progress" role="status">
                          <span>
                            Publishing {selected.embedded_count.toLocaleString()} of{' '}
                            {selected.chunk_count.toLocaleString()} passages
                          </span>
                          <Progress
                            value={
                              selected.chunk_count
                                ? (selected.embedded_count / selected.chunk_count) * 100
                                : 0
                            }
                          />
                        </div>
                      )}
                      {selected.error && <p className="error-message">{selected.error}</p>}
                      <details className="index-technical-details">
                        <summary>
                          <Database /> Embedding and build details
                        </summary>
                        <dl>
                          <div>
                            <dt>Provider</dt>
                            <dd>{selected.embedding_config.provider}</dd>
                          </div>
                          <div>
                            <dt>Model</dt>
                            <dd>{selected.embedding_config.model}</dd>
                          </div>
                          <div>
                            <dt>Vector dimensions</dt>
                            <dd>{selected.embedding_config.dimensions.toLocaleString()}</dd>
                          </div>
                          <div>
                            <dt>Configuration revision</dt>
                            <dd>{selected.embedding_config.revision}</dd>
                          </div>
                          <div>
                            <dt>Build attempts</dt>
                            <dd>{selected.attempts.toLocaleString()}</dd>
                          </div>
                        </dl>
                      </details>
                    </section>
                  </TabsContent>
                  <TabsContent value="sources" className="collection-detail-section">
                    <section className="index-lineage" aria-labelledby="index-lineage-title">
                      <div className="collection-section-heading">
                        <div>
                          <h3 id="index-lineage-title">Sources and provenance</h3>
                          <p>The immutable inputs used to build this exact version.</p>
                        </div>
                      </div>
                      {selected.source_snapshot_id ? (
                        <ol>
                          <li>
                            <strong>
                              Source snapshot {selected.source_snapshot_number ?? '—'}
                            </strong>
                            <span>
                              Immutable captured source
                              {selected.source_snapshot_collected_at
                                ? ` · ${new Intl.DateTimeFormat(undefined, {
                                    month: 'short',
                                    day: 'numeric',
                                    year: 'numeric',
                                  }).format(new Date(selected.source_snapshot_collected_at))}`
                                : ' · collection time unavailable'}
                            </span>
                          </li>
                          <li>
                            <strong>
                              {selected.ingestion_pipeline_name || 'Ingestion pipeline unavailable'}
                            </strong>
                            <span>
                              {selected.ingestion_pipeline_version
                                ? `Version ${selected.ingestion_pipeline_version}`
                                : 'Legacy pipeline lineage unavailable'}
                              {selected.chunk_size
                                ? ` · ${selected.chunk_size.toLocaleString()} characters · ${(selected.chunk_overlap ?? 0).toLocaleString()} overlap`
                                : ''}
                            </span>
                          </li>
                          <li>
                            <strong>
                              {selected.knowledge_set_name} · Version {selected.version}
                            </strong>
                            <span>
                              {selected.chunk_count.toLocaleString()} passages ·{' '}
                              {friendlyStatus(selected)}
                            </span>
                          </li>
                        </ol>
                      ) : selected.ingestion_pipeline_id ? (
                        <p className="legacy-lineage-warning">
                          Legacy collection version — a source snapshot is unavailable, so
                          historical equivalence cannot be proven.
                        </p>
                      ) : (
                        <div className="source-provenance-summary">
                          <FileStack />
                          <div>
                            <strong>Uploaded document preparations</strong>
                            <p>
                              {selected.processing_run_count.toLocaleString()} prepared document
                              version{selected.processing_run_count === 1 ? '' : 's'} contributed{' '}
                              {selected.chunk_count.toLocaleString()} passages. No website snapshot
                              applies.
                            </p>
                          </div>
                        </div>
                      )}
                    </section>
                  </TabsContent>
                  <TabsContent value="versions" className="collection-detail-section">
                    <section aria-labelledby="collection-versions-title">
                      <div className="collection-section-heading">
                        <div>
                          <h3 id="collection-versions-title">Version history</h3>
                          <p>
                            Every version is immutable. Selecting one changes only what you inspect.
                          </p>
                        </div>
                      </div>
                      <ul className="collection-version-list">
                        {versions.map((version) => (
                          <li key={version.id} data-selected={version.id === selected.id}>
                            <button
                              type="button"
                              onClick={() => selectIndex(version, 'versions')}
                              aria-pressed={version.id === selected.id}
                              aria-label={`View ${version.knowledge_set_name} version ${version.version}`}
                            >
                              <span>
                                <strong>Version {version.version}</strong>
                                <StatusBadge status={version.status}>
                                  {friendlyStatus(version)}
                                </StatusBadge>
                                {version.is_current && (
                                  <StatusBadge status="configured">Current</StatusBadge>
                                )}
                              </span>
                              <small>
                                {version.embedded_count.toLocaleString()} of{' '}
                                {version.chunk_count.toLocaleString()} passages ·{' '}
                                {new Intl.DateTimeFormat(undefined, {
                                  month: 'short',
                                  day: 'numeric',
                                  year: 'numeric',
                                }).format(new Date(version.created_at))}
                              </small>
                            </button>
                            {['queued', 'running'].includes(version.status) && (
                              <div className="index-progress">
                                <Progress
                                  value={
                                    version.chunk_count
                                      ? (version.embedded_count / version.chunk_count) * 100
                                      : 0
                                  }
                                />
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  disabled={busy}
                                  onClick={() => void cancel(version)}
                                  aria-label={`Cancel collection version ${version.version}`}
                                >
                                  Cancel
                                </Button>
                              </div>
                            )}
                            {version.error && <p className="error-message">{version.error}</p>}
                          </li>
                        ))}
                      </ul>
                    </section>
                  </TabsContent>
                  <TabsContent value="passages" className="collection-detail-section">
                    {selected.status === 'succeeded' && (
                      <IndexRecords projectId={projectId} index={selected} />
                    )}
                  </TabsContent>
                  <TabsContent value="retrieval" className="collection-detail-section">
                    {selected.status === 'succeeded' && (
                      <section aria-labelledby="retrieval-test-title">
                        <div className="collection-section-heading">
                          <div>
                            <h3 id="retrieval-test-title">Test retrieval</h3>
                            <p>
                              See the passages this exact immutable version returns. No answer is
                              generated.
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
                      </section>
                    )}
                  </TabsContent>
                </Tabs>
              </>
            )}
          </section>
        </div>
      </>
    </section>
  );
}
