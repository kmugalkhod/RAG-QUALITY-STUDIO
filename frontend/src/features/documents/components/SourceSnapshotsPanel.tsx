import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Database, FileText, Globe2, LoaderCircle, RefreshCw } from 'lucide-react';

import { Pagination } from '../../../components/Pagination';
import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { Progress } from '../../../components/ui/progress';
import { allPages } from '../../../lib/pagination';
import type { IngestionPipelineVersion, IngestionRun } from '../../ingestion-pipelines/model';
import * as api from '../indexApi';
import type {
  KnowledgeSet,
  SourceSnapshot,
  SourceSnapshotIndex,
  SourceSnapshotMember,
  SourceSnapshotPage,
} from '../model';

const errorText = (cause: unknown) =>
  cause instanceof Error ? cause.message : 'Request failed. Please try again.';

function date(value: string | null) {
  return value
    ? new Intl.DateTimeFormat(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      }).format(new Date(value))
    : 'Not complete';
}

function bytes(value: number) {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function statusLabel(snapshot: SourceSnapshot) {
  return snapshot.status === 'ready'
    ? 'Ready'
    : snapshot.status === 'collecting'
      ? 'Collecting'
      : snapshot.status[0].toUpperCase() + snapshot.status.slice(1);
}

function websiteVersions(versions: IngestionPipelineVersion[]) {
  return versions.filter((version) =>
    version.execution.nodes.some(
      (node) => node.type === 'source' && node.config.kind === 'website',
    ),
  );
}

function chunkSummary(version?: IngestionPipelineVersion) {
  const chunk = version?.execution.nodes.find((node) => node.type === 'chunk');
  return chunk?.type === 'chunk'
    ? `${chunk.size.toLocaleString()} characters · ${chunk.overlap.toLocaleString()} overlap`
    : 'Select a saved Website pipeline version.';
}

export function SourceSnapshotsPanel({ projectId }: { projectId: string }) {
  const [page, setPage] = useState<SourceSnapshotPage>();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [selected, setSelected] = useState<SourceSnapshot>();
  const [items, setItems] = useState<{
    items: SourceSnapshotMember[];
    total: number;
    limit: number;
    offset: number;
  }>();
  const [itemOffset, setItemOffset] = useState(0);
  const [indexes, setIndexes] = useState<{
    items: SourceSnapshotIndex[];
    total: number;
    limit: number;
    offset: number;
  }>();
  const [indexOffset, setIndexOffset] = useState(0);
  const [detailError, setDetailError] = useState('');
  const [pipelines, setPipelines] = useState<IngestionPipelineVersion[]>([]);
  const [knowledgeSets, setKnowledgeSets] = useState<KnowledgeSet[]>([]);
  const [pipelineVersionId, setPipelineVersionId] = useState('');
  const [destinationKind, setDestinationKind] = useState<'new' | 'existing'>('new');
  const [destinationName, setDestinationName] = useState('');
  const [destinationId, setDestinationId] = useState('');
  const [buildOpen, setBuildOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [notice, setNotice] = useState('');
  const [run, setRun] = useState<IngestionRun>();
  const selectedId = selected?.id;

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await api.listSourceSnapshots(projectId, offset);
        if (!disposed) {
          setPage(value);
          setLoadError('');
          const linkedId = new URLSearchParams(window.location.hash.split('?')[1]).get('snapshot');
          if (linkedId && selected?.id !== linkedId) {
            const linked = value.items.find((snapshot) => snapshot.id === linkedId);
            if (linked) {
              setSelected(linked);
            }
          }
        }
      } catch (cause) {
        if (!disposed) {
          setLoadError(errorText(cause));
        }
      }
      if (!disposed) {
        timer = setTimeout(() => void load(), 3000);
      }
    }
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [offset, projectId, revision, selected?.id]);

  useEffect(() => {
    let disposed = false;
    void Promise.all([
      allPages((next) => api.listIngestionPipelines(projectId, next)).then((summaries) =>
        Promise.all(
          summaries.map((pipeline) =>
            allPages((next) => api.listIngestionPipelineVersions(projectId, pipeline.id, next)),
          ),
        ).then((groups) => websiteVersions(groups.flat())),
      ),
      allPages((next) => api.listKnowledgeSets(projectId, next)),
    ])
      .then(([versions, sets]) => {
        if (!disposed) {
          setPipelines(versions);
          setKnowledgeSets(sets);
          setPipelineVersionId((current) => current || versions[0]?.id || '');
          setDestinationId((current) => current || sets[0]?.id || '');
        }
      })
      .catch((cause) => !disposed && setActionError(errorText(cause)));
    return () => {
      disposed = true;
    };
  }, [projectId, revision]);

  useEffect(() => {
    if (!selectedId) {
      setItems(undefined);
      setIndexes(undefined);
      return;
    }
    let disposed = false;
    void Promise.all([
      api.getSourceSnapshot(projectId, selectedId),
      api.listSourceSnapshotItems(projectId, selectedId, itemOffset),
      api.listSourceSnapshotIndexes(projectId, selectedId, indexOffset),
    ])
      .then(([snapshot, snapshotItems, downstream]) => {
        if (!disposed) {
          setSelected(snapshot);
          setItems(snapshotItems);
          setIndexes(downstream);
          setDetailError('');
        }
      })
      .catch((cause) => !disposed && setDetailError(errorText(cause)));
    return () => {
      disposed = true;
    };
  }, [indexOffset, itemOffset, projectId, revision, selectedId]);

  useEffect(() => {
    if (!run || !['queued', 'running'].includes(run.status)) {
      return;
    }
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const current = await api.getIngestionRun(projectId, run!.id);
        if (disposed) {
          return;
        }
        setRun(current);
        if (['queued', 'running'].includes(current.status)) {
          timer = setTimeout(() => void poll(), 1500);
        } else {
          setBusy(false);
          setRevision((value) => value + 1);
          setNotice(
            current.status === 'succeeded'
              ? `${current.knowledge_set_name} version ${current.published_index_version} is ready.`
              : '',
          );
          if (current.error) {
            setActionError(current.error);
          }
        }
      } catch (cause) {
        if (!disposed) {
          setBusy(false);
          setActionError(errorText(cause));
        }
      }
    }
    timer = setTimeout(() => void poll(), 750);
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [projectId, run]);

  const groups = useMemo(() => {
    const result = new Map<string, SourceSnapshot[]>();
    for (const snapshot of page?.items ?? []) {
      const origin = snapshot.source_identity.origins?.join(', ') || 'Website source';
      result.set(origin, [...(result.get(origin) ?? []), snapshot]);
    }
    return Array.from(result);
  }, [page]);
  const selectedPipeline = pipelines.find((version) => version.id === pipelineVersionId);

  function choose(snapshot?: SourceSnapshot) {
    setSelected(snapshot);
    setItemOffset(0);
    setIndexOffset(0);
    setBuildOpen(false);
    setActionError('');
    const [path, query] = window.location.hash.split('?');
    const params = new URLSearchParams(query);
    params.set('view', 'indexes');
    params.set('mode', 'snapshots');
    if (snapshot) {
      params.set('snapshot', snapshot.id);
    } else {
      params.delete('snapshot');
    }
    window.history.replaceState(null, '', `#${path}?${params}`);
  }

  async function build() {
    if (!selected || !selectedPipeline) {
      setActionError('Choose a ready snapshot and a saved Website pipeline version.');
      return;
    }
    if (destinationKind === 'new' && !destinationName.trim()) {
      setActionError('Enter a name for the new index.');
      return;
    }
    if (destinationKind === 'existing' && !destinationId) {
      setActionError('Choose an existing index destination.');
      return;
    }
    setBusy(true);
    setActionError('');
    setNotice('');
    try {
      setRun(
        await api.startSnapshotBuild(
          projectId,
          selectedPipeline.pipeline_id,
          selectedPipeline.id,
          selected.id,
          destinationKind === 'new'
            ? { kind: 'new', name: destinationName.trim() }
            : { kind: 'existing', knowledge_set_id: destinationId },
        ),
      );
    } catch (cause) {
      setBusy(false);
      setActionError(errorText(cause));
    }
  }

  async function refresh() {
    if (!selected) {
      return;
    }
    setBusy(true);
    setActionError('');
    setNotice('');
    try {
      setRun(
        await api.refreshSource(
          projectId,
          selected.collection_pipeline.id,
          selected.collection_pipeline.version_id,
        ),
      );
    } catch (cause) {
      setBusy(false);
      setActionError(errorText(cause));
    }
  }

  return (
    <div className="snapshot-browser" data-detail-open={selected ? 'true' : 'false'}>
      <section className="snapshot-catalog" aria-labelledby="snapshots-title">
        <header className="index-catalog-heading">
          <div>
            <h2 id="snapshots-title">Source snapshots</h2>
            <p>Immutable Website content collected for repeatable index builds.</p>
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setRevision((value) => value + 1)}
            aria-label="Refresh source snapshots"
          >
            <RefreshCw />
          </Button>
        </header>
        {loadError && (
          <div className="inline-error" role="alert">
            <span>{loadError}</span>
            <Button variant="outline" size="sm" onClick={() => setRevision((value) => value + 1)}>
              Retry
            </Button>
          </div>
        )}
        {!page && !loadError && (
          <p role="status" className="index-loading">
            <LoaderCircle /> Loading source snapshots…
          </p>
        )}
        {page?.total === 0 && (
          <div className="index-empty">
            <Globe2 />
            <h3>No Website snapshots yet</h3>
            <p>Run a saved Website ingestion pipeline to collect reusable source content.</p>
          </div>
        )}
        <div className="snapshot-groups">
          {groups.map(([origin, snapshots]) => (
            <section key={origin}>
              <h3>{origin}</h3>
              <ul>
                {snapshots.map((snapshot) => (
                  <li key={snapshot.id} data-state={selected?.id === snapshot.id ? 'selected' : ''}>
                    <button type="button" onClick={() => choose(snapshot)}>
                      <span className="index-version-title">
                        <strong>Snapshot {snapshot.snapshot_number}</strong>
                        <StatusBadge status={snapshot.status}>{statusLabel(snapshot)}</StatusBadge>
                      </span>
                      <span>
                        {snapshot.included_count.toLocaleString()} pages ·{' '}
                        {bytes(snapshot.total_bytes)}
                      </span>
                      <span>
                        {snapshot.downstream_index_count} index{' '}
                        {snapshot.downstream_index_count === 1 ? 'version' : 'versions'} ·{' '}
                        {date(snapshot.collected_at)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        {page && (
          <Pagination
            offset={offset}
            total={page.total}
            pageSize={page.limit}
            onChange={setOffset}
            label="Source snapshot pages"
          />
        )}
      </section>
      <section className="snapshot-detail index-detail" aria-label="Source snapshot details">
        {!selected ? (
          <div className="index-detail-empty">
            <Globe2 />
            <h2>Select a source snapshot</h2>
            <p>Inspect exact page membership and the indexes built from one collection.</p>
          </div>
        ) : (
          <>
            <Button variant="ghost" className="mobile-detail-back" onClick={() => choose()}>
              <ArrowLeft /> Back to source snapshots
            </Button>
            <header className="snapshot-detail-header">
              <div>
                <p>{selected.source_identity.origins?.join(', ') || 'Website source'}</p>
                <h2>Source snapshot {selected.snapshot_number}</h2>
                <span>Collected {date(selected.collected_at)}</span>
              </div>
              <StatusBadge status={selected.status}>{statusLabel(selected)}</StatusBadge>
            </header>
            <div className="snapshot-actions">
              <Button
                disabled={selected.status !== 'ready' || busy}
                onClick={() => setBuildOpen((value) => !value)}
                aria-expanded={buildOpen}
                aria-controls="snapshot-build-form"
              >
                <Database /> Build index variant
              </Button>
              <Button
                variant="outline"
                disabled={selected.status !== 'ready' || busy}
                onClick={() => void refresh()}
              >
                <RefreshCw /> Refresh source
              </Button>
            </div>
            {buildOpen && (
              <section id="snapshot-build-form" className="snapshot-build-form">
                <h3>Build another index</h3>
                <p>
                  Build another index from the content already collected. The website will not be
                  requested again. Embedding costs may still apply.
                </p>
                <div>
                  <Label htmlFor="snapshot-pipeline">Saved Website pipeline version</Label>
                  <NativeSelect
                    id="snapshot-pipeline"
                    value={pipelineVersionId}
                    onChange={(event) => setPipelineVersionId(event.target.value)}
                  >
                    <NativeSelectOption value="">Choose a saved version</NativeSelectOption>
                    {pipelines.map((version) => (
                      <NativeSelectOption key={version.id} value={version.id}>
                        {version.name} · Version {version.version}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </div>
                <dl className="snapshot-build-summary">
                  <div>
                    <dt>Chunk settings</dt>
                    <dd>{chunkSummary(selectedPipeline)}</dd>
                  </div>
                  <div>
                    <dt>Embedding</dt>
                    <dd>
                      {selectedPipeline?.execution.nodes.find((node) => node.type === 'embed')
                        ?.model || 'Configured by the saved version'}
                    </dd>
                  </div>
                </dl>
                <div>
                  <Label htmlFor="snapshot-destination-kind">Destination type</Label>
                  <NativeSelect
                    id="snapshot-destination-kind"
                    value={destinationKind}
                    onChange={(event) =>
                      setDestinationKind(event.target.value as 'new' | 'existing')
                    }
                  >
                    <NativeSelectOption value="new">New index</NativeSelectOption>
                    <NativeSelectOption value="existing">Existing index</NativeSelectOption>
                  </NativeSelect>
                </div>
                {destinationKind === 'new' ? (
                  <div>
                    <Label htmlFor="snapshot-index-name">Index name</Label>
                    <Input
                      id="snapshot-index-name"
                      value={destinationName}
                      maxLength={120}
                      onChange={(event) => setDestinationName(event.target.value)}
                      placeholder="Balanced website index"
                    />
                  </div>
                ) : (
                  <div>
                    <Label htmlFor="snapshot-index-destination">Existing index</Label>
                    <NativeSelect
                      id="snapshot-index-destination"
                      value={destinationId}
                      onChange={(event) => setDestinationId(event.target.value)}
                    >
                      <NativeSelectOption value="">Choose an index</NativeSelectOption>
                      {knowledgeSets.map((set) => (
                        <NativeSelectOption key={set.id} value={set.id}>
                          {set.name}
                        </NativeSelectOption>
                      ))}
                    </NativeSelect>
                  </div>
                )}
                <Button disabled={busy} onClick={() => void build()}>
                  {busy ? 'Starting build…' : 'Build from source snapshot'}
                </Button>
              </section>
            )}
            {run && ['queued', 'running'].includes(run.status) && (
              <div className="snapshot-run-progress" role="status">
                <span>
                  {run.stage === 'discovering' ? 'Reading snapshot' : run.stage} · {run.progress}%
                </span>
                <Progress value={run.progress} />
              </div>
            )}
            {actionError && (
              <p role="alert" className="error-message">
                {actionError}
              </p>
            )}
            {notice && (
              <p role="status" className="success-message">
                {notice}
              </p>
            )}
            {detailError && (
              <div role="alert" className="inline-error">
                <span>{detailError}</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setRevision((value) => value + 1)}
                >
                  Retry
                </Button>
              </div>
            )}
            <dl className="snapshot-counts">
              {[
                ['Included', selected.included_count],
                ['New', selected.new_count],
                ['Changed', selected.changed_count],
                ['Unchanged', selected.unchanged_count],
                ['Removed', selected.removed_count],
                ['Excluded', selected.excluded_count],
                ['Duplicates', selected.duplicate_count],
                ['Failed', selected.failed_count],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{Number(value).toLocaleString()}</dd>
                </div>
              ))}
            </dl>
            {selected.error && <p className="error-message">{selected.error}</p>}
            <section className="snapshot-section" aria-labelledby="snapshot-items-title">
              <div className="section-heading">
                <h3 id="snapshot-items-title">Included pages</h3>
                <span>{items?.total.toLocaleString() ?? '…'} exact revisions</span>
              </div>
              {!items && !detailError && <p role="status">Loading included pages…</p>}
              {items?.total === 0 && <p>No included page revisions are available.</p>}
              <ul className="snapshot-item-list">
                {items?.items.map((item) => (
                  <li key={item.source_revision_id}>
                    <FileText />
                    <div>
                      <strong>{item.canonical_location}</strong>
                      <dl>
                        <div>
                          <dt>Media type</dt>
                          <dd>{item.media_type}</dd>
                        </div>
                        <div>
                          <dt>Stored size</dt>
                          <dd>{bytes(item.size_bytes)}</dd>
                        </div>
                        <div>
                          <dt>Fetched</dt>
                          <dd>{date(item.fetched_at)}</dd>
                        </div>
                        {item.provider_revision && (
                          <div>
                            <dt>Provider revision</dt>
                            <dd>{item.provider_revision}</dd>
                          </div>
                        )}
                      </dl>
                    </div>
                  </li>
                ))}
              </ul>
              {items && (
                <Pagination
                  offset={itemOffset}
                  total={items.total}
                  pageSize={items.limit}
                  onChange={setItemOffset}
                  label="Snapshot item pages"
                />
              )}
            </section>
            <section className="snapshot-section" aria-labelledby="snapshot-indexes-title">
              <div className="section-heading">
                <h3 id="snapshot-indexes-title">Indexes built from this snapshot</h3>
                <span>{indexes?.total.toLocaleString() ?? '…'} versions</span>
              </div>
              {indexes?.total === 0 && <p>No index has been built from this snapshot yet.</p>}
              <ul className="snapshot-downstream-list">
                {indexes?.items.map((index) => (
                  <li key={index.id}>
                    <Database />
                    <div>
                      <strong>
                        {index.knowledge_set_name} · Version {index.version}
                      </strong>
                      <span>
                        {index.chunk_count.toLocaleString()} passages ·{' '}
                        {index.processing_summary
                          ? `${index.processing_summary.size.toLocaleString()} characters / ${index.processing_summary.overlap.toLocaleString()} overlap`
                          : 'Legacy processing settings unavailable'}
                      </span>
                    </div>
                    <Button variant="outline" size="sm" asChild>
                      <a
                        href={`#/projects/${projectId}/knowledge-base?view=indexes&mode=indexes&index=${index.id}`}
                      >
                        Open
                      </a>
                    </Button>
                  </li>
                ))}
              </ul>
              {indexes && (
                <Pagination
                  offset={indexOffset}
                  total={indexes.total}
                  pageSize={indexes.limit}
                  onChange={setIndexOffset}
                  label="Snapshot index pages"
                />
              )}
            </section>
          </>
        )}
      </section>
    </div>
  );
}
