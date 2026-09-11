import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProjectsPage } from './ProjectsPage';

const empty = { items: [], total: 0, limit: 20, offset: 0 };
const project = { id: 'abc', name: 'Research', description: 'Support knowledge', created_at: '2026-09-09T10:00:00Z' };
function response(data: unknown, status = 200) { return { ok: status < 400, status, json: async () => data } as Response; }
function mockFetch() { return vi.spyOn(globalThis, 'fetch'); }

test('shows loading then the empty state', async () => {
  let resolve!: (value: Response) => void;
  mockFetch().mockReturnValue(new Promise(r => { resolve = r; }));
  render(<ProjectsPage />);
  expect(screen.getByText('Loading projects…')).toBeInTheDocument();
  resolve(response(empty));
  expect(await screen.findByText('Your first project starts here')).toBeVisible();
});

test('validates whitespace and creates a project through the API', async () => {
  const fetch = mockFetch().mockResolvedValueOnce(response(empty)).mockResolvedValueOnce(response(project, 201)).mockResolvedValueOnce(response({ ...empty, total: 1, items: [project] }));
  const onCreated = vi.fn();
  const user = userEvent.setup(); render(<ProjectsPage onCreated={onCreated} />);
  await screen.findByText('Your first project starts here');
  await user.click(screen.getByRole('button', { name: 'New project' }));
  expect(screen.getByLabelText(/Project name/)).toHaveFocus();
  await user.type(screen.getByLabelText(/Project name/), '   ');
  await user.click(screen.getByRole('button', { name: 'Create project' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Enter a project name');
  expect(fetch).toHaveBeenCalledTimes(1);
  await user.clear(screen.getByLabelText(/Project name/));
  await user.type(screen.getByLabelText(/Project name/), 'Research');
  await user.click(screen.getByRole('button', { name: 'Create project' }));
  expect(await screen.findByRole('heading', { name: 'Research' })).toBeVisible();
  expect(fetch.mock.calls[1][0]).toBe('/api/projects');
  expect(JSON.parse(fetch.mock.calls[1][1]?.body as string)).toEqual({ name: 'Research', description: '' });
  expect(screen.getByRole('status')).toHaveTextContent('created');
  expect(onCreated).toHaveBeenCalledOnce();
});

test('shows list error and retries successfully', async () => {
  mockFetch().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(response(empty));
  const user = userEvent.setup(); render(<ProjectsPage />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the server');
  await user.click(screen.getByRole('button', { name: 'Try again' }));
  expect(await screen.findByText('Your first project starts here')).toBeVisible();
});

test('retains form values after a failed creation', async () => {
  mockFetch().mockResolvedValueOnce(response(empty)).mockResolvedValueOnce(response({}, 503));
  const user = userEvent.setup(); render(<ProjectsPage />);
  await user.click(screen.getByRole('button', { name: 'New project' }));
  await user.type(screen.getByLabelText(/Project name/), 'Keep this');
  await user.click(screen.getByRole('button', { name: 'Create project' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('database is temporarily unavailable');
  expect(screen.getByLabelText(/Project name/)).toHaveValue('Keep this');
  expect(screen.getByRole('button', { name: 'Create project' })).toBeEnabled();
});

test('paginates with the API offset', async () => {
  const fetch = mockFetch().mockResolvedValue(response({ ...empty, items: [project], total: 21 }));
  const user = userEvent.setup(); render(<ProjectsPage />);
  await user.click(await screen.findByRole('button', { name: 'Next' }));
  await waitFor(() => expect(fetch.mock.calls[1][0]).toBe('/api/projects?limit=20&offset=20'));
});
