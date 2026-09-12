import { ArrowRight, FolderPlus, Plus, RotateCw } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Skeleton } from '../../../components/ui/skeleton';
import { Pagination } from '../../../components/Pagination';
import type { ProjectPage } from '../api';

export function ProjectList({
  page,
  offset,
  loading,
  error,
  formOpen,
  onRefresh,
  onPage,
  onCreate,
}: {
  page: ProjectPage | null;
  offset: number;
  loading: boolean;
  error: string;
  formOpen: boolean;
  onRefresh: () => void;
  onPage: (offset: number) => void;
  onCreate: () => void;
}) {
  return (
    <section className="project-section mt-8" aria-labelledby="all-projects">
      <div className="section-heading flex items-center justify-between gap-4 py-3">
        <h2 id="all-projects">
          All projects {page && !loading && !error && <span className="count">{page.total}</span>}
        </h2>
        <Button variant="outline" disabled={loading} onClick={onRefresh}>
          <RotateCw />
          Refresh
        </Button>
      </div>
      {loading ? (
        <div className="loading-state py-6" role="status">
          Loading projects…
          <Skeleton className="mt-4 h-15" />
          <Skeleton className="mt-4 h-15" />
        </div>
      ) : error ? (
        <div className="error-state rounded-lg bg-destructive/10 p-6">
          <h3>Projects couldn’t be loaded</h3>
          <p role="alert">{error}</p>
          <Button variant="outline" onClick={onRefresh}>
            Try again
          </Button>
        </div>
      ) : page?.items.length === 0 ? (
        <div className="empty-state py-16 text-center text-muted-foreground">
          <FolderPlus size={36} />
          <h3>{offset ? 'No projects on this page' : 'Your first project starts here'}</h3>
          <p>
            {offset
              ? 'Return to the previous page to see your projects.'
              : 'Create a project to organize sources, pipelines, and experiments.'}
          </p>
          {!offset && !formOpen && (
            <Button variant="outline" onClick={onCreate}>
              <Plus />
              Create your first project
            </Button>
          )}
        </div>
      ) : (
        <ul className="project-list m-0 list-none border-t border-border p-0">
          {page?.items.map((project) => (
            <li key={project.id}>
              <div className="project-initial" aria-hidden="true">
                {project.name.slice(0, 1).toUpperCase()}
              </div>
              <div className="project-content min-w-0 flex-1">
                <h3>
                  <a className="project-link" href={`#/projects/${project.id}/overview`}>
                    {project.name}
                    <ArrowRight />
                  </a>
                </h3>
                <p>{project.description || 'No description added.'}</p>
              </div>
              <div className="project-date shrink-0 text-right">
                <span>Created</span>
                <time dateTime={project.created_at}>
                  {new Intl.DateTimeFormat(undefined, {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric',
                  }).format(new Date(project.created_at))}
                </time>
              </div>
            </li>
          ))}
        </ul>
      )}
      {!loading && !error && page && (
        <Pagination
          offset={offset}
          total={page.total}
          pageSize={page.limit}
          onChange={onPage}
          label="Project pages"
        />
      )}
    </section>
  );
}
