import { Button } from '../components/ui/button';
import { ErrorState } from '../components/states/ErrorState';
import { LoadingState } from '../components/states/LoadingState';
import { cn } from '../lib/utils';
import { useEffect } from 'react';
import { FolderOpen } from 'lucide-react';
import { useRoute } from './navigation';
import { pages } from './pages';
import { BottomTabBar } from './BottomTabBar';
import { DisconnectedBanner } from './DisconnectedBanner';
import { ShellSidebar, SidebarProfile } from './ShellSidebar';
import { ShellTopBar, type Crumb } from './ShellTopBar';
import { WorkspacePage } from './WorkspacePage';
import { useWorkspaceProjects } from './useWorkspaceProjects';
import { OrganizationSwitcher, UserButton, useClerk, useOrganization, useUser } from '@clerk/react';

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

// The profile footer from the signed in Clerk user and their organization role.
function ClerkProfile() {
  const { user } = useUser();
  const { organization, membership } = useOrganization();
  const role = membership?.role?.replace(/^org:/, '') ?? 'member';
  return (
    <SidebarProfile
      name={user?.fullName || user?.primaryEmailAddress?.emailAddress || 'Signed in'}
      role={`${role} · ${organization?.name ?? 'personal'}`}
    />
  );
}

function detailLabel(page: string, detail: string, kind: string | null) {
  if (page === 'pipelines') {
    if (detail === 'setup') {
      return 'Guided setup';
    }
    if (detail === 'new') {
      return kind === 'ingestion' ? 'New ingestion pipeline' : 'New answer pipeline';
    }
    return 'Editor';
  }
  return page === 'experiments' ? 'Experiment' : page === 'deployments' ? 'Deployment' : detail;
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
  const crumbs: Crumb[] = projectId
    ? [
        { label: projectName, href: `#/projects/${projectId}/overview` },
        {
          label: title,
          href: `#/projects/${projectId}/${page}${page === 'pipelines' && route.query.get('kind') === 'ingestion' ? '?kind=ingestion' : ''}`,
        },
        ...(detail ? [{ label: detailLabel(page, detail, route.query.get('kind')) }] : []),
      ]
    : [{ label: 'Workspace', href: '#/' }, { label: title }];
  if (projectId && page === 'overview') {
    crumbs.splice(1, 1, { label: title });
  }
  return (
    <div className="flex min-h-dvh gap-2 bg-background px-2 text-foreground">
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
      <ShellSidebar
        route={route}
        current={current}
        projects={projects}
        profile={
          clerkEnabled ? (
            <ClerkProfile />
          ) : (
            <SidebarProfile name="Local owner" role="Owner · local" />
          )
        }
      />
      <div className={cn('flex min-w-0 flex-1 flex-col pb-2', viewport && 'desktop:h-dvh')}>
        <div className="sticky top-0 z-30 shrink-0 bg-background py-2">
          <ShellTopBar
            crumbs={crumbs}
            projectId={projectId}
            projectName={projectName}
            projects={projects}
            account={clerkEnabled ? <AuthControls /> : undefined}
          />
        </div>
        <DisconnectedBanner />
        <main
          id="main"
          tabIndex={-1}
          className={cn(
            'w-full min-w-0 flex-1 overflow-clip rounded-shell border border-border bg-surface p-4 md:p-6',
            fullBleed && 'p-0 md:p-0',
            projectId && 'max-md:mb-(--tabbar-clearance)',
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
