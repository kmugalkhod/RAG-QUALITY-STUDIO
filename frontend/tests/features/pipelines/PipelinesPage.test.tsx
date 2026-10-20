import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { PipelinesPage } from '../../../src/features/pipelines/PipelinesPage';

const emptyPage = { items: [], total: 0, limit: 25, offset: 0 };

function respond(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  window.location.hash = '';
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => respond(emptyPage));
});

const lastUrl = () => String(vi.mocked(fetch).mock.calls.at(-1)?.[0]);

test('uses URL-addressable kind tabs and enables the ingestion editor', async () => {
  const user = userEvent.setup();
  const { rerender } = render(<PipelinesPage projectId="project-a" kind="answer" />);
  await screen.findByText('Build your first answer pipeline');
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/projects/project-a/pipelines?kind=answer&limit=25&offset=0',
    expect.any(Object),
  );
  expect(screen.getByRole('link', { name: 'New answer pipeline' })).toHaveAttribute(
    'href',
    '#/projects/project-a/pipelines/new',
  );
  expect(screen.queryByLabelText('Last run')).not.toBeInTheDocument();

  await user.click(screen.getByRole('tab', { name: 'Ingestion pipelines' }));
  expect(window.location.hash).toBe('#/projects/project-a/pipelines?kind=ingestion');
  rerender(<PipelinesPage projectId="project-a" kind="ingestion" />);
  await screen.findByText('No ingestion pipelines yet');
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/projects/project-a/pipelines?kind=ingestion&limit=25&offset=0',
    expect.any(Object),
  );
  expect(screen.getByRole('link', { name: 'New ingestion pipeline' })).toHaveAttribute(
    'href',
    '#/projects/project-a/pipelines/new?kind=ingestion',
  );
});

test('normalizes an unknown tab to answer without sending it to the API', async () => {
  render(<PipelinesPage projectId="project-a" kind="unknown" />);
  await waitFor(() => expect(fetch).toHaveBeenCalled());
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/projects/project-a/pipelines?kind=answer&limit=25&offset=0',
    expect.any(Object),
  );
});

const rows = {
  items: [
    {
      id: 'p1',
      name: 'Census rows',
      kind: 'ingestion',
      latest_version: { version: 3, created_at: '2026-10-18T10:00:00Z' },
      last_run: {
        id: 'r1',
        pipeline_version: 2,
        status: 'succeeded',
        completion: 'with_warnings',
        created_at: '2026-10-18T10:00:00Z',
        finished_at: '2026-10-18T10:05:00Z',
      },
      published_index: {
        id: 'i1',
        version: 4,
        knowledge_set_id: 'k1',
        knowledge_set_name: 'Census index',
        is_current: true,
      },
    },
    {
      id: 'p2',
      name: 'GAO tables',
      kind: 'ingestion',
      latest_version: { version: 1, created_at: '2026-10-17T10:00:00Z' },
      last_run: {
        id: 'r2',
        pipeline_version: 1,
        status: 'failed',
        completion: null,
        created_at: '2026-10-17T10:00:00Z',
        finished_at: null,
      },
      published_index: null,
    },
    {
      id: 'p3',
      name: 'Harbor site',
      kind: 'ingestion',
      latest_version: { version: 1, created_at: '2026-10-16T10:00:00Z' },
      last_run: null,
      published_index: null,
    },
  ],
  total: 60,
  limit: 25,
  offset: 0,
};

test('each ingestion row shows its last run and published index', async () => {
  vi.mocked(fetch).mockImplementation(async () => respond(rows));
  render(<PipelinesPage projectId="project-a" kind="ingestion" />);
  const list = await screen.findByRole('list', { name: 'Ingestion pipelines' });
  const [census, gao, harbor] = within(list).getAllByRole('listitem');
  expect(census).toHaveTextContent('Complete with warnings');
  expect(census).toHaveTextContent('Version 3');
  expect(census).toHaveTextContent('(version 2)');
  expect(census).toHaveTextContent('Index Census index · version 4 · current');
  expect(gao).toHaveTextContent('Failed');
  expect(gao).toHaveTextContent('No published index');
  expect(harbor).toHaveTextContent('Never run');
  expect(screen.getByRole('status')).toHaveTextContent('60 pipelines · newest first');
  // One request for the page: no per-pipeline version requests for ingestion rows.
  expect(fetch).toHaveBeenCalledTimes(1);
});

test('search, the last-run filter and paging send their parameters', async () => {
  const user = userEvent.setup();
  vi.mocked(fetch).mockImplementation(async () => respond(rows));
  render(<PipelinesPage projectId="project-a" kind="ingestion" />);
  await screen.findByRole('list', { name: 'Ingestion pipelines' });

  await user.click(screen.getByRole('button', { name: /Next/ }));
  await waitFor(() => expect(lastUrl()).toContain('offset=25'));

  await user.type(screen.getByLabelText('Search pipelines'), 'cen');
  await waitFor(() => expect(lastUrl()).toContain('q=cen'));
  expect(lastUrl()).toContain('offset=0');

  await user.selectOptions(screen.getByLabelText('Last run'), 'never_run');
  await waitFor(() => expect(lastUrl()).toContain('outcome=never_run'));
  expect(lastUrl()).toContain('q=cen');
});

test('a search with no match offers to clear it', async () => {
  const user = userEvent.setup();
  render(<PipelinesPage projectId="project-a" kind="ingestion" />);
  await screen.findByText('No ingestion pipelines yet');
  await user.type(screen.getByLabelText('Search pipelines'), 'zzz');
  expect(await screen.findByRole('heading', { name: 'No pipelines match' })).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Clear search and filter' }));
  expect(screen.getByLabelText('Search pipelines')).toHaveValue('');
  await screen.findByText('No ingestion pipelines yet');
});
