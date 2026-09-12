import { useEffect, useState } from 'react';
import { Plus, Workflow } from 'lucide-react';

import { Button } from '../../components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { allPages } from '../../lib/pagination';
import * as api from './api';
import { type Pipeline, type PipelineKind } from './model';

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
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let disposed = false;
    setPipelines(undefined);
    void allPages((offset) => api.listPipelines(projectId, kind, offset))
      .then((items) => {
        if (!disposed) {
          setPipelines(items);
          setError('');
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
    <div role="alert" className="flex items-center gap-3">
      <p>{error}</p>
      <Button variant="outline" onClick={() => setRevision((value) => value + 1)}>
        Retry
      </Button>
    </div>
  ) : !pipelines ? (
    <p role="status">Loading {kind} pipelines…</p>
  ) : !pipelines.length ? (
    <div className="empty-state border-0 border-border px-6 py-17.5 text-center text-muted-foreground">
      <h2>{isAnswer ? 'Build your first answer pipeline' : 'No ingestion pipelines yet'}</h2>
      <p>
        {isAnswer
          ? 'Create a pipeline, choose the documents to search, and save a version to test in Playground.'
          : 'Build a source-to-index workflow from explicitly selected, processed project files.'}
      </p>
    </div>
  ) : (
    <ul className="project-list pipeline-list m-0 mt-0 list-none border-t border-border p-0">
      {pipelines.map((pipeline) => (
        <li key={pipeline.id}>
          <Workflow className="list-symbol" size={20} />
          <div className="project-content min-w-0 flex-1 wrap-anywhere">
            <h2>{pipeline.name}</h2>
            <p>
              {isAnswer
                ? 'Versioned question → retrieval → answer pipeline'
                : 'Versioned existing-files → ready index pipeline'}
            </p>
          </div>
          <Button variant="outline" asChild>
            <a
              href={`#/projects/${projectId}/pipelines/${pipeline.id}${isAnswer ? '' : '?kind=ingestion'}`}
            >
              Open<span className="sr-only"> {pipeline.name}</span>
            </a>
          </Button>
        </li>
      ))}
    </ul>
  );
  return (
    <>
      <div className="page-heading mb-7 flex items-center justify-between gap-5">
        <div>
          <h1>Pipelines</h1>
          <p>
            {isAnswer
              ? 'Saved configurations for answering questions with evidence.'
              : 'Saved configurations for acquiring and indexing project knowledge.'}
          </p>
        </div>
        {isAnswer ? (
          <Button asChild>
            <a href={`#/projects/${projectId}/pipelines/new`}>
              <Plus size={14} />
              New answer pipeline
            </a>
          </Button>
        ) : (
          <Button asChild>
            <a href={`#/projects/${projectId}/pipelines/new?kind=ingestion`}>
              <Plus size={14} />
              New ingestion pipeline
            </a>
          </Button>
        )}
      </div>
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
          className="pt-5 outline-none"
        >
          {collection}
        </div>
      </Tabs>
    </>
  );
}
