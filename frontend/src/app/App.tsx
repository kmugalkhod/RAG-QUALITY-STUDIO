import { Button } from '../components/ui/button';
import { cn } from '../lib/utils';
import { useEffect, useState } from 'react';
import { CircleAlert, FolderOpen, RotateCw } from 'lucide-react';
import { useRoute } from './navigation';
import { pages } from './pages';
import { WorkspaceSidebar } from './WorkspaceSidebar';
import { WorkspacePage } from './WorkspacePage';
import { useWorkspaceProjects } from './useWorkspaceProjects';
export function App() {
  const route = useRoute();
  const { projectId, page, detail } = route;
  const [mobile, setMobile] = useState(false);
  const { projects, current, error, refresh } = useWorkspaceProjects(projectId);
  const title =
    pages.find((p) => p[0] === page)?.[1] || (page === 'projects' ? 'Projects' : 'Page not found');
  useEffect(() => {
    setMobile(false);
    document.title = `${title}${current ? ` · ${current.name}` : ''} · RAG Quality Studio`;
    document.getElementById('main')?.focus({ preventScroll: true });
  }, [projectId, page, detail, title, current]);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [projectId, page, detail]);
  useEffect(() => {
    if (!projectId || error?.status !== 404) {
      return;
    }
    for (const key of [
      `knowledge-base:${projectId}`,
      `pipelines:${projectId}`,
      `playground:${projectId}`,
      `experiment-draft:v1:${projectId}`,
    ]) {
      sessionStorage.removeItem(key);
    }
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#/`);
    window.dispatchEvent(new Event('hashchange'));
  }, [error?.status, projectId]);
  const queryString = route.query.toString();
  useEffect(() => {
    if (
      projectId &&
      error?.status !== 404 &&
      (page === 'knowledge-base' || page === 'playground' || (page === 'pipelines' && !detail))
    ) {
      sessionStorage.setItem(
        `${page}:${projectId}`,
        `#/projects/${projectId}/${page}${queryString ? `?${queryString}` : ''}`,
      );
    }
  }, [detail, error?.status, projectId, page, queryString]);
  return (
    <div className="app-shell flex min-h-screen">
      <a
        className="skip-link absolute -top-20 left-3.75 p-3 bg-background z-10"
        href="#main"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById('main')?.focus();
        }}
      >
        Skip to content
      </a>
      <WorkspaceSidebar
        projectId={projectId}
        page={page}
        current={current}
        projects={projects}
        mobile={mobile}
        setMobile={setMobile}
      />
      <div className="workspace flex-1 min-w-0 flex flex-col">
        <header className="topbar border-b flex justify-between text-muted-foreground min-h-12 text-xs wrap-anywhere h-12 border-border bg-background py-3.5 px-6.5">
          <span>
            {projectId ? current?.name || 'Loading project…' : 'Workspace'}{' '}
            <span aria-hidden="true">/</span>{' '}
            <strong>
              {title}
              {page === 'pipelines' && detail ? ' / Editor' : ''}
            </strong>
          </span>
        </header>
        <main
          id="main"
          tabIndex={-1}
          className={cn(
            'w-full flex-1 min-w-0 mx-auto p-7 max-[760px]:px-4.5 max-[760px]:py-5.5',
            page === 'playground'
              ? 'playground-main'
              : page === 'knowledge-base'
                ? 'knowledge-main p-0 max-[760px]:p-0'
                : page === 'pipelines' && detail
                  ? 'editor-main p-0 max-[760px]:p-0'
                  : '',
          )}
        >
          {projectId && !current ? (
            error ? (
              <div role="alert" className="project-route-error">
                <div className="project-route-error-icon" aria-hidden="true">
                  <CircleAlert />
                </div>
                <h1>We couldn’t open this project</h1>
                <p>{error.message}</p>
                <p className="project-route-error-help">
                  The service may be temporarily unavailable. Try loading again, or return to your
                  project list.
                </p>
                <div className="project-route-error-actions">
                  <Button onClick={() => refresh()}>
                    <RotateCw />
                    Try loading again
                  </Button>
                  <Button variant="outline" asChild>
                    <a href="#/">
                      <FolderOpen />
                      View all projects
                    </a>
                  </Button>
                </div>
              </div>
            ) : (
              <p role="status">Loading project…</p>
            )
          ) : (
            <div
              key={`${projectId}/${page}/${detail || ''}`}
              className={`page-content min-w-0 ${page}-page`}
            >
              <WorkspacePage route={route} onProjectCreated={refresh} />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
