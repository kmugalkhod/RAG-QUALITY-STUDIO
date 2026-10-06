import {
  BookOpen,
  FlaskConical,
  Folder,
  KeyRound,
  LayoutDashboard,
  LifeBuoy,
  MessageSquare,
  Server,
  Settings,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { docsHref } from '../lib/docs';
import { pageHref, type PagePath } from './pages';

export type NavItem = {
  key: string;
  label: string;
  Icon: LucideIcon;
  href: string;
  current: boolean;
  external?: boolean;
};

export type NavGroup = { name: string; items: NavItem[] };

type ShellRoute = { projectId?: string; page: string; query: URLSearchParams };

const PROJECT_PAGES: { path: PagePath; label: string; Icon: LucideIcon }[] = [
  { path: 'overview', label: 'Overview', Icon: LayoutDashboard },
  { path: 'knowledge-base', label: 'Knowledge Base', Icon: BookOpen },
  { path: 'pipelines', label: 'Pipelines', Icon: Workflow },
  { path: 'playground', label: 'Playground', Icon: MessageSquare },
  { path: 'deployments', label: 'Deployments', Icon: Server },
  { path: 'experiments', label: 'Experiments', Icon: FlaskConical },
  { path: 'settings', label: 'Settings', Icon: Settings },
];

const GROUPS: { name: string; pages: PagePath[] }[] = [
  { name: 'Build', pages: ['overview', 'knowledge-base', 'pipelines'] },
  { name: 'Run', pages: ['playground', 'deployments'] },
  { name: 'Measure', pages: ['experiments', 'settings'] },
];

/** Which pipeline kind the route shows, for the Pipelines sub-menu. */
export function pipelineKindOf(route: ShellRoute): 'answer' | 'ingestion' | undefined {
  if (route.page !== 'pipelines') {
    return undefined;
  }
  return route.query.get('kind') === 'ingestion' ? 'ingestion' : 'answer';
}

// Spec 0003 sidebar: Build, Run and Measure for a project, then the workspace links that
// the spec 0002 sidebar already had (all projects and organization settings).
export function navigationGroups(route: ShellRoute): NavGroup[] {
  const { projectId, page } = route;
  const help: NavItem = {
    key: 'docs',
    label: 'Help & docs',
    Icon: LifeBuoy,
    href: docsHref('start'),
    current: false,
    external: true,
  };
  const workspace: NavGroup = {
    name: 'Workspace',
    items: [
      {
        key: 'projects',
        label: projectId ? 'Manage projects' : 'Projects',
        Icon: Folder,
        href: '#/',
        current: page === 'projects',
      },
      {
        key: 'organization',
        label: 'Organization settings',
        Icon: KeyRound,
        href: '#/organization/settings',
        current: page === 'organization',
      },
    ],
  };
  if (!projectId) {
    return [{ ...workspace, items: [...workspace.items, help] }];
  }
  const groups: NavGroup[] = GROUPS.map(({ name, pages }) => ({
    name,
    items: pages.map((path): NavItem => {
      const { label, Icon } = PROJECT_PAGES.find((entry) => entry.path === path)!;
      return { key: path, label, Icon, href: pageHref(projectId, path), current: page === path };
    }),
  }));
  groups[2].items.push(help);
  return [...groups, workspace];
}

/** Every page the quick jump can open, with canonical (not remembered) addresses. */
export function navigationTargets(projectId: string | undefined) {
  const workspace = [
    { label: 'All projects', href: '#/' },
    { label: 'Organization settings', href: '#/organization/settings' },
  ];
  if (!projectId) {
    return workspace;
  }
  const base = `#/projects/${projectId}`;
  return [
    { label: 'Overview', href: `${base}/overview` },
    { label: 'Knowledge Base', href: `${base}/knowledge-base` },
    { label: 'Answer pipelines', href: `${base}/pipelines?kind=answer` },
    { label: 'Ingestion pipelines', href: `${base}/pipelines?kind=ingestion` },
    { label: 'Playground', href: `${base}/playground` },
    { label: 'Deployments', href: `${base}/deployments` },
    { label: 'Experiments', href: `${base}/experiments` },
    { label: 'Settings', href: `${base}/settings` },
    { label: 'Connections', href: `${base}/settings?section=connections` },
    ...workspace,
  ];
}
