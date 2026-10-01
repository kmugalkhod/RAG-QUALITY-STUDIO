import { ChevronRight, FolderPlus, Plus, RotateCw } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { EmptyState } from '../../../components/states/EmptyState';
import { ErrorState } from '../../../components/states/ErrorState';
import { LoadingState } from '../../../components/states/LoadingState';
import { Pagination } from '../../../components/Pagination';
import type { ProjectPage } from '../api';

const DATE = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
});

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
    <section className="flex flex-col gap-4" aria-labelledby="all-projects">
      <div className="flex items-center justify-between gap-4">
        <h2
          id="all-projects"
          className="flex items-center gap-2 text-base font-semibold text-foreground"
        >
          All projects
          {page && !loading && !error && (
            <span className="text-sm font-normal text-foreground-muted tabular-nums">
              {page.total}
            </span>
          )}
        </h2>
        <Button variant="ghost" size="sm" disabled={loading} onClick={onRefresh}>
          <RotateCw aria-hidden="true" />
          Refresh
        </Button>
      </div>
      {loading ? (
        <LoadingState label="Loading projects…" />
      ) : error ? (
        <ErrorState
          title="Projects couldn’t be loaded"
          message={error}
          onRetry={onRefresh}
          retryLabel="Try again"
        />
      ) : page?.items.length === 0 ? (
        <EmptyState
          icon={<FolderPlus />}
          title={offset ? 'No projects on this page' : 'Your first project starts here'}
          description={
            offset
              ? 'Return to the previous page to see your projects.'
              : 'Create a project to organize sources, pipelines, and experiments.'
          }
          action={
            !offset && !formOpen ? (
              <Button variant="outline" onClick={onCreate}>
                <Plus aria-hidden="true" />
                Create your first project
              </Button>
            ) : null
          }
        />
      ) : (
        <ul className="overflow-hidden rounded-card border border-border bg-surface">
          {page?.items.map((project) => (
            <li
              key={project.id}
              className="relative flex items-center gap-4 border-b border-border px-4 py-3 last:border-b-0 hover:bg-surface-hover"
            >
              <span
                aria-hidden="true"
                className="flex size-control-md shrink-0 items-center justify-center rounded-control border border-border text-sm font-medium text-foreground-muted"
              >
                {project.name.slice(0, 1).toUpperCase()}
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <h3 className="truncate text-sm font-medium text-foreground">
                  {/* The link covers the whole row, so the row is one large target. */}
                  <a
                    className="outline-none after:absolute after:inset-0 after:rounded-card focus-visible:after:outline-2 focus-visible:after:-outline-offset-2 focus-visible:after:outline-accent"
                    href={`#/projects/${project.id}/overview`}
                  >
                    {project.name}
                  </a>
                </h3>
                <p className="truncate text-xs text-foreground-muted">
                  {project.description || 'No description added.'}
                </p>
              </div>
              <p className="hidden shrink-0 flex-col items-end text-xs text-foreground-muted md:flex">
                <span>Created</span>
                <time dateTime={project.created_at} className="text-foreground tabular-nums">
                  {DATE.format(new Date(project.created_at))}
                </time>
              </p>
              <ChevronRight aria-hidden="true" className="size-4 shrink-0 text-foreground-subtle" />
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
