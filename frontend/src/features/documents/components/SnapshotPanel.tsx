import { useEffect, useId, useMemo, useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowRight, ExternalLink, Globe2, RefreshCw } from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { RadioGroup, RadioGroupItem } from '../../../components/ui/radio-group';
import { EmptyState } from '../../../components/states/EmptyState';
import { LoadingState } from '../../../components/states/LoadingState';
import { cn } from '../../../lib/utils';
import { StatusBadge } from '../../../components/StatusBadge';
import { allPages } from '../../../lib/pagination';
import { docsHref } from '../../../lib/docs';
import * as ingestionApi from '../../ingestion-pipelines/api';
import type { IngestionPipelineVersion, IngestionRun } from '../../ingestion-pipelines/model';
import * as pipelineApi from '../../pipelines/api';
import * as api from '../indexApi';
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
  SectionHeading,
} from '../../../components/parts';
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
  const formId = useId();

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
    <section className="flex flex-col gap-6" aria-labelledby="snapshot-title">
      <header className="flex min-w-0 flex-col gap-1">
        <h2 id="snapshot-title" className="text-base font-semibold text-foreground">
          Source snapshots
        </h2>
        <p className="text-sm text-foreground-muted">
          Immutable connector collections that can feed independently configured indexes.
        </p>
        <a
          className={cn(LINK, 'self-start')}
          href={docsHref('ingestion/source-history')}
          target="_blank"
          rel="noopener noreferrer"
        >
          Snapshot reuse guide
        </a>
      </header>
      {error && (
        <InlineError onRetry={() => setRevision((value) => value + 1)}>{error}</InlineError>
      )}
      <div className="flex flex-col gap-6 desktop:flex-row desktop:items-start">
        <section
          className={cn(
            'flex min-w-0 flex-col desktop:w-panel desktop:shrink-0',
            selected && 'max-md:hidden',
          )}
          aria-label="Source snapshot catalog"
        >
          {loading ? (
            <LoadingState label="Loading source snapshots…" />
          ) : snapshots.length === 0 ? (
            <EmptyState
              icon={<Globe2 />}
              title="No source snapshots yet"
              headingLevel="h3"
              description="Run a remote-source ingestion pipeline to collect a reusable source snapshot."
              action={
                <Button variant="outline" asChild>
                  <a href={`#/projects/${projectId}/pipelines/new?kind=ingestion`}>
                    Open ingestion pipelines
                  </a>
                </Button>
              }
            />
          ) : (
            <ul className={LIST}>
              {snapshots.map((snapshot) => (
                <li key={snapshot.id} className={LIST_ROW}>
                  <Button
                    variant="ghost"
                    className={SELECT_ROW}
                    aria-pressed={selected?.id === snapshot.id}
                    onClick={() => select(snapshot)}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <strong className="truncate font-semibold">{origin(snapshot)}</strong>
                      <StatusBadge status={snapshot.status}>{snapshot.status}</StatusBadge>
                    </span>
                    <small className={META}>
                      Snapshot {snapshot.snapshot_number} · {formatDate(snapshot.collected_at)}
                    </small>
                    <small className={META}>
                      {snapshot.included_count} items · {snapshot.downstream_index_count} indexes
                    </small>
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section
          className={cn('flex min-w-0 flex-1 flex-col gap-6', !selected && 'max-md:hidden')}
          aria-label="Selected source snapshot details"
          data-testid="snapshot-detail"
        >
          {!selected ? (
            <EmptyState
              icon={<Globe2 />}
              title="Select a source snapshot"
              headingLevel="h2"
              description="Inspect captured items, collection state, and every derived index."
            />
          ) : (
            <>
              <Button className="self-start md:hidden" variant="ghost" onClick={() => select()}>
                <ArrowLeft aria-hidden="true" /> Back to snapshots
              </Button>
              <header className={cn(CARD, 'flex items-start justify-between gap-4 p-4')}>
                <div className="flex min-w-0 flex-col gap-1">
                  <p className={cn(META, 'wrap-anywhere')}>{origin(selected)}</p>
                  <h2 className="text-lg font-semibold text-foreground">
                    Snapshot {selected.snapshot_number}
                  </h2>
                  <small className={META}>{formatDate(selected.collected_at)}</small>
                </div>
                <StatusBadge status={selected.status}>{selected.status}</StatusBadge>
              </header>
              {selected.error && (
                <p className="text-sm text-danger wrap-anywhere">{selected.error}</p>
              )}
              <Facts
                className={cn(CARD, 'p-4 md:grid-cols-3')}
                items={[
                  ['Included items', selected.included_count],
                  ['Changed / new', `${selected.changed_count} / ${selected.new_count}`],
                  ['Failed', selected.failed_count],
                ]}
              />
              {selected.status === 'ready' && (
                <>
                  {currentReadyIndex && (
                    <Button asChild className="self-start max-md:w-full">
                      <a
                        href={`#/projects/${projectId}/pipelines/new?index=${currentReadyIndex.id}`}
                      >
                        Use current index in answer pipeline
                        <ArrowRight aria-hidden="true" />
                      </a>
                    </Button>
                  )}
                  <form className={cn(CARD, 'flex flex-col gap-4 p-4')} onSubmit={build}>
                    <div className="flex flex-col gap-1">
                      <h3 className="text-base font-semibold text-foreground">
                        Create an index variant from this snapshot
                      </h3>
                      <p className="text-sm text-foreground-muted">
                        This is optional. Reprocess this exact snapshot only when you need different
                        processing or embedding settings. The existing ready index remains
                        available, and the remote source will not be fetched again.
                      </p>
                    </div>
                    <div className="flex flex-col">
                      <Label htmlFor={`${formId}-version`}>Ingestion pipeline version</Label>
                      <NativeSelect
                        id={`${formId}-version`}
                        value={versionId}
                        onChange={(event) => setVersionId(event.target.value)}
                      >
                        {compatibleVersions.map((version) => (
                          <NativeSelectOption key={version.id} value={version.id}>
                            {version.name} · v{version.version}
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                    </div>
                    {chunk?.type === 'chunk' && (
                      <p className={META}>
                        {chunk.algorithm === 'section_token'
                          ? `Section-aware tokens · ${chunk.target_tokens} target · ${chunk.maximum_tokens} hard maximum · ${chunk.overlap_tokens} overlap`
                          : chunk.algorithm === 'parent_child'
                            ? `Parent/child · ${chunk.child_target_tokens}/${chunk.child_maximum_tokens} child · ${chunk.parent_target_tokens}/${chunk.parent_maximum_tokens} parent`
                            : `Character window · ${chunk.size} size · ${chunk.overlap} overlap`}
                        {embed?.type === 'embed' ? ` · ${embed.provider}/${embed.model}` : ''}
                      </p>
                    )}
                    <fieldset className="flex flex-col gap-2">
                      <legend className="mb-2 text-xs font-medium text-foreground-muted">
                        Destination
                      </legend>
                      <RadioGroup
                        value={destination}
                        onValueChange={(value) => setDestination(value as typeof destination)}
                        className="flex-row gap-6"
                      >
                        {(
                          [
                            ['new', 'New index'],
                            ['existing', 'Existing index'],
                          ] as const
                        ).map(([value, label]) => (
                          <label
                            key={value}
                            className="flex min-h-row items-center gap-2 text-sm text-foreground"
                          >
                            <RadioGroupItem value={value} />
                            {label}
                          </label>
                        ))}
                      </RadioGroup>
                    </fieldset>
                    {destination === 'new' ? (
                      <div className="flex flex-col">
                        <Label htmlFor={`${formId}-name`}>Index name</Label>
                        <Input
                          id={`${formId}-name`}
                          value={name}
                          onChange={(event) => setName(event.target.value)}
                          required
                        />
                      </div>
                    ) : (
                      <div className="flex flex-col">
                        <Label htmlFor={`${formId}-set`}>Existing index</Label>
                        <NativeSelect
                          id={`${formId}-set`}
                          value={setId}
                          onChange={(event) => setSetId(event.target.value)}
                        >
                          {sets.map((set) => (
                            <NativeSelectOption key={set.id} value={set.id}>
                              {set.name}
                            </NativeSelectOption>
                          ))}
                        </NativeSelect>
                      </div>
                    )}
                    <Button
                      type="submit"
                      variant="outline"
                      className="self-end max-md:w-full"
                      disabled={busy || !compatibleVersions.length}
                    >
                      Create index variant
                    </Button>
                  </form>
                </>
              )}
              {run &&
                (run.status === 'failed' ? (
                  <p role="status" className="text-sm text-danger wrap-anywhere">
                    Run {run.status}: {run.progress}% · {run.stage}
                    {run.error ? ` — ${run.error}` : ''}
                  </p>
                ) : (
                  <Notice>
                    Run {run.status}: {run.progress}% · {run.stage}
                    {run.error ? ` — ${run.error}` : ''}
                  </Notice>
                ))}
              <SectionHeading
                title="Derived indexes"
                action={
                  indexes.some((value) => value.ingestion_pipeline_version_id) && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void refreshSource()}
                      disabled={busy}
                    >
                      <RefreshCw aria-hidden="true" /> Refresh source
                    </Button>
                  )
                }
              />
              {indexes.length ? (
                <ul className={LIST}>
                  {indexes.map((index) => (
                    <li key={index.id} className={LIST_ROW}>
                      <a
                        className="flex min-h-row items-center gap-3 px-4 py-3 outline-none hover:bg-surface-hover focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
                        href={`#/projects/${projectId}/knowledge-base?view=indexes&mode=indexes&index=${index.id}`}
                      >
                        <span className="flex min-w-0 flex-1 flex-col gap-1">
                          <strong className="truncate text-sm font-semibold text-foreground">
                            {index.knowledge_set_name} · v{index.version}
                          </strong>
                          <small className={META}>
                            {index.ingestion_pipeline_name
                              ? `${index.ingestion_pipeline_name} · v${index.ingestion_pipeline_version}`
                              : 'Historical lineage unavailable'}
                          </small>
                        </span>
                        <StatusBadge status={index.status}>{index.status}</StatusBadge>
                        <ExternalLink
                          aria-hidden="true"
                          className="size-4 shrink-0 text-foreground-subtle"
                        />
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-foreground-muted">
                  No indexes have been built from this snapshot.
                </p>
              )}
              <h3 className="text-base font-semibold text-foreground">Captured items</h3>
              {items.length ? (
                <ul className={LIST}>
                  {items.map((item) => (
                    <li
                      key={`${item.ordinal}-${item.canonical_location}`}
                      className={cn(LIST_ROW, 'flex flex-col gap-1 px-4 py-3')}
                    >
                      <span className="text-sm text-foreground wrap-anywhere">
                        {item.canonical_location}
                      </span>
                      <small className={META}>
                        {item.media_type} · {item.size_bytes.toLocaleString()} bytes
                      </small>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-foreground-muted">No captured items are available.</p>
              )}
            </>
          )}
        </section>
      </div>
    </section>
  );
}
