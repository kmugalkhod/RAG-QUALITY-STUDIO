import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it } from 'vitest';
import { WorkspaceSidebar } from '../../src/app/WorkspaceSidebar';

const project = {
  id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  name: 'Evidence',
  description: '',
  created_at: '2026-01-01',
};

function Sidebar({ page = 'playground' }: { page?: string }) {
  const [mobile, setMobile] = useState(false);
  return (
    <WorkspaceSidebar
      projectId={project.id}
      current={project}
      projects={[]}
      page={page}
      mobile={mobile}
      setMobile={setMobile}
    />
  );
}

beforeEach(() => sessionStorage.clear());

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
  render(
    <WorkspaceSidebar
      projectId={project.id}
      current={project}
      projects={[{ ...project, id: other, name: 'Other' }]}
      page="pipelines"
      mobile={false}
      setMobile={() => undefined}
    />,
  );
  expect(screen.getByRole('link', { name: 'Pipelines' })).toHaveAttribute(
    'href',
    `#/projects/${project.id}/pipelines?kind=ingestion`,
  );
  await user.selectOptions(screen.getByRole('combobox', { name: 'Switch project' }), other);
  expect(window.location.hash).toBe(`#/projects/${other}/pipelines?kind=answer`);
});

it('closes navigation with Escape and returns focus to the toggle', async () => {
  const user = userEvent.setup();
  render(<Sidebar />);
  await user.click(screen.getByRole('button', { name: 'Open navigation' }));
  expect(screen.getByRole('button', { name: 'Close navigation' })).toHaveAttribute(
    'aria-expanded',
    'true',
  );
  screen.getByRole('link', { name: 'Overview' }).focus();
  await user.keyboard('{Escape}');
  expect(screen.getByRole('button', { name: 'Open navigation' })).toHaveFocus();
  expect(screen.getByRole('button', { name: 'Open navigation' })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
});
