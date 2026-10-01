import { useEffect, useState } from 'react';
import { ArrowRight, Plus, Workflow } from 'lucide-react';

import { LIST, LIST_ROW } from '../../components/parts';
import { PageHeader } from '../../components/PageHeader';
import { EmptyState } from '../../components/states/EmptyState';
import { ErrorState } from '../../components/states/ErrorState';
import { LoadingState } from '../../components/states/LoadingState';
import { StatusBadge } from '../../components/StatusBadge';
import { Button } from '../../components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { allPages } from '../../lib/pagination';
import { cn } from '../../lib/utils';
import { listIngestionPipelineVersions } from '../ingestion-pipelines/api';
import * as api from './api';
import { type Pipeline, type PipelineKind, validatePipelineExecution } from './model';

type PipelineMetadata = {
  version: number;
  updatedAt: string;
  ready: boolean;
};

function normalizedKind(value: string): PipelineKind {
  return value === 'ingestion' ? 'ingestion' : 'answer';
}

export function PipelinesPage({
  projectId,
  kind: requestedKind,
}: {
  projectId: string;
  kind: string;
}) {
  const kind = normalizedKind(requestedKind);
  const [pipelines, setPipelines] = useState<Pipeline[]>();
  const [metadata, setMetadata] = useState<Record<string, PipelineMetadata>>({});
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let disposed = false;
    setPipelines(undefined);
    setMetadata({});
    void allPages((offset) => api.listPipelines(projectId, kind, offset))
      .then(async (items) => {
        if (!disposed) {
          setPipelines(items);
          setError('');
        }
        const entries = await Promise.all(
          items.map(async (pipeline): Promise<[string, PipelineMetadata | undefined]> => {
            try {
              if (kind === 'answer') {
                const versions = await allPages((offset) =>
                  api.listPipelineVersions(projectId, pipeline.id, offset),
                );
                const latest = versions.sort((a, b) => b.version - a.version)[0];
                if (!latest) {
                  return [pipeline.id, undefined];
                }
                return [
                  pipeline.id,
                  {
                    version: latest.version,
                    updatedAt: latest.created_at,
                    ready: validatePipelineExecution(latest.execution).length === 0,
                  },
                ];
              }
              const versions = await allPages((offset) =>
                listIngestionPipelineVersions(projectId, pipeline.id, offset),
              );
              const latest = versions.sort((a, b) => b.version - a.version)[0];
              return [
                pipeline.id,
                latest
                  ? { version: latest.version, updatedAt: latest.created_at, ready: true }
                  : undefined,
              ];
            } catch {
              return [pipeline.id, undefined];
            }
          }),
        );
        if (!disposed) {
          setMetadata(
            Object.fromEntries(
              entries.filter((entry): entry is [string, PipelineMetadata] => !!entry[1]),
            ),
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
  }, [kind, projectId, revision]);

  const isAnswer = kind === 'answer';
  const collection = error ? (
    <ErrorState
      title={`We couldn’t load ${kind} pipelines`}
      message={error}
      onRetry={() => setRevision((value) => value + 1)}
    />
  ) : !pipelines ? (
    <LoadingState label={`Loading ${kind} pipelines…`} />
  ) : !pipelines.length ? (
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
    <ul className={LIST}>
      {pipelines.map((pipeline) => {
        const details = metadata[pipeline.id];
        return (
          <li
            key={pipeline.id}
            className={cn(
              LIST_ROW,
              'flex min-h-row flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:gap-4',
            )}
          >
            <div className="flex min-w-0 flex-1 items-start gap-3">
              <Workflow
                aria-hidden="true"
                className="mt-1 size-4 shrink-0 text-foreground-subtle"
              />
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-semibold text-foreground wrap-anywhere">
                    {pipeline.name}
                  </h2>
                  {details && (
                    <StatusBadge status={details.ready ? 'configured' : 'uploaded'}>
                      {details.ready
                        ? isAnswer
                          ? 'Ready to test'
                          : 'Ready to run'
                        : 'Needs setup'}
                    </StatusBadge>
                  )}
                </div>
                <p className="text-xs text-foreground-muted tabular-nums">
                  {details
                    ? `Version ${details.version} · updated ${new Date(details.updatedAt).toLocaleDateString()}`
                    : isAnswer
                      ? 'No saved version details available'
                      : 'Saved ingestion configuration'}
                </p>
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
        );
      })}
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
          <Button asChild>
            <a href={`#/projects/${projectId}/pipelines/new${isAnswer ? '' : '?kind=ingestion'}`}>
              <Plus aria-hidden="true" />
              {isAnswer ? 'New answer pipeline' : 'New ingestion pipeline'}
            </a>
          </Button>
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
          className="pt-6 outline-none"
        >
          {collection}
        </div>
      </Tabs>
    </div>
  );
}
