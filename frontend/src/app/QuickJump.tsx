import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { listPipelines } from '../features/pipelines/api';
import type { Project } from '../features/projects/api';
import { cn } from '../lib/utils';
import { navigationTargets } from './shellNavigation';

type Target = { group: string; label: string; href: string };

const LINK =
  'flex min-h-control-md items-center rounded-control px-2 text-sm text-foreground outline-none hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent pointer-coarse:min-h-control-lg';

// Spec 0003 top bar search: a client side jump list over the workspace pages, the projects
// and the current project's pipelines. There is no server search, so it only navigates.
export function QuickJump({ projectId, projects }: { projectId?: string; projects: Project[] }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [pipelines, setPipelines] = useState<{ projectId: string; targets: Target[] }>();
  const [pipelineError, setPipelineError] = useState(false);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen(true);
      }
    };
    document.addEventListener('keydown', shortcut);
    return () => document.removeEventListener('keydown', shortcut);
  }, []);

  useEffect(() => {
    if (!open || !projectId || pipelines?.projectId === projectId) {
      return;
    }
    let disposed = false;
    setPipelineError(false);
    Promise.all([listPipelines(projectId, 'answer'), listPipelines(projectId, 'ingestion')])
      .then(([answer, ingestion]) => {
        if (disposed) {
          return;
        }
        setPipelines({
          projectId,
          targets: [
            ...answer.items.map((pipeline) => ({
              group: 'Answer pipelines',
              label: pipeline.name,
              href: `#/projects/${projectId}/pipelines/${pipeline.id}`,
            })),
            ...ingestion.items.map((pipeline) => ({
              group: 'Ingestion pipelines',
              label: pipeline.name,
              href: `#/projects/${projectId}/pipelines/${pipeline.id}?kind=ingestion`,
            })),
          ],
        });
      })
      .catch(() => {
        if (!disposed) {
          setPipelineError(true);
        }
      });
    return () => {
      disposed = true;
    };
  }, [open, pipelines?.projectId, projectId]);

  const targets = useMemo(() => {
    const all: Target[] = [
      ...navigationTargets(projectId).map((target) => ({ group: 'Pages', ...target })),
      ...projects.map((project) => ({
        group: 'Projects',
        label: project.name,
        href: `#/projects/${project.id}/overview`,
      })),
      ...(pipelines && pipelines.projectId === projectId ? pipelines.targets : []),
    ];
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return all.filter((target) =>
      words.every((word) => `${target.label} ${target.group}`.toLowerCase().includes(word)),
    );
  }, [pipelines, projectId, projects, query]);

  const groups = [...new Set(targets.map((target) => target.group))];

  // Arrow keys move between the input and the results; Tab works as well.
  function moveFocus(event: React.KeyboardEvent, from: number) {
    const links = [...(listRef.current?.querySelectorAll('a') ?? [])];
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') {
      return;
    }
    event.preventDefault();
    const next = event.key === 'ArrowDown' ? from + 1 : from - 1;
    if (next < 0) {
      document.getElementById(`${listId}-input`)?.focus();
    } else {
      links[Math.min(next, links.length - 1)]?.focus();
    }
  }

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setQuery('');
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          icon
          aria-label="Jump to a page, project or pipeline"
          title="Jump to a page, project or pipeline (Ctrl K)"
          aria-keyshortcuts="Control+K Meta+K"
        >
          <Search aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="flex max-h-(--quick-jump-height) w-(--quick-jump-width) flex-col gap-2 p-2"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          document.getElementById(`${listId}-input`)?.focus();
        }}
      >
        <Input
          id={`${listId}-input`}
          type="search"
          value={query}
          placeholder="Jump to…"
          aria-label="Filter pages, projects and pipelines"
          aria-controls={listId}
          autoComplete="off"
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => moveFocus(event, -1)}
        />
        <div className="min-h-0 overflow-y-auto">
          {targets.length ? (
            <ul id={listId} ref={listRef} className="flex flex-col gap-2">
              {groups.map((group) => (
                <li key={group}>
                  <p className="px-2 pb-1 text-xs font-medium text-foreground-muted">{group}</p>
                  <ul>
                    {targets
                      .filter((target) => target.group === group)
                      .map((target) => (
                        <li key={target.href}>
                          <a
                            href={target.href}
                            className={cn(LINK, 'wrap-anywhere')}
                            onClick={() => setOpen(false)}
                            onKeyDown={(event) =>
                              moveFocus(
                                event,
                                [...(listRef.current?.querySelectorAll('a') ?? [])].indexOf(
                                  event.currentTarget,
                                ),
                              )
                            }
                          >
                            {target.label}
                          </a>
                        </li>
                      ))}
                  </ul>
                </li>
              ))}
            </ul>
          ) : (
            <p id={listId} className="px-2 py-3 text-sm text-foreground-muted">
              Nothing matches “{query.trim()}”.
            </p>
          )}
          {pipelineError && (
            <p className="px-2 py-2 text-xs text-foreground-muted">
              Pipelines could not be loaded; pages and projects are still listed.
            </p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
