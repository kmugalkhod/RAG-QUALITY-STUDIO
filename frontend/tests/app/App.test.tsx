import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import { App } from '../../src/app/App';
import { useWorkspaceProjects } from '../../src/app/useWorkspaceProjects';

vi.mock('../../src/app/useWorkspaceProjects');
vi.mock('../../src/app/WorkspaceSidebar', () => ({
  WorkspaceSidebar: () => <nav aria-label="Mock sidebar" />,
}));
vi.mock('../../src/app/WorkspacePage', () => ({
  WorkspacePage: () => <p>Projects route</p>,
}));

const missingProject = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

beforeEach(() => {
  sessionStorage.clear();
  window.history.replaceState(null, '', '/#/');
  window.scrollTo = vi.fn();
  vi.resetAllMocks();
});

test('replaces a stale missing-project route with the projects route', async () => {
  sessionStorage.setItem(`knowledge-base:${missingProject}`, 'stale');
  window.history.replaceState(null, '', `/#/projects/${missingProject}/knowledge-base`);
  vi.mocked(useWorkspaceProjects).mockReturnValue({
    projects: [],
    current: undefined,
    error: { message: 'Project not found.', status: 404 },
    refresh: vi.fn(),
  });

  render(<App />);

  await waitFor(() => expect(window.location.hash).toBe('#/'));
  expect(screen.getByText('Projects route')).toBeVisible();
  expect(sessionStorage.getItem(`knowledge-base:${missingProject}`)).toBeNull();
  expect(screen.queryByText('Project unavailable')).toBeNull();
});

test('gives a temporary project failure specific recovery actions', async () => {
  const refresh = vi.fn();
  window.history.replaceState(null, '', `/#/projects/${missingProject}/knowledge-base`);
  vi.mocked(useWorkspaceProjects).mockReturnValue({
    projects: [],
    current: undefined,
    error: { message: 'Could not reach the server.' },
    refresh,
  });

  render(<App />);

  expect(screen.getByRole('heading', { name: 'We couldn’t open this project' })).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Try loading again' }));
  expect(refresh).toHaveBeenCalledOnce();
  expect(screen.getByRole('link', { name: 'View all projects' })).toHaveAttribute('href', '#/');
  expect(screen.queryByText('Retry')).toBeNull();
});
