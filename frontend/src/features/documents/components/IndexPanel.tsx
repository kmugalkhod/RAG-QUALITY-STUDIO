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
import { EmptyState } from '../../../components/states/EmptyState';
import { ErrorState } from '../../../components/states/ErrorState';
import { cn } from '../../../lib/utils';
import {
  createDefaultRetrievalSettings,
  validateRetrievalSettings,
  type RetrievalSettings,
} from '../../../lib/retrieval';
import { allPages } from '../../../lib/pagination';
import * as api from '../indexApi';
import { docsHref } from '../../../lib/docs';
import type { EmbeddingSettings, IndexVersion, Retrieval } from '../model';
import { collectionGroups, IndexList } from './IndexList';
import { IndexRecords } from './IndexRecords';
import { IndexSearch } from './IndexSearch';
import {
  CARD,
  Facts,
  InlineError,
  LINK,
  LIST,
  LIST_ROW,
  META,
  Notice,
  SELECT_ROW,
  SUMMARY,
  SectionHeading,
} from '../../../components/parts';

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
const SHORT_DATE = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
});

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

  const detailOpen = Boolean(selected || selectionError);
  return (
    <section
      className="flex flex-col gap-6"
      aria-labelledby="index-title"
      data-testid="index-workspace"
    >
      <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="flex min-w-0 flex-col gap-1">
          <h2 id="index-title" className="text-base font-semibold text-foreground">
            Searchable collections
          </h2>
          <p className="text-sm text-foreground-muted">
            Publish prepared content into an immutable version that retrieval can use.
          </p>
          <a
            className={cn(LINK, 'self-start')}
            href={docsHref('knowledge-base/collections')}
            target="_blank"
            rel="noopener noreferrer"
          >
            How collection versions work
          </a>
        </div>
        <Button
          onClick={() => void create()}
          disabled={busy || hasActive || !settings?.configured}
          className="max-md:w-full"
        >
          <Plus aria-hidden="true" /> Publish prepared documents
        </Button>
      </header>
      {settings && !settings.configured && (
        <InlineError>
          <strong className="font-semibold">Publishing is unavailable</strong> {settings.error}
        </InlineError>
      )}
      {error && <InlineError>{error}</InlineError>}
      {notice && <Notice>{notice}</Notice>}
      <div
        className="flex flex-col gap-6 desktop:flex-row desktop:items-start"
        data-detail-open={detailOpen ? 'true' : 'false'}
      >
        <div
          className={cn(
            'flex min-w-0 flex-col desktop:w-panel desktop:shrink-0',
            detailOpen && 'max-md:hidden',
          )}
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
        </div>
        <section
          className={cn('flex min-w-0 flex-1 flex-col gap-6', !detailOpen && 'max-md:hidden')}
          aria-label="Selected collection details"
        >
          {selectionError ? (
            <ErrorState
              title="Version unavailable"
              headingLevel="h2"
              message={selectionError}
              action={
                <Button variant="outline" onClick={closeDetail}>
                  Back to collections
                </Button>
              }
            />
          ) : !selected ? (
            <EmptyState
              icon={<Box />}
              title="Select a collection"
              headingLevel="h2"
              description="Choose a collection to see exactly what it contains and which immutable version is in use."
            />
          ) : (
            <>
              <Button variant="ghost" className="self-start md:hidden" onClick={closeDetail}>
                <ArrowLeft aria-hidden="true" /> Back to collections
              </Button>
              <header
                className={cn(CARD, 'flex flex-col gap-4 p-4 md:flex-row md:justify-between')}
              >
                <div className="flex min-w-0 flex-col gap-1">
                  <p className={META}>Selected collection</p>
                  <h2 className="text-lg font-semibold text-foreground wrap-anywhere">
                    {selected.knowledge_set_name}
                  </h2>
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <strong className="font-semibold text-foreground">
                      Version {selected.version}
                    </strong>
                    <StatusBadge status={selected.status}>{friendlyStatus(selected)}</StatusBadge>
                    {selected.is_current && <StatusBadge status="configured">Current</StatusBadge>}
                  </div>
                </div>
                <div className="flex items-start gap-2 text-sm text-foreground-muted md:w-1/3 [&>svg]:mt-1 [&>svg]:size-4 [&>svg]:shrink-0 [&>svg]:text-foreground-subtle">
                  {selected.is_current && selected.status === 'succeeded' ? (
                    <>
                      <FileStack aria-hidden="true" />
                      <span>
                        <strong className="block font-semibold text-foreground">
                          Ready for retrieval
                        </strong>
                        This is the collection’s current immutable version.
                      </span>
                    </>
                  ) : selected.status === 'succeeded' ? (
                    <>
                      <Layers3 aria-hidden="true" />
                      <span>
                        <strong className="block font-semibold text-foreground">
                          Historical version
                        </strong>
                        Retrieval tests and pipelines use it only when explicitly selected.
                      </span>
                    </>
                  ) : (
                    <>
                      <Info aria-hidden="true" />
                      <span>
                        <strong className="block font-semibold text-foreground">
                          Not ready yet
                        </strong>
                        This version cannot be used for retrieval until publication succeeds.
                      </span>
                    </>
                  )}
                </div>
              </header>
              {(selected.status === 'succeeded' || selected.source_snapshot_id) && (
                <div className="flex flex-wrap gap-2 max-md:*:w-full">
                  {selected.status === 'succeeded' && (
                    <Button variant="outline" asChild>
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
              )}
              <Tabs
                value={section}
                onValueChange={(value) => setSection(value as DetailSection)}
                className="gap-6"
              >
                <div className="overflow-x-auto border-b border-border">
                  <TabsList
                    variant="line"
                    className="justify-start"
                    aria-label="Collection details"
                  >
                    <TabsTrigger value="overview" className="flex-none px-3">
                      <BookOpen aria-hidden="true" /> Overview
                    </TabsTrigger>
                    <TabsTrigger value="sources" className="flex-none px-3">
                      <GitBranch aria-hidden="true" /> Sources
                    </TabsTrigger>
                    <TabsTrigger value="versions" className="flex-none px-3">
                      <Layers3 aria-hidden="true" /> Versions
                    </TabsTrigger>
                    <TabsTrigger
                      value="passages"
                      className="flex-none px-3"
                      disabled={selected.status !== 'succeeded'}
                    >
                      <Braces aria-hidden="true" /> Passages
                    </TabsTrigger>
                    <TabsTrigger
                      value="retrieval"
                      className="flex-none px-3"
                      disabled={selected.status !== 'succeeded'}
                    >
                      <Search aria-hidden="true" /> Test retrieval
                    </TabsTrigger>
                  </TabsList>
                </div>
                <TabsContent value="overview">
                  <section
                    aria-labelledby="collection-overview-title"
                    className="flex flex-col gap-6"
                  >
                    <SectionHeading
                      id="collection-overview-title"
                      title="What this version contains"
                      description="A plain-language summary before build and embedding details."
                    />
                    <Facts
                      className={cn(CARD, 'p-4')}
                      items={[
                        ['Source content', sourceSummary(selected)],
                        ['Stored passages', selected.embedded_count.toLocaleString()],
                        [
                          'Published',
                          <time key="published" dateTime={selected.created_at}>
                            {SHORT_DATE.format(new Date(selected.created_at))}
                          </time>,
                        ],
                        [
                          'Pipeline default',
                          selected.is_current && selected.status === 'succeeded'
                            ? 'Current version'
                            : 'Explicit selection only',
                        ],
                      ]}
                    />
                    {['queued', 'running'].includes(selected.status) && (
                      <div className="flex flex-col gap-2 text-sm text-foreground" role="status">
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
                    {selected.error && (
                      <p className="text-sm text-danger wrap-anywhere">{selected.error}</p>
                    )}
                    <details className="border-y border-border">
                      <summary className={SUMMARY}>
                        <Database aria-hidden="true" /> Embedding and build details
                      </summary>
                      <Facts
                        className="pb-4"
                        items={[
                          ['Provider', selected.embedding_config.provider],
                          ['Model', selected.embedding_config.model],
                          [
                            'Vector dimensions',
                            selected.embedding_config.dimensions.toLocaleString(),
                          ],
                          ['Configuration revision', selected.embedding_config.revision],
                          ['Build attempts', selected.attempts.toLocaleString()],
                        ]}
                      />
                    </details>
                  </section>
                </TabsContent>
                <TabsContent value="sources">
                  <section aria-labelledby="index-lineage-title" className="flex flex-col gap-6">
                    <SectionHeading
                      id="index-lineage-title"
                      title="Sources and provenance"
                      description="The immutable inputs used to build this exact version."
                    />
                    {selected.source_snapshot_id ? (
                      <ol className={LIST}>
                        {[
                          [
                            `Source snapshot ${selected.source_snapshot_number ?? '—'}`,
                            `Immutable captured source${
                              selected.source_snapshot_collected_at
                                ? ` · ${SHORT_DATE.format(new Date(selected.source_snapshot_collected_at))}`
                                : ' · collection time unavailable'
                            }`,
                          ],
                          [
                            selected.ingestion_pipeline_name || 'Ingestion pipeline unavailable',
                            `${
                              selected.ingestion_pipeline_version
                                ? `Version ${selected.ingestion_pipeline_version}`
                                : 'Legacy pipeline lineage unavailable'
                            }${
                              selected.chunk_size
                                ? ` · ${selected.chunk_size.toLocaleString()} characters · ${(selected.chunk_overlap ?? 0).toLocaleString()} overlap`
                                : ''
                            }`,
                          ],
                          [
                            `${selected.knowledge_set_name} · Version ${selected.version}`,
                            `${selected.chunk_count.toLocaleString()} passages · ${friendlyStatus(selected)}`,
                          ],
                        ].map(([title, detail], step) => (
                          <li key={step} className={cn(LIST_ROW, 'flex items-start gap-3 p-4')}>
                            <span
                              aria-hidden="true"
                              className="flex size-6 shrink-0 items-center justify-center rounded-full border border-border-strong text-xs text-foreground-muted tabular-nums"
                            >
                              {step + 1}
                            </span>
                            <span className="flex min-w-0 flex-col gap-1">
                              <strong className="text-sm font-semibold text-foreground wrap-anywhere">
                                {title}
                              </strong>
                              <span className={META}>{detail}</span>
                            </span>
                          </li>
                        ))}
                      </ol>
                    ) : selected.ingestion_pipeline_id ? (
                      <p className="text-sm text-warning">
                        Legacy collection version — a source snapshot is unavailable, so historical
                        equivalence cannot be proven.
                      </p>
                    ) : (
                      <div className={cn(CARD, 'flex items-start gap-3 p-4')}>
                        <FileStack
                          aria-hidden="true"
                          className="mt-1 size-4 shrink-0 text-foreground-subtle"
                        />
                        <div className="flex flex-col gap-1">
                          <strong className="text-sm font-semibold text-foreground">
                            Uploaded document preparations
                          </strong>
                          <p className="text-sm text-foreground-muted">
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
                <TabsContent value="versions">
                  <section
                    aria-labelledby="collection-versions-title"
                    className="flex flex-col gap-6"
                  >
                    <SectionHeading
                      id="collection-versions-title"
                      title="Version history"
                      description="Every version is immutable. Selecting one changes only what you inspect."
                    />
                    <ul className={LIST}>
                      {versions.map((version) => (
                        <li
                          key={version.id}
                          data-selected={version.id === selected.id}
                          className={cn(LIST_ROW, 'flex flex-col')}
                        >
                          <Button
                            variant="ghost"
                            className={SELECT_ROW}
                            onClick={() => selectIndex(version, 'versions')}
                            aria-pressed={version.id === selected.id}
                            aria-label={`View ${version.knowledge_set_name} version ${version.version}`}
                          >
                            <span className="flex flex-wrap items-center gap-2">
                              <strong className="font-semibold">Version {version.version}</strong>
                              <StatusBadge status={version.status}>
                                {friendlyStatus(version)}
                              </StatusBadge>
                              {version.is_current && (
                                <StatusBadge status="configured">Current</StatusBadge>
                              )}
                            </span>
                            <small className={META}>
                              {version.embedded_count.toLocaleString()} of{' '}
                              {version.chunk_count.toLocaleString()} passages ·{' '}
                              {SHORT_DATE.format(new Date(version.created_at))}
                            </small>
                          </Button>
                          {['queued', 'running'].includes(version.status) && (
                            <div className="flex items-center gap-3 px-4 pb-3">
                              <Progress
                                className="flex-1"
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
                          {version.error && (
                            <p className="px-4 pb-3 text-xs text-danger wrap-anywhere">
                              {version.error}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  </section>
                </TabsContent>
                <TabsContent value="passages">
                  {selected.status === 'succeeded' && (
                    <IndexRecords projectId={projectId} index={selected} />
                  )}
                </TabsContent>
                <TabsContent value="retrieval">
                  {selected.status === 'succeeded' && (
                    <section aria-labelledby="retrieval-test-title" className="flex flex-col gap-6">
                      <SectionHeading
                        id="retrieval-test-title"
                        title="Test retrieval"
                        description="See the passages this exact immutable version returns. No answer is generated."
                      />
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
    </section>
  );
}
