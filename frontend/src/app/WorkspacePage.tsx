import { lazy, Suspense } from 'react';
import type { parseRoute } from './navigation';

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
    <>
      <h1>Page not found</h1>
      <a href="#/">Return to projects</a>
    </>
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
      return <ProjectSummary projectId={projectId} configuration />;
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
    default:
      return <PageNotFound />;
  }
}

export function WorkspacePage(props: WorkspacePageProps) {
  return (
    <Suspense fallback={<p role="status">Loading page…</p>}>
      <WorkspaceRoute {...props} />
    </Suspense>
  );
}
