import {
  FlaskConical,
  BookOpen,
  Workflow,
  MessageSquare,
  Settings,
  LayoutDashboard,
  Server,
} from 'lucide-react';
export const pages = [
  ['overview', 'Overview', LayoutDashboard],
  ['knowledge-base', 'Knowledge Base', BookOpen],
  ['pipelines', 'Pipelines', Workflow],
  ['deployments', 'Deployments', Server],
  ['playground', 'Playground', MessageSquare],
  ['experiments', 'Experiments', FlaskConical],
  ['settings', 'Settings', Settings],
] as const;

export type PagePath = (typeof pages)[number][0];

// Knowledge Base, Pipelines and Playground reopen at the view last used in this project.
const REMEMBERED: readonly string[] = ['knowledge-base', 'pipelines', 'playground'];

export function pageHref(projectId: string, path: PagePath) {
  const fallback = `#/projects/${projectId}/${path}`;
  return REMEMBERED.includes(path)
    ? sessionStorage.getItem(`${path}:${projectId}`) || fallback
    : fallback;
}
