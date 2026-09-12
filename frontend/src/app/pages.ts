import {
  FlaskConical,
  BookOpen,
  Workflow,
  MessageSquare,
  Settings,
  LayoutDashboard,
} from 'lucide-react';
export const pages = [
  ['overview', 'Overview', LayoutDashboard],
  ['knowledge-base', 'Knowledge Base', BookOpen],
  ['pipelines', 'Pipelines', Workflow],
  ['playground', 'Playground', MessageSquare],
  ['experiments', 'Experiments', FlaskConical],
  ['settings', 'Settings', Settings],
] as const;
