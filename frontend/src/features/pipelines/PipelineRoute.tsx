import { Component, lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import { Button } from '../../components/ui/button';
import { EmptyState } from '../../components/states/EmptyState';
import { ErrorState } from '../../components/states/ErrorState';
import { LoadingState } from '../../components/states/LoadingState';
import { ApiError } from '../../lib/api';
import { getPipeline } from './api';
import type { PipelineKind } from './model';

const IngestionPipelineEditor = lazy(() =>
  import('../ingestion-pipelines/IngestionPipelineEditor').then((module) => ({
    default: module.IngestionPipelineEditor,
  })),
);
const PipelineEditor = lazy(() =>
  import('./PipelineEditor').then((module) => ({ default: module.PipelineEditor })),
);

type Props = {
  projectId: string;
  pipelineId: string;
  versionId: string;
  // The kind the link names; a saved pipeline opens by its own kind (spec 0015 U3).
  linkedKind: string | null;
};

type Loaded =
  | { state: 'loading' }
  | { state: 'ready'; kind: PipelineKind }
  | { state: 'missing' }
  | { state: 'error'; message: string };

function listHref(projectId: string, kind: string | null) {
  return `#/projects/${projectId}/pipelines${kind === 'ingestion' ? '?kind=ingestion' : ''}`;
}

/** The link for a saved pipeline in its own editor, keeping the linked version. */
export function pipelineHref(
  projectId: string,
  pipelineId: string,
  kind: PipelineKind,
  versionId: string,
) {
  const query = new URLSearchParams();
  if (kind === 'ingestion') {
    query.set('kind', 'ingestion');
  }
  if (versionId) {
    query.set('version', versionId);
  }
  const text = query.toString();
  return `#/projects/${projectId}/pipelines/${pipelineId}${text ? `?${text}` : ''}`;
}

function NotFound({ projectId, kind }: { projectId: string; kind: string | null }) {
  return (
    <EmptyState
      headingLevel="h2"
      title="Pipeline not found"
      description="This project has no pipeline at this address. It may have been opened from another project or an incomplete link."
      action={
        <Button variant="outline" asChild>
          <a href={listHref(projectId, kind)}>Back to pipelines</a>
        </Button>
      }
    />
  );
}

/** Keeps an editor failure from blanking the page; shows a safe message instead. */
export class EditorErrorBoundary extends Component<
  { projectId: string; kind: string | null; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) {
      return this.props.children;
    }
    return (
      <ErrorState
        headingLevel="h2"
        title="The pipeline editor could not be shown"
        message="Something in this pipeline could not be displayed. Your saved versions are unchanged."
        onRetry={() => this.setState({ failed: false })}
        action={
          <Button variant="outline" asChild>
            <a href={listHref(this.props.projectId, this.props.kind)}>Back to pipelines</a>
          </Button>
        }
      />
    );
  }
}

export function PipelineRoute({ projectId, pipelineId, versionId, linkedKind }: Props) {
  const isNew = pipelineId === 'new';
  const [loaded, setLoaded] = useState<Loaded>({ state: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (isNew) {
      return;
    }
    let disposed = false;
    setLoaded({ state: 'loading' });
    getPipeline(projectId, pipelineId)
      .then((pipeline) => {
        if (disposed) {
          return;
        }
        if (pipeline.kind !== 'answer' && pipeline.kind !== 'ingestion') {
          // An unexpected response keeps the kind the link names.
          setLoaded({ state: 'ready', kind: linkedKind === 'ingestion' ? 'ingestion' : 'answer' });
          return;
        }
        if ((linkedKind === 'ingestion') !== (pipeline.kind === 'ingestion')) {
          // Correct the address so a reload or a copied link opens the same editor.
          window.history.replaceState(
            null,
            '',
            pipelineHref(projectId, pipelineId, pipeline.kind, versionId),
          );
        }
        setLoaded({ state: 'ready', kind: pipeline.kind });
      })
      .catch((cause) => {
        if (disposed) {
          return;
        }
        if (cause instanceof ApiError && (cause.status === 404 || cause.status === 422)) {
          setLoaded({ state: 'missing' });
        } else {
          setLoaded({
            state: 'error',
            message: cause instanceof Error ? cause.message : 'Request failed.',
          });
        }
      });
    return () => {
      disposed = true;
    };
  }, [isNew, projectId, pipelineId, versionId, linkedKind, attempt]);

  const kind: PipelineKind | null = isNew
    ? linkedKind === 'ingestion'
      ? 'ingestion'
      : 'answer'
    : loaded.state === 'ready'
      ? loaded.kind
      : null;
  if (!isNew && loaded.state === 'missing') {
    return <NotFound projectId={projectId} kind={linkedKind} />;
  }
  if (!isNew && loaded.state === 'error') {
    return (
      <ErrorState
        headingLevel="h2"
        title="The pipeline could not be loaded"
        message={loaded.message}
        onRetry={() => setAttempt((value) => value + 1)}
      />
    );
  }
  if (!kind) {
    return <LoadingState label="Loading pipeline…" />;
  }
  return (
    <EditorErrorBoundary key={`${pipelineId}:${kind}`} projectId={projectId} kind={kind}>
      <Suspense fallback={<LoadingState label="Loading pipeline…" />}>
        {kind === 'ingestion' ? (
          <IngestionPipelineEditor
            projectId={projectId}
            pipelineId={pipelineId}
            versionId={versionId}
          />
        ) : (
          <PipelineEditor projectId={projectId} pipelineId={pipelineId} versionId={versionId} />
        )}
      </Suspense>
    </EditorErrorBoundary>
  );
}
