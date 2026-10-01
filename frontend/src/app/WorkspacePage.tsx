import { lazy, Suspense } from 'react';
import type { parseRoute } from './navigation';
import { Button } from '../components/ui/button';
import { EmptyState } from '../components/states/EmptyState';
import { LoadingState } from '../components/states/LoadingState';

const ExperimentsPage = lazy(() =>
  import('../features/experiments/ExperimentsPage').then((module) => ({
    default: module.ExperimentsPage,
  })),
);
const IngestionPipelineEditor = lazy(() =>
  import('../features/ingestion-pipelines/IngestionPipelineEditor').then((module) => ({
    default: module.IngestionPipelineEditor,
  })),
);
const KnowledgeBase = lazy(() =>
  import('../features/documents/KnowledgeBase').then((module) => ({
    default: module.KnowledgeBase,
  })),
);
const PipelineEditor = lazy(() =>
  import('../features/pipelines/PipelineEditor').then((module) => ({
    default: module.PipelineEditor,
  })),
);
const PipelinesPage = lazy(() =>
  import('../features/pipelines/PipelinesPage').then((module) => ({
    default: module.PipelinesPage,
  })),
);
const DeploymentsPage = lazy(() =>
  import('../features/deployments/DeploymentsPage').then((module) => ({
    default: module.DeploymentsPage,
  })),
);
const Playground = lazy(() =>
  import('../features/playground/Playground').then((module) => ({ default: module.Playground })),
);
const ProjectsPage = lazy(() =>
  import('../features/projects/ProjectsPage').then((module) => ({
    default: module.ProjectsPage,
  })),
);
const ProjectSummary = lazy(() =>
  import('../features/workspace/ProjectSummary').then((module) => ({
    default: module.ProjectSummary,
  })),
);
type WorkspacePageProps = {
  route: ReturnType<typeof parseRoute>;
  onProjectCreated: () => void;
};
function PageNotFound() {
  return (
    <EmptyState
      title="Page not found"
      description="This address does not match a page in the workspace."
      action={
        <Button variant="outline" asChild>
          <a href="#/">Return to projects</a>
        </Button>
      }
    />
  );
}
function WorkspaceRoute({ route, onProjectCreated }: WorkspacePageProps) {
  const { projectId, page, detail, query } = route;
  if (page === 'projects') {
    return <ProjectsPage onCreated={onProjectCreated} />;
  }
  if (!projectId) {
    return <PageNotFound />;
  }
  switch (page) {
    case 'overview':
      return <ProjectSummary projectId={projectId} />;
    case 'settings':
      return (
        <ProjectSummary
          projectId={projectId}
          configuration
          section={query.get('section') || undefined}
        />
      );
    case 'experiments':
      return <ExperimentsPage projectId={projectId} experimentId={detail} />;
    case 'knowledge-base':
      return <KnowledgeBase projectId={projectId} documentId={query.get('document') || ''} />;
    case 'pipelines':
      return detail ? (
        query.get('kind') === 'ingestion' ? (
          <IngestionPipelineEditor
            projectId={projectId}
            pipelineId={detail}
            versionId={query.get('version') || ''}
          />
        ) : (
          <PipelineEditor
            projectId={projectId}
            pipelineId={detail}
            versionId={query.get('version') || ''}
          />
        )
      ) : (
        <PipelinesPage projectId={projectId} kind={query.get('kind') || 'answer'} />
      );
    case 'playground':
      return (
        <Playground
          projectId={projectId}
          pipelineId={query.get('pipeline') || ''}
          versionId={query.get('version') || ''}
          readyIndexId={query.get('index') || ''}
          retrievalCount={query.get('top_k') || '5'}
          testMode={query.get('mode') || 'pipeline'}
        />
      );
    case 'deployments':
      return <DeploymentsPage projectId={projectId} deploymentId={detail} />;
    default:
      return <PageNotFound />;
  }
}

export function WorkspacePage(props: WorkspacePageProps) {
  return (
    <Suspense fallback={<LoadingState label="Loading page…" />}>
      <WorkspaceRoute {...props} />
    </Suspense>
  );
}
