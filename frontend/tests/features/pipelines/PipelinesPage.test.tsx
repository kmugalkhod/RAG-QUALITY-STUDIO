import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { PipelinesPage } from '../../../src/features/pipelines/PipelinesPage';

const emptyPage = { items: [], total: 0, limit: 20, offset: 0 };

beforeEach(() => {
  window.location.hash = '';
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () =>
      new Response(JSON.stringify(emptyPage), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
  );
});

test('uses URL-addressable kind tabs and keeps ingestion actions unavailable', async () => {
  const user = userEvent.setup();
  const { rerender } = render(<PipelinesPage projectId="project-a" kind="answer" />);
  await screen.findByText('Build your first answer pipeline');
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/projects/project-a/pipelines?kind=answer&offset=0',
    expect.any(Object),
  );
  expect(screen.getByRole('link', { name: 'New answer pipeline' })).toHaveAttribute(
    'href',
    '#/projects/project-a/pipelines/new',
  );

  await user.click(screen.getByRole('tab', { name: 'Ingestion pipelines' }));
  expect(window.location.hash).toBe('#/projects/project-a/pipelines?kind=ingestion');
  rerender(<PipelinesPage projectId="project-a" kind="ingestion" />);
  await screen.findByText('No ingestion pipelines yet');
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/projects/project-a/pipelines?kind=ingestion&offset=0',
    expect.any(Object),
  );
  expect(screen.getByRole('button', { name: 'New ingestion pipeline' })).toBeDisabled();
  expect(screen.queryByRole('link', { name: /New ingestion pipeline/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /run|preview|connector/i })).not.toBeInTheDocument();
});

test('normalizes an unknown tab to answer without sending it to the API', async () => {
  render(<PipelinesPage projectId="project-a" kind="unknown" />);
  await waitFor(() => expect(fetch).toHaveBeenCalled());
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/projects/project-a/pipelines?kind=answer&offset=0',
    expect.any(Object),
  );
});
