import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it } from 'vitest';
import { ShellSidebar, SidebarProfile } from '../../src/app/ShellSidebar';

const project = {
  id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  name: 'Evidence Base',
  description: '',
  created_at: '2026-01-01',
};

function Sidebar({
  page = 'playground',
  query = '',
  projects = [],
}: {
  page?: string;
  query?: string;
  projects?: (typeof project)[];
}) {
  return (
    <ShellSidebar
      route={{ projectId: project.id, page, query: new URLSearchParams(query) }}
      current={project}
      projects={projects}
      profile={<SidebarProfile name="Local owner" role="Owner · local" />}
    />
  );
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
});

it('preserves the current project and remembered Playground version before the project list loads', () => {
  const href = `#/projects/${project.id}/playground?version=saved-version`;
  sessionStorage.setItem(`playground:${project.id}`, href);
  render(<Sidebar />);
  expect(screen.getByRole('combobox', { name: 'Switch project' })).toHaveValue(project.id);
  expect(screen.getByRole('link', { name: 'Playground' })).toHaveAttribute('href', href);
  expect(screen.getByRole('link', { name: 'Playground' })).toHaveAttribute('aria-current', 'page');
});

it('restores pipeline tab URLs only from the destination project', async () => {
  const user = userEvent.setup();
  const other = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  sessionStorage.setItem(
    `pipelines:${project.id}`,
    `#/projects/${project.id}/pipelines?kind=ingestion`,
  );
  sessionStorage.setItem(`pipelines:${other}`, `#/projects/${other}/pipelines?kind=answer`);
  render(<Sidebar page="pipelines" projects={[{ ...project, id: other, name: 'Other' }]} />);
  expect(screen.getByRole('link', { name: 'Pipelines' })).toHaveAttribute(
    'href',
    `#/projects/${project.id}/pipelines?kind=ingestion`,
  );
  await user.selectOptions(screen.getByRole('combobox', { name: 'Switch project' }), other);
  expect(window.location.hash).toBe(`#/projects/${other}/pipelines?kind=answer`);
});

it('groups pages under Build, Run and Measure and keeps the workspace links', () => {
  render(<Sidebar />);
  for (const name of ['Build', 'Run', 'Measure', 'Workspace']) {
    expect(screen.getByRole('button', { name })).toHaveAttribute('aria-expanded', 'true');
  }
  for (const name of ['Overview', 'Knowledge Base', 'Deployments', 'Experiments', 'Settings']) {
    expect(screen.getByRole('link', { name })).toBeVisible();
  }
  expect(screen.getByRole('link', { name: 'Manage projects' })).toHaveAttribute('href', '#/');
  expect(screen.getByRole('link', { name: 'Organization settings' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Help & docs' })).toHaveAttribute('target', '_blank');
  expect(screen.getByText('Owner · local')).toBeVisible();
});

it('marks the pipeline kind in the sub-menu, or Pipelines itself when the menu is closed', async () => {
  const user = userEvent.setup();
  render(<Sidebar page="pipelines" query="kind=ingestion" />);
  expect(screen.getByRole('link', { name: 'Ingestion pipelines' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  expect(screen.getByRole('link', { name: 'Pipelines' })).not.toHaveAttribute('aria-current');
  await user.click(screen.getByRole('button', { name: 'Pipeline kinds' }));
  expect(screen.queryByRole('link', { name: 'Ingestion pipelines' })).toBeNull();
  expect(screen.getByRole('link', { name: 'Pipelines' })).toHaveAttribute('aria-current', 'page');
});

it('collapses groups and the whole sidebar, and remembers the choice', async () => {
  const user = userEvent.setup();
  const { unmount } = render(<Sidebar />);
  await user.click(screen.getByRole('button', { name: 'Run' }));
  expect(screen.queryByRole('link', { name: 'Deployments' })).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
  // Collapsed, every page shows as a named icon link and the groups cannot hide them.
  expect(screen.getByRole('link', { name: 'Deployments' })).toBeVisible();
  expect(screen.queryByRole('combobox', { name: 'Switch project' })).toBeNull();
  expect(screen.getByRole('link', { name: 'Evidence Base, switch project' })).toHaveTextContent(
    'EB',
  );
  unmount();
  render(<Sidebar />);
  expect(screen.getByRole('button', { name: 'Expand sidebar' })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
  await user.click(screen.getByRole('button', { name: 'Expand sidebar' }));
  expect(screen.queryByRole('link', { name: 'Deployments' })).toBeNull();
});

it('falls back to the defaults when the stored state is unreadable', () => {
  localStorage.setItem('rqs.sidebar', '{broken');
  render(<Sidebar />);
  expect(screen.getByRole('button', { name: 'Collapse sidebar' })).toBeVisible();
});

it('shows icons in a pipeline editor without changing the remembered preference', async () => {
  const user = userEvent.setup();
  const editor = (detail: string) => (
    <ShellSidebar
      route={{ projectId: project.id, page: 'pipelines', detail, query: new URLSearchParams() }}
      current={project}
      projects={[]}
      profile={null}
    />
  );
  const { rerender } = render(editor('pipeline-1'));
  expect(screen.getByRole('button', { name: 'Expand sidebar' })).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Expand sidebar' }));
  expect(screen.getByRole('button', { name: 'Collapse sidebar' })).toBeVisible();
  // Another editor starts collapsed again; the guided setup and other pages keep the preference.
  rerender(editor('pipeline-2'));
  expect(screen.getByRole('button', { name: 'Expand sidebar' })).toBeVisible();
  rerender(editor('setup'));
  expect(screen.getByRole('button', { name: 'Collapse sidebar' })).toBeVisible();
  expect(JSON.parse(localStorage.getItem('rqs.sidebar') ?? '{}').collapsed).toBe(false);
});
