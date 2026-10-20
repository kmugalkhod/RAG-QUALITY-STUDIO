import { useEffect, useState } from 'react';
import { ArrowRight, Globe, Plus, Search, Workflow } from 'lucide-react';

import { LIST, LIST_ROW, META } from '../../components/parts';
import { PageHeader } from '../../components/PageHeader';
import { Pagination } from '../../components/Pagination';
import { EmptyState } from '../../components/states/EmptyState';
import { ErrorState } from '../../components/states/ErrorState';
import { LoadingState } from '../../components/states/LoadingState';
import { StatusBadge } from '../../components/StatusBadge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../components/ui/native-select';
import { Tabs, TabsList, TabsTrigger } from '../../components/ui/tabs';
import type { Page } from '../../lib/pagination';
import { allPages } from '../../lib/pagination';
import { cn } from '../../lib/utils';
import * as api from './api';
import {
  type Pipeline,
  type PipelineKind,
  type PipelineLastRun,
  type PipelineOutcome,
  validatePipelineExecution,
} from './model';

function normalizedKind(value: string): PipelineKind {
  return value === 'ingestion' ? 'ingestion' : 'answer';
}

const outcomes: { value: PipelineOutcome | ''; label: string }[] = [
  { value: '', label: 'All' },
  { value: 'complete', label: 'Complete' },
  { value: 'failed', label: 'Failed' },
  { value: 'running', label: 'Running' },
  { value: 'never_run', label: 'Never run' },
];

const when = (value: string) =>
  new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

/** The last run's outcome as a badge: status and its own words. */
function runBadge(run: PipelineLastRun | null | undefined) {
  if (!run) {
    return <StatusBadge status="uploaded">Never run</StatusBadge>;
  }
  if (run.status === 'succeeded') {
    return (
      <StatusBadge status="succeeded">
        {run.completion === 'with_warnings' ? 'Complete with warnings' : 'Complete'}
      </StatusBadge>
    );
  }
  const label = {
    queued: 'Queued',
    running: 'Running',
    failed: 'Failed',
    cancelled: 'Cancelled',
  }[run.status];
  return <StatusBadge status={run.status}>{label}</StatusBadge>;
}

function ingestionDetails(pipeline: Pipeline) {
  const run = pipeline.last_run;
  const index = pipeline.published_index;
  return (
    <>
      <p className={cn(META, 'tabular-nums')}>
        {pipeline.latest_version ? `Version ${pipeline.latest_version.version}` : 'No version'}
        {run
          ? ` · last run ${when(run.finished_at ?? run.created_at)} (version ${run.pipeline_version})`
          : ''}
      </p>
      <p className={cn(META, 'wrap-anywhere')}>
        {index
          ? `Index ${index.knowledge_set_name} · version ${index.version}${index.is_current ? ' · current' : ''}`
          : 'No published index'}
      </p>
    </>
  );
}

export function PipelinesPage({
  projectId,
  kind: requestedKind,
}: {
  projectId: string;
  kind: string;
}) {
  const kind = normalizedKind(requestedKind);
  const isAnswer = kind === 'answer';
  const [page, setPage] = useState<Page<Pipeline>>();
  const [ready, setReady] = useState<Record<string, boolean>>({});
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [outcome, setOutcome] = useState<PipelineOutcome | ''>('');
  const [offset, setOffset] = useState(0);

  // Typing settles before a request; a new search or filter starts at page one.
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);
  useEffect(() => setOffset(0), [query, outcome, kind, projectId]);
  useEffect(() => {
    setSearch('');
    setQuery('');
    setOutcome('');
  }, [kind, projectId]);

  useEffect(() => {
    let disposed = false;
    setPage(undefined);
    setReady({});
    void api
      .listPipelinePage(projectId, kind, {
        offset,
        q: query,
        outcome: isAnswer ? undefined : outcome || undefined,
      })
      .then(async (value) => {
        if (disposed) {
          return;
        }
        setPage(value);
        setError('');
        if (!isAnswer) {
          return;
        }
        // Answer rows say whether their latest version is ready to test.
        const entries = await Promise.all(
          value.items.map(async (pipeline): Promise<[string, boolean] | undefined> => {
            try {
              const versions = await allPages((at) =>
                api.listPipelineVersions(projectId, pipeline.id, at),
              );
              const latest = versions.sort((a, b) => b.version - a.version)[0];
              return latest
                ? [pipeline.id, validatePipelineExecution(latest.execution).length === 0]
                : undefined;
            } catch {
              return undefined;
            }
          }),
        );
        if (!disposed) {
          setReady(
            Object.fromEntries(entries.filter((entry): entry is [string, boolean] => !!entry)),
          );
        }
      })
      .catch((cause) => {
        if (!disposed) {
          setError((cause as Error).message);
        }
      });
    return () => {
      disposed = true;
    };
  }, [kind, isAnswer, projectId, revision, offset, query, outcome]);

  const filtered = !!query || (!isAnswer && !!outcome);
  const clear = () => {
    setSearch('');
    setQuery('');
    setOutcome('');
  };
  const filters = (
    <div className="flex flex-wrap items-end gap-3 max-md:flex-col max-md:items-stretch">
      <Label className="mb-0 min-w-0 flex-1 md:max-w-panel">
        Search pipelines
        <span className="relative mt-2 block">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2 text-foreground-subtle"
          />
          <Input
            type="search"
            className="pl-8"
            placeholder="Pipeline name"
            value={search}
            maxLength={120}
            onChange={(event) => setSearch(event.target.value)}
          />
        </span>
      </Label>
      {!isAnswer && (
        <Label className="mb-0">
          Last run
          <NativeSelect
            className="mt-2"
            value={outcome}
            onChange={(event) => setOutcome(event.target.value as PipelineOutcome | '')}
          >
            {outcomes.map((option) => (
              <NativeSelectOption key={option.value} value={option.value}>
                {option.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Label>
      )}
    </div>
  );
  const collection = error ? (
    <ErrorState
      title={`We couldn’t load ${kind} pipelines`}
      message={error}
      onRetry={() => setRevision((value) => value + 1)}
    />
  ) : !page ? (
    <LoadingState label={`Loading ${kind} pipelines…`} />
  ) : !page.items.length && filtered ? (
    <EmptyState
      icon={<Search />}
      headingLevel="h2"
      title="No pipelines match"
      description="Change the search or the last-run filter."
      action={
        <Button variant="outline" onClick={clear}>
          Clear search and filter
        </Button>
      }
    />
  ) : !page.items.length ? (
    <EmptyState
      icon={<Workflow />}
      headingLevel="h2"
      title={isAnswer ? 'Build your first answer pipeline' : 'No ingestion pipelines yet'}
      description={
        isAnswer
          ? 'Create a pipeline, choose the documents to search, and save a version to test in Playground.'
          : 'Build a source-to-index workflow from explicitly selected, processed project files.'
      }
    />
  ) : (
    <ul className={LIST} aria-label={isAnswer ? 'Answer pipelines' : 'Ingestion pipelines'}>
      {page.items.map((pipeline) => (
        <li
          key={pipeline.id}
          className={cn(
            LIST_ROW,
            'flex min-h-row flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:gap-4',
          )}
        >
          <div className="flex min-w-0 flex-1 items-start gap-3">
            <Workflow aria-hidden="true" className="mt-1 size-4 shrink-0 text-foreground-subtle" />
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-sm font-medium text-foreground wrap-anywhere">
                  {pipeline.name}
                </h2>
                {isAnswer
                  ? pipeline.id in ready && (
                      <StatusBadge status={ready[pipeline.id] ? 'configured' : 'uploaded'}>
                        {ready[pipeline.id] ? 'Ready to test' : 'Needs setup'}
                      </StatusBadge>
                    )
                  : runBadge(pipeline.last_run)}
              </div>
              {isAnswer ? (
                <p className={cn(META, 'tabular-nums')}>
                  {pipeline.latest_version
                    ? `Version ${pipeline.latest_version.version} · updated ${new Date(pipeline.latest_version.created_at).toLocaleDateString()}`
                    : 'No saved version details available'}
                </p>
              ) : (
                ingestionDetails(pipeline)
              )}
            </div>
          </div>
          <Button variant="outline" size="sm" className="self-start md:self-auto" asChild>
            <a
              href={`#/projects/${projectId}/pipelines/${pipeline.id}${isAnswer ? '' : '?kind=ingestion'}`}
            >
              Open<span className="sr-only"> {pipeline.name}</span>
              <ArrowRight aria-hidden="true" />
            </a>
          </Button>
        </li>
      ))}
    </ul>
  );
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Pipelines"
        meta={
          isAnswer
            ? 'Saved configurations for answering questions with evidence.'
            : 'Saved configurations for acquiring and indexing project knowledge.'
        }
        action={
          <div className="flex flex-wrap gap-2 max-md:flex-col max-md:*:w-full">
            {!isAnswer && (
              <Button variant="outline" asChild>
                <a href={`#/projects/${projectId}/pipelines/setup?kind=ingestion`}>
                  <Globe aria-hidden="true" />
                  Guided setup
                </a>
              </Button>
            )}
            <Button asChild>
              <a href={`#/projects/${projectId}/pipelines/new${isAnswer ? '' : '?kind=ingestion'}`}>
                <Plus aria-hidden="true" />
                {isAnswer ? 'New answer pipeline' : 'New ingestion pipeline'}
              </a>
            </Button>
          </div>
        }
      />
      <Tabs
        key={kind}
        value={kind}
        onValueChange={(value) => {
          window.location.hash = `/projects/${projectId}/pipelines?kind=${normalizedKind(value)}`;
        }}
      >
        <TabsList variant="line" aria-label="Pipeline kind">
          <TabsTrigger id="answer-pipelines-tab" aria-controls="pipeline-kind-panel" value="answer">
            Answer pipelines
          </TabsTrigger>
          <TabsTrigger
            id="ingestion-pipelines-tab"
            aria-controls="pipeline-kind-panel"
            value="ingestion"
          >
            Ingestion pipelines
          </TabsTrigger>
        </TabsList>
        <div
          id="pipeline-kind-panel"
          role="tabpanel"
          aria-labelledby={`${kind}-pipelines-tab`}
          className="flex flex-col gap-4 pt-6 outline-none"
        >
          {filters}
          {collection}
          {page && page.total > page.limit && (
            <Pagination
              offset={offset}
              total={page.total}
              pageSize={page.limit}
              onChange={setOffset}
              label="Pipeline pages"
            />
          )}
          {page && page.total > 0 && (
            <p className={META} role="status">
              {page.total} {page.total === 1 ? 'pipeline' : 'pipelines'}
              {filtered ? ' match' : ''} · newest first
            </p>
          )}
        </div>
      </Tabs>
    </div>
  );
}
