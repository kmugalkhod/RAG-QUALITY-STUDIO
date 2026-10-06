import { useEffect, useState, type ReactNode } from 'react';
import { ChevronDown, ChevronUp, Layers3, PanelLeft } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Label } from '../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../components/ui/native-select';
import type { Project } from '../features/projects/api';
import { cn } from '../lib/utils';
import { pageHref, pages } from './pages';
import { navigationGroups, pipelineKindOf, type NavItem } from './shellNavigation';

type ShellSidebarProps = {
  route: { projectId?: string; page: string; detail?: string; query: URLSearchParams };
  current?: Project;
  projects: Project[];
  profile: ReactNode;
};

type SidebarState = { collapsed: boolean; closed: string[]; pipelinesOpen: boolean };

const STORAGE_KEY = 'rqs.sidebar';
const DEFAULT_STATE: SidebarState = { collapsed: false, closed: [], pipelinesOpen: true };

// Layout preferences only (no project or source data); storage can be unavailable.
function readState(): SidebarState {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') as unknown;
    if (stored && typeof stored === 'object') {
      const value = stored as Partial<SidebarState>;
      return {
        collapsed: value.collapsed === true,
        closed: Array.isArray(value.closed)
          ? value.closed.filter((n) => typeof n === 'string')
          : [],
        pipelinesOpen: value.pipelinesOpen !== false,
      };
    }
  } catch {
    // Fall back to the defaults.
  }
  return DEFAULT_STATE;
}

function useSidebarState() {
  const [state, setState] = useState(readState);
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // The sidebar still works; the choice is just not remembered.
    }
  }, [state]);
  return [state, setState] as const;
}

const NAV_LINK =
  'relative flex h-control-md min-w-0 items-center gap-3 rounded-control px-2 text-sm font-medium outline-none pointer-coarse:h-control-lg hover:bg-surface-hover hover:text-foreground focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent';
// The 2px accent marker sits on the sidebar card's left edge, 12px outside the link.
const MARKER =
  'before:absolute before:inset-y-2 before:-left-3 before:w-(--nav-marker) before:rounded-full before:bg-accent';

function linkClass(active: boolean, marker = active) {
  return cn(
    NAV_LINK,
    active ? 'bg-surface-active text-foreground' : 'text-foreground-muted',
    marker && MARKER,
  );
}

function NavLink({
  item,
  collapsed,
  active,
  trailing,
}: {
  item: NavItem;
  collapsed: boolean;
  active: boolean;
  trailing?: ReactNode;
}) {
  const { Icon } = item;
  return (
    <a
      href={item.href}
      className={cn(linkClass(active), collapsed && 'justify-center px-0', trailing && 'flex-1')}
      aria-current={active ? 'page' : undefined}
      aria-label={collapsed ? item.label : undefined}
      title={collapsed ? item.label : undefined}
      {...(item.external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
    >
      <Icon aria-hidden="true" className={cn('size-4 shrink-0', active && 'text-accent')} />
      {!collapsed && <span className="truncate">{item.label}</span>}
    </a>
  );
}

function initials(name: string) {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return (words.length > 1 ? words[0][0] + words[1][0] : name.slice(0, 2)).toUpperCase() || '?';
}

// Spec 0003. The grouped sidebar card: 240px, or 64px of icons when collapsed. Below 768px
// the bottom tab bar replaces it.
export function ShellSidebar({ route, current, projects, profile }: ShellSidebarProps) {
  const { projectId, page } = route;
  const [state, setState] = useSidebarState();
  // Pipeline editors start with the sidebar as icons so the canvas gets the width. Expanding
  // it there lasts until the editor is left; the remembered preference is not changed.
  const editor = page === 'pipelines' && !!route.detail && route.detail !== 'setup';
  const editorKey = editor ? `${projectId}/${route.detail}` : '';
  const [expandedIn, setExpandedIn] = useState('');
  const collapsed = editor ? expandedIn !== editorKey : state.collapsed;
  const toggleCollapsed = () => {
    if (editor) {
      setExpandedIn(collapsed ? editorKey : '');
    } else {
      setState((value) => ({ ...value, collapsed: !value.collapsed }));
    }
  };
  const groups = navigationGroups(route);
  const kind = pipelineKindOf(route);
  const subOpen = !collapsed && state.pipelinesOpen;

  return (
    <div className="sticky top-0 hidden h-dvh shrink-0 py-2 md:flex">
      <aside
        aria-label="Studio navigation"
        data-collapsed={collapsed}
        className={cn(
          'group/shell flex flex-col overflow-y-auto rounded-shell border border-border bg-surface px-3',
          collapsed ? 'w-16' : 'w-sidebar',
        )}
      >
        <div
          className={cn(
            'flex shrink-0 items-center gap-2',
            collapsed ? 'flex-col py-3' : 'h-12 justify-between',
          )}
        >
          <a
            className="flex h-control-md min-w-0 items-center gap-2 rounded-control px-1 text-sm font-semibold text-foreground outline-none focus-visible:outline-2 focus-visible:outline-accent"
            href="#/"
            aria-label="RAG Quality Studio home"
          >
            <Layers3 aria-hidden="true" className="size-(--icon-lg) shrink-0 text-accent" />
            {!collapsed && (
              <span className="truncate">
                RAG <span className="text-accent">Quality</span> Studio
              </span>
            )}
          </a>
          <Button
            variant="ghost"
            size="sm"
            icon
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-expanded={!collapsed}
            onClick={toggleCollapsed}
          >
            <PanelLeft aria-hidden="true" className="text-foreground-muted" />
          </Button>
        </div>

        <div className={cn('border-t border-border py-3', collapsed && 'flex justify-center')}>
          {collapsed ? (
            <a
              href="#/"
              aria-label={`${current?.name ?? 'All projects'}, switch project`}
              title={current?.name ?? 'All projects'}
              className="flex size-control-md items-center justify-center rounded-control bg-surface-active font-mono text-xs font-medium text-accent outline-none focus-visible:outline-2 focus-visible:outline-accent pointer-coarse:size-control-lg"
            >
              {current ? initials(current.name) : <Layers3 aria-hidden="true" className="size-4" />}
            </a>
          ) : (
            <>
              <Label htmlFor="workspace-project" className="sr-only">
                Project
              </Label>
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
            </>
          )}
        </div>

        <nav aria-label="Project navigation" className="flex flex-col">
          {groups.map((group) => {
            const open = collapsed || !state.closed.includes(group.name);
            const listId = `nav-group-${group.name.toLowerCase()}`;
            return (
              <div key={group.name} className="flex flex-col border-t border-border py-2">
                {!collapsed && (
                  <button
                    type="button"
                    aria-expanded={open}
                    aria-controls={listId}
                    className="flex h-control-sm items-center justify-between rounded-control px-1 text-xs font-medium text-foreground-muted outline-none pointer-coarse:h-control-lg hover:text-foreground focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
                    onClick={() =>
                      setState((value) => ({
                        ...value,
                        closed: open
                          ? [...value.closed, group.name]
                          : value.closed.filter((name) => name !== group.name),
                      }))
                    }
                  >
                    {group.name}
                    {open ? (
                      <ChevronUp aria-hidden="true" className="size-3" />
                    ) : (
                      <ChevronDown aria-hidden="true" className="size-3" />
                    )}
                  </button>
                )}
                {open && (
                  <ul id={listId} className="flex flex-col gap-1">
                    {group.items.map((item) =>
                      item.key === 'pipelines' && projectId ? (
                        <li key={item.key}>
                          <div className="flex items-center gap-1">
                            <NavLink
                              item={item}
                              collapsed={collapsed}
                              active={item.current && !subOpen}
                              trailing={!collapsed}
                            />
                            {!collapsed && (
                              <Button
                                variant="ghost"
                                size="sm"
                                icon
                                aria-label="Pipeline kinds"
                                aria-expanded={subOpen}
                                aria-controls="nav-pipeline-kinds"
                                onClick={() =>
                                  setState((value) => ({
                                    ...value,
                                    pipelinesOpen: !value.pipelinesOpen,
                                  }))
                                }
                              >
                                {subOpen ? (
                                  <ChevronUp aria-hidden="true" className="text-foreground-muted" />
                                ) : (
                                  <ChevronDown
                                    aria-hidden="true"
                                    className="text-foreground-muted"
                                  />
                                )}
                              </Button>
                            )}
                          </div>
                          {subOpen && (
                            <ul
                              id="nav-pipeline-kinds"
                              className="mt-1 ml-4 flex flex-col gap-1 border-l border-border pl-3"
                            >
                              {(['answer', 'ingestion'] as const).map((value) => {
                                const active = kind === value;
                                return (
                                  <li key={value}>
                                    <a
                                      href={`#/projects/${projectId}/pipelines?kind=${value}`}
                                      aria-current={active ? 'page' : undefined}
                                      className={cn(linkClass(active), 'h-control-sm font-normal')}
                                    >
                                      {value === 'answer'
                                        ? 'Answer pipelines'
                                        : 'Ingestion pipelines'}
                                    </a>
                                  </li>
                                );
                              })}
                            </ul>
                          )}
                        </li>
                      ) : (
                        <li key={item.key}>
                          <NavLink item={item} collapsed={collapsed} active={item.current} />
                        </li>
                      ),
                    )}
                  </ul>
                )}
              </div>
            );
          })}
        </nav>

        <div
          className={cn(
            'mt-auto flex shrink-0 items-center gap-3 border-t border-border py-3',
            collapsed && 'justify-center',
          )}
        >
          {profile}
        </div>
      </aside>
    </div>
  );
}

/** The profile footer; Clerk builds its own from the signed in user. */
export function SidebarProfile({ name, role }: { name: string; role: string }) {
  return (
    <>
      <span
        aria-hidden="true"
        title={`${name} · ${role}`}
        className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border-strong text-xs font-semibold"
      >
        {initials(name)}
      </span>
      <span className="flex min-w-0 flex-col group-data-[collapsed=true]/shell:sr-only">
        <span className="truncate text-sm font-semibold">{name}</span>
        <span className="truncate text-xs tracking-wide text-foreground-muted uppercase">
          {role}
        </span>
      </span>
    </>
  );
}
