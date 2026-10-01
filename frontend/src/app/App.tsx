import { Button } from '../components/ui/button';
import { ErrorState } from '../components/states/ErrorState';
import { LoadingState } from '../components/states/LoadingState';
import { cn } from '../lib/utils';
import { useEffect } from 'react';
import { FolderOpen, Layers3 } from 'lucide-react';
import { useRoute } from './navigation';
import { pages } from './pages';
import { BottomTabBar } from './BottomTabBar';
import { DisconnectedBanner } from './DisconnectedBanner';
import { ThemeToggle } from './ThemeToggle';
import { WorkspaceSidebar } from './WorkspaceSidebar';
import { WorkspacePage } from './WorkspacePage';
import { useWorkspaceProjects } from './useWorkspaceProjects';
import { OrganizationSwitcher, UserButton, useClerk } from '@clerk/react';

// Phones keep only the user button; the organization controls stay on wider screens.
function AuthControls() {
  const clerk = useClerk();
  return (
    <div className="flex items-center gap-2">
      <div className="hidden items-center gap-2 md:flex">
        <OrganizationSwitcher hidePersonal />
        <Button variant="ghost" size="sm" onClick={() => clerk.openOrganizationProfile()}>
          Members &amp; invitations
        </Button>
      </div>
      <UserButton />
    </div>
  );
}

// Pages that manage their own full height layout, so the shell adds no padding.
const FULL_BLEED = new Set<string>();

// Pages that fill the viewport on desktop and scroll inside their own regions, so the page
// itself never scrolls (the Playground keeps its composer in view).
const VIEWPORT_PAGES = new Set(['playground']);

export function App() {
  const clerkEnabled = Boolean(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY);
  const route = useRoute();
  const { projectId, page, detail } = route;
  const { projects, current, error, refresh } = useWorkspaceProjects(projectId);
  const title =
    pages.find((p) => p[0] === page)?.[1] ||
    { projects: 'Projects', organization: 'Organization settings' }[page] ||
    'Page not found';
  useEffect(() => {
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
  const fullBleed = FULL_BLEED.has(page) || (page === 'pipelines' && !!detail);
  const viewport = VIEWPORT_PAGES.has(page);
  const projectName = current?.name || (error ? 'Project' : 'Loading project…');
  return (
    <div className="flex min-h-dvh bg-background text-foreground">
      <a
        className="sr-only z-50 rounded-control bg-surface px-4 py-2 text-sm text-foreground focus:not-sr-only focus:absolute focus:top-2 focus:left-2"
        href="#main"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById('main')?.focus();
        }}
      >
        Skip to content
      </a>
      <WorkspaceSidebar projectId={projectId} page={page} current={current} projects={projects} />
      <div className={cn('flex min-w-0 flex-1 flex-col', viewport && 'desktop:h-dvh')}>
        <header className="sticky top-0 z-30 flex h-12 shrink-0 items-center justify-between gap-4 border-b border-border bg-background px-4 md:px-6">
          <p className="hidden min-w-0 truncate text-sm text-foreground-muted md:block">
            {projectId ? projectName : 'Workspace'} <span aria-hidden="true">/</span>{' '}
            <strong className="font-medium text-foreground">
              {title}
              {page === 'pipelines' && detail ? ' / Editor' : ''}
            </strong>
          </p>
          <div className="flex min-w-0 items-center md:hidden">
            {projectId ? (
              <a
                href="#/"
                aria-label={`${projectName}, back to all projects`}
                className="flex h-control-lg min-w-0 items-center rounded-control text-sm font-semibold text-foreground outline-none focus-visible:outline-2 focus-visible:outline-accent"
              >
                <span className="truncate">{projectName}</span>
              </a>
            ) : (
              <a
                href="#/"
                aria-label="RAG Quality Studio home"
                className="flex h-control-lg items-center gap-2 rounded-control text-sm font-semibold text-foreground outline-none focus-visible:outline-2 focus-visible:outline-accent"
              >
                <Layers3 aria-hidden="true" className="size-(--icon-lg) text-accent" />
                RAG Quality Studio
              </a>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <ThemeToggle />
            {clerkEnabled && <AuthControls />}
          </div>
        </header>
        <DisconnectedBanner />
        <main
          id="main"
          tabIndex={-1}
          className={cn(
            'w-full min-w-0 flex-1 p-4 md:p-6',
            fullBleed && 'p-0 md:p-0',
            projectId && 'max-md:pb-(--tabbar-clearance)',
            viewport && 'desktop:flex desktop:min-h-0 desktop:flex-col desktop:overflow-hidden',
          )}
        >
          {projectId && !current ? (
            error ? (
              <ErrorState
                headingLevel="h1"
                title="We couldn’t open this project"
                message={
                  <>
                    {error.message} The service may be temporarily unavailable. Try loading again,
                    or return to your project list.
                  </>
                }
                onRetry={() => refresh()}
                retryLabel="Try loading again"
                action={
                  <Button variant="ghost" asChild>
                    <a href="#/">
                      <FolderOpen aria-hidden="true" />
                      View all projects
                    </a>
                  </Button>
                }
              />
            ) : (
              <LoadingState label="Loading project…" />
            )
          ) : (
            <div
              key={`${projectId}/${page}/${detail || ''}`}
              className={cn(
                'min-w-0',
                viewport && 'desktop:flex desktop:min-h-0 desktop:flex-1 desktop:flex-col',
              )}
            >
              <WorkspacePage route={route} onProjectCreated={refresh} />
            </div>
          )}
        </main>
      </div>
      {projectId && (
        <BottomTabBar projectId={projectId} page={page} section={route.query.get('section')} />
      )}
    </div>
  );
}
