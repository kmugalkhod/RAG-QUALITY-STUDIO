import { KnowledgeBase } from '../features/documents/KnowledgeBase';
import { IngestionPipelineEditor } from '../features/ingestion-pipelines/IngestionPipelineEditor';
import { ExperimentsPage } from '../features/experiments/ExperimentsPage';
import { PipelineEditor } from '../features/pipelines/PipelineEditor';
import { PipelinesPage } from '../features/pipelines/PipelinesPage';
import { Playground } from '../features/playground/Playground';
import { ProjectsPage } from '../features/projects/ProjectsPage';
import { ProjectSummary } from '../features/workspace/ProjectSummary';
import type { parseRoute } from './navigation';
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
export function WorkspacePage({ route, onProjectCreated }: WorkspacePageProps) {
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
