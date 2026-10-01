import { useEffect, useState } from 'react';
import {
  BookOpen,
  Ellipsis,
  FlaskConical,
  Folder,
  LayoutDashboard,
  MessageSquare,
  Plug,
  Server,
  Settings,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '../components/ui/sheet';
import { cn } from '../lib/utils';
import { pageHref, type PagePath } from './pages';

const TABS: { path: PagePath; label: string; Icon: LucideIcon }[] = [
  { path: 'overview', label: 'Overview', Icon: LayoutDashboard },
  { path: 'knowledge-base', label: 'Knowledge', Icon: BookOpen },
  { path: 'pipelines', label: 'Pipelines', Icon: Workflow },
  { path: 'playground', label: 'Playground', Icon: MessageSquare },
];

// Routes reached through More, so More is the active tab on them.
const MORE_PAGES = new Set(['experiments', 'deployments', 'settings']);

const TAB_CLASS =
  'flex h-tabbar min-w-0 flex-col items-center justify-center gap-1 text-xs font-medium outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent';

// Hide the tab bar while a Playground composer field has focus, so the phone keyboard
// cannot push it over the composer.
function useComposerFocused() {
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    const update = () => setFocused(Boolean(document.activeElement?.closest('[data-composer]')));
    document.addEventListener('focusin', update);
    document.addEventListener('focusout', update);
    return () => {
      document.removeEventListener('focusin', update);
      document.removeEventListener('focusout', update);
    };
  }, []);
  return focused;
}

// Spec 0002, AC-5. The phone navigation on project routes, below 768px only.
export function BottomTabBar({
  projectId,
  page,
  section,
}: {
  projectId: string;
  page: string;
  section: string | null;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  const composerFocused = useComposerFocused();
  const connections = page === 'settings' && section === 'connections';
  const more: { label: string; Icon: LucideIcon; href: string; current: boolean }[] = [
    {
      label: 'Experiments',
      Icon: FlaskConical,
      href: pageHref(projectId, 'experiments'),
      current: page === 'experiments',
    },
    {
      label: 'Deployments',
      Icon: Server,
      href: pageHref(projectId, 'deployments'),
      current: page === 'deployments',
    },
    {
      label: 'Connections',
      Icon: Plug,
      href: `#/projects/${projectId}/settings?section=connections`,
      current: connections,
    },
    {
      label: 'Settings',
      Icon: Settings,
      href: pageHref(projectId, 'settings'),
      current: page === 'settings' && !connections,
    },
    { label: 'All projects', Icon: Folder, href: '#/', current: false },
  ];
  const moreActive = MORE_PAGES.has(page);

  return (
    <nav
      aria-label="Project sections"
      className={cn(
        'fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] md:hidden',
        composerFocused && 'hidden',
      )}
    >
      <ul className="grid grid-cols-5">
        {TABS.map(({ path, label, Icon }) => {
          const active = page === path;
          return (
            <li key={path} className="min-w-0">
              <a
                href={pageHref(projectId, path)}
                aria-current={active ? 'page' : undefined}
                className={cn(TAB_CLASS, active ? 'text-foreground' : 'text-foreground-muted')}
              >
                <Icon
                  aria-hidden="true"
                  className={cn('size-(--icon-lg)', active && 'text-accent')}
                />
                <span className="max-w-full truncate">{label}</span>
              </a>
            </li>
          );
        })}
        <li className="min-w-0">
          <Sheet open={moreOpen} onOpenChange={setMoreOpen}>
            <SheetTrigger asChild>
              <button
                type="button"
                aria-current={moreActive ? 'page' : undefined}
                className={cn(
                  TAB_CLASS,
                  'w-full',
                  moreActive ? 'text-foreground' : 'text-foreground-muted',
                )}
              >
                <Ellipsis
                  aria-hidden="true"
                  className={cn('size-(--icon-lg)', moreActive && 'text-accent')}
                />
                <span>More</span>
              </button>
            </SheetTrigger>
            <SheetContent side="bottom" aria-describedby={undefined}>
              <SheetHeader>
                <SheetTitle>More</SheetTitle>
              </SheetHeader>
              <ul className="flex flex-col px-2 pb-4">
                {more.map(({ label, Icon, href, current }) => (
                  <li key={label}>
                    <SheetClose asChild>
                      <a
                        href={href}
                        aria-current={current ? 'page' : undefined}
                        className={cn(
                          'flex h-control-lg items-center gap-3 rounded-control px-4 text-sm outline-none hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-accent',
                          current
                            ? 'bg-surface-hover font-medium text-foreground'
                            : 'text-foreground-muted',
                        )}
                      >
                        <Icon aria-hidden="true" className="size-(--icon-lg)" />
                        {label}
                      </a>
                    </SheetClose>
                  </li>
                ))}
              </ul>
            </SheetContent>
          </Sheet>
        </li>
      </ul>
    </nav>
  );
}
