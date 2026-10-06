import { Fragment, useSyncExternalStore, type ReactNode } from 'react';
import { ChevronRight, Layers3, RefreshCw } from 'lucide-react';
import type { Project } from '../features/projects/api';
import { getConnection, subscribeConnection } from '../lib/connection';
import { cn } from '../lib/utils';
import { QuickJump } from './QuickJump';
import { ThemeToggle } from './ThemeToggle';
import { useActiveRuns } from './useActiveRuns';

export type Crumb = { label: string; href?: string };

function Divider() {
  return <span aria-hidden="true" className="hidden h-4 w-px shrink-0 bg-border md:block" />;
}

// The API status from the readiness store that also drives the disconnected banner.
function ApiStatus() {
  const { status, lastOkAt } = useSyncExternalStore(subscribeConnection, getConnection);
  const ready = status === 'ok' && lastOkAt !== null;
  const label =
    status === 'unreachable' ? 'API unreachable' : ready ? 'API ready' : 'Checking API…';
  return (
    <span className="hidden shrink-0 items-center gap-2 text-sm font-medium md:flex">
      <span
        aria-hidden="true"
        className={cn(
          'size-2 rounded-full',
          status === 'unreachable' ? 'bg-danger' : ready ? 'bg-success' : 'bg-foreground-subtle',
        )}
      />
      {label}
    </span>
  );
}

function ActiveRuns({ projectId }: { projectId: string }) {
  const count = useActiveRuns(projectId);
  if (count === undefined) {
    return null;
  }
  const description =
    count === null
      ? 'Ingestion runs in progress could not be counted'
      : `${count} ingestion ${count === 1 ? 'run' : 'runs'} in progress (among the 20 most recent)`;
  return (
    <>
      <Divider />
      <span className="flex shrink-0 items-center gap-1 text-sm font-medium" title={description}>
        <RefreshCw aria-hidden="true" className="size-4 text-highlight" />
        <span aria-hidden="true" className="font-mono tabular-nums">
          {count ?? '–'}
        </span>
        <span className="sr-only">{description}</span>
      </span>
    </>
  );
}

// Spec 0003. The slim top bar card: the breadcrumb on the left; search, API status, active
// runs and the theme toggle on the right. Phones show the project link in place of the
// breadcrumb.
export function ShellTopBar({
  crumbs,
  projectId,
  projectName,
  projects,
  account,
}: {
  crumbs: Crumb[];
  projectId?: string;
  projectName: string;
  projects: Project[];
  account?: ReactNode;
}) {
  return (
    <header className="flex h-12 shrink-0 items-center justify-between gap-3 rounded-shell border border-border bg-surface pr-2 pl-4">
      <nav aria-label="Breadcrumb" className="hidden min-w-0 md:block">
        <ol className="flex min-w-0 items-center gap-1 text-sm text-foreground-muted">
          {crumbs.map((crumb, index) => {
            const last = index === crumbs.length - 1;
            return (
              <Fragment key={`${crumb.label}-${index}`}>
                {index > 0 && (
                  <li aria-hidden="true" className="flex shrink-0">
                    <ChevronRight className="size-3 text-foreground-subtle" />
                  </li>
                )}
                <li className={cn('min-w-0', last ? 'shrink' : 'shrink-[2]')}>
                  {last || !crumb.href ? (
                    <span
                      aria-current={last ? 'page' : undefined}
                      className={cn('block truncate', last && 'font-medium text-foreground')}
                    >
                      {crumb.label}
                    </span>
                  ) : (
                    <a
                      href={crumb.href}
                      className="block truncate rounded-control outline-none hover:text-foreground focus-visible:outline-2 focus-visible:outline-accent"
                    >
                      {crumb.label}
                      <span className="sr-only"> (breadcrumb)</span>
                    </a>
                  )}
                </li>
              </Fragment>
            );
          })}
        </ol>
      </nav>
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
            <span>
              RAG <span className="text-accent">Quality</span> Studio
            </span>
          </a>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2 md:gap-3">
        <QuickJump projectId={projectId} projects={projects} />
        <Divider />
        <ApiStatus />
        {projectId && <ActiveRuns key={projectId} projectId={projectId} />}
        <Divider />
        <ThemeToggle />
        {account}
      </div>
    </header>
  );
}
