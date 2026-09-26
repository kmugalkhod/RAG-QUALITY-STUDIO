import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowRight, ExternalLink, Globe2, RefreshCw } from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { StatusBadge } from '../../../components/StatusBadge';
import { allPages } from '../../../lib/pagination';
import { docsHref } from '../../../lib/docs';
import * as ingestionApi from '../../ingestion-pipelines/api';
import type { IngestionPipelineVersion, IngestionRun } from '../../ingestion-pipelines/model';
import * as pipelineApi from '../../pipelines/api';
import * as api from '../indexApi';
import type {
  KnowledgeSet,
  SourceSnapshot,
  SourceSnapshotIndex,
  SourceSnapshotMember,
} from '../model';

const message = (cause: unknown) =>
  cause instanceof Error ? cause.message : 'Request failed. Please try again.';
const formatDate = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
        new Date(value),
      )
    : 'In progress';
const sourceLabel = (kind: SourceSnapshot['source_kind']) =>
  ({ website: 'Website', s3: 'S3', notion: 'Notion', confluence: 'Confluence' })[kind];
const origin = (snapshot: SourceSnapshot) =>
  snapshot.source_identity.origins?.join(', ') ||
  snapshot.source_identity.buckets?.join(', ') ||
  `${sourceLabel(snapshot.source_kind)} source`;

export function SnapshotPanel({ projectId }: { projectId: string }) {
  const [snapshots, setSnapshots] = useState<SourceSnapshot[]>([]);
  const [selected, setSelected] = useState<SourceSnapshot>();
  const [items, setItems] = useState<SourceSnapshotMember[]>([]);
  const [indexes, setIndexes] = useState<SourceSnapshotIndex[]>([]);
  const [versions, setVersions] = useState<IngestionPipelineVersion[]>([]);
  const [sets, setSets] = useState<KnowledgeSet[]>([]);
  const [versionId, setVersionId] = useState('');
  const [destination, setDestination] = useState<'new' | 'existing'>('new');
  const [name, setName] = useState('Source index variant');
  const [setId, setSetId] = useState('');
  const [run, setRun] = useState<IngestionRun>();
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const selectedId = selected?.id;

  useEffect(() => {
    let disposed = false;
    let request = 0;
    const restoreSelection = () => {
      const sequence = ++request;
      const linkedId = new URLSearchParams(window.location.hash.split('?')[1]).get('snapshot');
      if (!linkedId) {
        setSelected(undefined);
        return;
      }
      if (linkedId === selectedId) {
        return;
      }
      void api
        .getSourceSnapshot(projectId, linkedId)
        .then((snapshot) => {
          if (!disposed && sequence === request) {
            setSelected(snapshot);
            setError('');
          }
        })
        .catch((cause) => {
          if (!disposed && sequence === request) {
            setSelected(undefined);
            setError(`That source snapshot is unavailable. ${message(cause)}`);
          }
        });
    };
    restoreSelection();
    window.addEventListener('hashchange', restoreSelection);
    window.addEventListener('popstate', restoreSelection);
    return () => {
      disposed = true;
      window.removeEventListener('hashchange', restoreSelection);
      window.removeEventListener('popstate', restoreSelection);
    };
  }, [projectId, selectedId]);

  useEffect(() => {
    let disposed = false;
    Promise.all([
      allPages((offset) => api.listSourceSnapshots(projectId, offset)),
      allPages((offset) => api.listKnowledgeSets(projectId, offset)),
      allPages((offset) => pipelineApi.listPipelines(projectId, 'ingestion', offset)),
    ])
      .then(async ([values, knowledgeSets, pipelines]) => {
        const pipelineVersions = (
          await Promise.all(
            pipelines.map((pipeline) =>
              allPages((offset) =>
                ingestionApi.listIngestionPipelineVersions(projectId, pipeline.id, offset),
              ),
            ),
          )
        ).flat();
        if (disposed) {
          return;
        }
        setSnapshots(values);
        setSets(knowledgeSets);
        const remoteVersions = pipelineVersions.filter((version) =>
          version.execution.nodes.some(
            (node) => node.type === 'source' && node.config.kind !== 'existing_files',
          ),
        );
        setVersions(remoteVersions);
        setSetId((current) => current || knowledgeSets[0]?.id || '');
        const linked = new URLSearchParams(window.location.hash.split('?')[1]).get('snapshot');
        setSelected((current) => current ?? values.find((value) => value.id === linked));
        setError('');
      })
      .catch((cause) => !disposed && setError(message(cause)))
      .finally(() => !disposed && setLoading(false));
    return () => {
      disposed = true;
    };
  }, [projectId, revision]);

  useEffect(() => {
    if (!selected) {
      setItems([]);
      setIndexes([]);
      return;
    }
    let disposed = false;
    Promise.all([
      allPages((offset) => api.listSourceSnapshotItems(projectId, selected.id, offset)),
      allPages((offset) => api.listSourceSnapshotIndexes(projectId, selected.id, offset)),
    ])
      .then(([members, downstream]) => {
        if (!disposed) {
          setItems(members);
          setIndexes(downstream);
        }
      })
      .catch((cause) => !disposed && setError(message(cause)));
    return () => {
      disposed = true;
    };
  }, [projectId, selected, revision]);

  useEffect(() => {
    if (!run || !['queued', 'running'].includes(run.status)) {
      return;
    }
    const timer = window.setTimeout(
      () =>
        ingestionApi
          .getIngestionRun(projectId, run.id)
          .then((value) => {
            setRun(value);
            if (value.status === 'succeeded') {
              setRevision((current) => current + 1);
            }
          })
          .catch((cause) => setError(message(cause))),
      1500,
    );
    return () => window.clearTimeout(timer);
  }, [projectId, run]);

  const compatibleVersions = useMemo(
    () =>
      versions.filter((version) =>
        version.execution.nodes.some(
          (node) => node.type === 'source' && selected && node.config.kind === selected.source_kind,
        ),
      ),
    [selected, versions],
  );
  useEffect(() => {
    setVersionId((current) =>
      compatibleVersions.some((version) => version.id === current)
        ? current
        : compatibleVersions[0]?.id || '',
    );
  }, [compatibleVersions]);
  const chosenVersion = useMemo(
    () => compatibleVersions.find((value) => value.id === versionId),
    [compatibleVersions, versionId],
  );
  const chunk = chosenVersion?.execution.nodes.find((node) => node.type === 'chunk');
  const embed = chosenVersion?.execution.nodes.find((node) => node.type === 'embed');
  const currentReadyIndex = indexes.find(
    (index) => index.is_current && index.status === 'succeeded',
  );

  function select(snapshot?: SourceSnapshot) {
    setSelected(snapshot);
    const [rawPath] = window.location.hash.split('?');
    const path = rawPath.replace(/^#+/, '');
    const params = new URLSearchParams({ view: 'indexes', mode: 'snapshots' });
    if (snapshot) {
      params.set('snapshot', snapshot.id);
    }
    window.history.pushState(null, '', `#${path}?${params}`);
  }

  async function build(event: FormEvent) {
    event.preventDefault();
    if (!selected || !chosenVersion || (destination === 'new' ? !name.trim() : !setId)) {
      return;
    }
    setBusy(true);
    setError('');
    try {
      setRun(
        await ingestionApi.startIngestionRun(
          projectId,
          chosenVersion.pipeline_id,
          chosenVersion.id,
          {
            source_input: { kind: 'snapshot', source_snapshot_id: selected.id },
            destination:
              destination === 'new'
                ? { kind: 'new', name: name.trim() }
                : { kind: 'existing', knowledge_set_id: setId },
          },
        ),
      );
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  async function refreshSource() {
    const lineage = indexes.find(
      (value) => value.ingestion_pipeline_id && value.ingestion_pipeline_version_id,
    );
    if (!lineage?.ingestion_pipeline_id || !lineage.ingestion_pipeline_version_id) {
      return;
    }
    setBusy(true);
    setError('');
    try {
      setRun(
        await ingestionApi.startIngestionRun(
          projectId,
          lineage.ingestion_pipeline_id,
          lineage.ingestion_pipeline_version_id,
          { source_input: { kind: 'refresh' } },
        ),
      );
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className={`snapshot-workspace ${selected ? 'has-selection' : ''}`}
      aria-labelledby="snapshot-title"
    >
      <header className="index-workspace-header">
        <div>
          <h2 id="snapshot-title">Source snapshots</h2>
          <p>Immutable connector collections that can feed independently configured indexes.</p>
          <a href={docsHref('ingestion/source-history')} target="_blank" rel="noopener noreferrer">
            Snapshot reuse guide
          </a>
        </div>
      </header>
      {error && (
        <p role="alert" className="error-message">
          {error}{' '}
          <Button variant="outline" size="sm" onClick={() => setRevision((value) => value + 1)}>
            Retry
          </Button>
        </p>
      )}
      <div className="snapshot-browser-layout">
        <section className="snapshot-catalog" aria-label="Source snapshot catalog">
          {loading ? (
            <p role="status">Loading source snapshots…</p>
          ) : snapshots.length === 0 ? (
            <div className="index-detail-empty">
              <Globe2 />
              <h3>No source snapshots yet</h3>
              <p>Run a remote-source ingestion pipeline to collect a reusable source snapshot.</p>
              <Button asChild>
                <a href={`#/projects/${projectId}/pipelines/new?kind=ingestion`}>
                  Open ingestion pipelines
                </a>
              </Button>
            </div>
          ) : (
            snapshots.map((snapshot) => (
              <button
                key={snapshot.id}
                type="button"
                className={
                  selected?.id === snapshot.id ? 'snapshot-row is-selected' : 'snapshot-row'
                }
                onClick={() => select(snapshot)}
              >
                <span>
                  <strong>{origin(snapshot)}</strong>
                  <small>
                    Snapshot {snapshot.snapshot_number} · {formatDate(snapshot.collected_at)}
                  </small>
                </span>
                <span>
                  <StatusBadge status={snapshot.status}>{snapshot.status}</StatusBadge>
                  <small>
                    {snapshot.included_count} items · {snapshot.downstream_index_count} indexes
                  </small>
                </span>
              </button>
            ))
          )}
        </section>
        <section className="snapshot-detail" aria-label="Selected source snapshot details">
          {!selected ? (
            <div className="index-detail-empty">
              <Globe2 />
              <h2>Select a source snapshot</h2>
              <p>Inspect captured items, collection state, and every derived index.</p>
            </div>
          ) : (
            <>
              <Button className="snapshot-back" variant="ghost" onClick={() => select()}>
                <ArrowLeft /> Back to snapshots
              </Button>
              <header className="index-detail-header">
                <div>
                  <p>{origin(selected)}</p>
                  <h2>Snapshot {selected.snapshot_number}</h2>
                  <small>{formatDate(selected.collected_at)}</small>
                </div>
                <StatusBadge status={selected.status}>{selected.status}</StatusBadge>
              </header>
              {selected.error && <p className="error-message">{selected.error}</p>}
              <dl className="index-detail-stats">
                <div>
                  <dt>Included items</dt>
                  <dd>{selected.included_count}</dd>
                </div>
                <div>
                  <dt>Changed / new</dt>
                  <dd>
                    {selected.changed_count} / {selected.new_count}
                  </dd>
                </div>
                <div>
                  <dt>Failed</dt>
                  <dd>{selected.failed_count}</dd>
                </div>
              </dl>
              {selected.status === 'ready' && (
                <>
                  {currentReadyIndex && (
                    <div className="snapshot-actions">
                      <Button asChild>
                        <a
                          href={`#/projects/${projectId}/pipelines/new?index=${currentReadyIndex.id}`}
                        >
                          Use current index in answer pipeline
                          <ArrowRight aria-hidden="true" />
                        </a>
                      </Button>
                    </div>
                  )}
                  <form className="snapshot-build-form" onSubmit={build}>
                    <h3>Create an index variant from this snapshot</h3>
                    <p>
                      This is optional. Reprocess this exact snapshot only when you need different
                      processing or embedding settings. The existing ready index remains available,
                      and the remote source will not be fetched again.
                    </p>
                    <label>
                      Ingestion pipeline version
                      <select
                        value={versionId}
                        onChange={(event) => setVersionId(event.target.value)}
                      >
                        {compatibleVersions.map((version) => (
                          <option key={version.id} value={version.id}>
                            {version.name} · v{version.version}
                          </option>
                        ))}
                      </select>
                    </label>
                    {chunk?.type === 'chunk' && (
                      <p className="muted">
                        {chunk.algorithm === 'section_token'
                          ? `Section-aware tokens · ${chunk.target_tokens} target · ${chunk.maximum_tokens} hard maximum · ${chunk.overlap_tokens} overlap`
                          : chunk.algorithm === 'parent_child'
                            ? `Parent/child · ${chunk.child_target_tokens}/${chunk.child_maximum_tokens} child · ${chunk.parent_target_tokens}/${chunk.parent_maximum_tokens} parent`
                            : `Character window · ${chunk.size} size · ${chunk.overlap} overlap`}
                        {embed?.type === 'embed' ? ` · ${embed.provider}/${embed.model}` : ''}
                      </p>
                    )}
                    <fieldset>
                      <legend>Destination</legend>
                      <label>
                        <input
                          type="radio"
                          checked={destination === 'new'}
                          onChange={() => setDestination('new')}
                        />{' '}
                        New index
                      </label>
                      <label>
                        <input
                          type="radio"
                          checked={destination === 'existing'}
                          onChange={() => setDestination('existing')}
                        />{' '}
                        Existing index
                      </label>
                    </fieldset>
                    {destination === 'new' ? (
                      <label>
                        Index name
                        <Input
                          value={name}
                          onChange={(event) => setName(event.target.value)}
                          required
                        />
                      </label>
                    ) : (
                      <label>
                        Existing index
                        <select value={setId} onChange={(event) => setSetId(event.target.value)}>
                          {sets.map((set) => (
                            <option key={set.id} value={set.id}>
                              {set.name}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}
                    <Button type="submit" disabled={busy || !compatibleVersions.length}>
                      Create index variant
                    </Button>
                  </form>
                </>
              )}
              {run && (
                <p
                  role="status"
                  className={run.status === 'failed' ? 'error-message' : 'success-message'}
                >
                  Run {run.status}: {run.progress}% · {run.stage}
                  {run.error ? ` — ${run.error}` : ''}
                </p>
              )}
              <div className="snapshot-section-heading">
                <h3>Derived indexes</h3>
                {indexes.some((value) => value.ingestion_pipeline_version_id) && (
                  <Button variant="outline" onClick={() => void refreshSource()} disabled={busy}>
                    <RefreshCw /> Refresh source
                  </Button>
                )}
              </div>
              {indexes.length ? (
                <div className="snapshot-indexes">
                  {indexes.map((index) => (
                    <a
                      key={index.id}
                      href={`#/projects/${projectId}/knowledge-base?view=indexes&mode=indexes&index=${index.id}`}
                    >
                      <span>
                        <strong>
                          {index.knowledge_set_name} · v{index.version}
                        </strong>
                        <small>
                          {index.ingestion_pipeline_name
                            ? `${index.ingestion_pipeline_name} · v${index.ingestion_pipeline_version}`
                            : 'Historical lineage unavailable'}
                        </small>
                      </span>
                      <StatusBadge status={index.status}>{index.status}</StatusBadge>
                      <ExternalLink />
                    </a>
                  ))}
                </div>
              ) : (
                <p className="muted">No indexes have been built from this snapshot.</p>
              )}
              <h3>Captured items</h3>
              {items.length ? (
                <div className="snapshot-items">
                  {items.map((item) => (
                    <div key={`${item.ordinal}-${item.canonical_location}`}>
                      <span>{item.canonical_location}</span>
                      <small>
                        {item.media_type} · {item.size_bytes.toLocaleString()} bytes
                      </small>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted">No captured items are available.</p>
              )}
            </>
          )}
        </section>
      </div>
    </section>
  );
}
