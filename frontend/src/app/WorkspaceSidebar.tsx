import { NativeSelect, NativeSelectOption } from '../components/ui/native-select';
import { Label } from '../components/ui/label';
import { BookOpen, Folder, Layers3 } from 'lucide-react';
import type { Project } from '../features/projects/api';
import { cn } from '../lib/utils';
import { pageHref, pages } from './pages';
import { docsHref } from '../lib/docs';

type WorkspaceSidebarProps = {
  projectId?: string;
  page: string;
  current?: Project;
  projects: Project[];
};

const NAV_LINK =
  'flex h-row items-center gap-3 rounded-control px-3 text-sm outline-none hover:bg-surface-hover focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent';

function navLinkClass(active: boolean) {
  return cn(
    NAV_LINK,
    active ? 'bg-surface-hover font-medium text-foreground' : 'text-foreground-muted',
  );
}

// Spec 0002, AC-5. The 224px desktop sidebar; below 768px the bottom tab bar replaces it.
export function WorkspaceSidebar({ projectId, page, current, projects }: WorkspaceSidebarProps) {
  return (
    <aside className="sticky top-0 hidden h-dvh w-sidebar shrink-0 flex-col gap-6 border-r border-border bg-surface p-4 md:flex">
      <a
        className="flex h-control-md items-center gap-2 rounded-control px-2 text-sm font-semibold text-foreground outline-none focus-visible:outline-2 focus-visible:outline-accent"
        href="#/"
        aria-label="RAG Quality Studio home"
      >
        <Layers3 aria-hidden="true" className="size-(--icon-lg) text-accent" />
        <span>
          RAG Quality <span className="font-normal text-foreground-muted">Studio</span>
        </span>
      </a>
      <div>
        <Label htmlFor="workspace-project">Project</Label>
        <NativeSelect
          id="workspace-project"
          aria-label="Switch project"
          title={current?.name ?? 'All projects'}
          value={projectId || ''}
          onChange={(e) => {
            const destination = e.target.value;
            const samePage = pages.find((p) => p[0] === page)?.[0];
            window.location.hash = destination
              ? pageHref(destination, samePage ?? 'overview').replace(/^#/, '')
              : '/';
          }}
        >
          <NativeSelectOption value="">All projects</NativeSelectOption>
          {current && !projects.some((p) => p.id === current.id) && (
            <NativeSelectOption value={current.id}>{current.name}</NativeSelectOption>
          )}
          {projects.map((p) => (
            <NativeSelectOption key={p.id} value={p.id}>
              {p.name}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
      <nav aria-label="Project navigation" className="flex flex-col gap-1">
        {projectId ? (
          pages.map(([path, label, Icon]) => (
            <a
              key={path}
              href={pageHref(projectId, path)}
              className={navLinkClass(page === path)}
              aria-current={page === path ? 'page' : undefined}
            >
              <Icon aria-hidden="true" className="size-4" />
              {label}
            </a>
          ))
        ) : (
          <a href="#/" className={navLinkClass(true)} aria-current="page">
            <Folder aria-hidden="true" className="size-4" />
            Projects
          </a>
        )}
      </nav>
      <div className="mt-auto flex flex-col gap-1 border-t border-border pt-4">
        {projectId && (
          <a href="#/" className={navLinkClass(false)}>
            <Folder aria-hidden="true" className="size-4" />
            Manage projects
          </a>
        )}
        <a
          className={navLinkClass(false)}
          href={docsHref('start')}
          target="_blank"
          rel="noopener noreferrer"
        >
          <BookOpen aria-hidden="true" className="size-4" />
          Help &amp; docs
        </a>
      </div>
    </aside>
  );
}
