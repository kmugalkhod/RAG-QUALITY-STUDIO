import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ExperimentsPage } from '../../../src/features/experiments/ExperimentsPage';
import * as api from '../../../src/features/experiments/api';
import * as pipelines from '../../../src/features/pipelines/api';
vi.mock('../../../src/features/experiments/api', async (original) => ({
  ...(await original<typeof api>()),
  listDatasets: vi.fn(),
  listExperiments: vi.fn(),
  getEvaluationOptions: vi.fn(),
  previewDataset: vi.fn(),
  importDataset: vi.fn(),
}));
vi.mock('../../../src/features/pipelines/api', async (original) => ({
  ...(await original<typeof pipelines>()),
  listPipelines: vi.fn(),
}));
beforeEach(() => {
  sessionStorage.clear();
  vi.mocked(api.listDatasets).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.mocked(api.listExperiments).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.mocked(pipelines.listPipelines).mockResolvedValue({
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
  });
  vi.mocked(api.getEvaluationOptions).mockResolvedValue({
    model: 'test/judge',
    error: null,
    max_rows: 200,
    max_bytes: 2097152,
    metrics: {
      faithfulness: 'Answer and context, not overall accuracy.',
      response_relevancy: 'Requires embeddings.',
      context_recall: 'Requires reference answer.',
    },
  });
});
describe('experiment setup', () => {
  it('explains requirements and prevents running without saved inputs', async () => {
    render(<ExperimentsPage projectId="p" />);
    expect(await screen.findByText('Requires reference answer.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Run experiment' })).toBeDisabled();
    expect(screen.getByRole('link', { name: 'Download example CSV' })).toHaveAttribute(
      'href',
      '/api/projects/p/datasets/example.csv',
    );
  });
  it('shows row errors, blocks import, and clears preview when the file changes', async () => {
    const user = userEvent.setup();
    vi.mocked(api.previewDataset).mockResolvedValue({
      rows: [],
      errors: [{ row: 2, message: 'Question is empty.' }],
      content_hash: 'hash',
    });
    render(<ExperimentsPage projectId="p" />);
    await user.upload(
      await screen.findByLabelText('CSV file'),
      new File(['question\n'], 'bad.csv', { type: 'text/csv' }),
    );
    await user.click(screen.getByRole('button', { name: 'Preview CSV' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Row 2: Question is empty.');
    expect(screen.getByRole('button', { name: 'Import reviewed dataset' })).toBeDisabled();
    await user.upload(
      screen.getByLabelText('CSV file'),
      new File(['question\nvalid'], 'good.csv', { type: 'text/csv' }),
    );
    await waitFor(() =>
      expect(screen.queryByText('Row 2: Question is empty.')).not.toBeInTheDocument(),
    );
  });
});

it('restores name and metrics on remount and resets only the draft', async () => {
  const user = userEvent.setup();
  const view = render(<ExperimentsPage projectId="p" />);
  await user.type(await screen.findByLabelText('Experiment name'), 'Saved draft');
  await user.click(screen.getByRole('checkbox', { name: /Response relevancy/ }));
  view.unmount();
  render(<ExperimentsPage projectId="p" />);
  expect(await screen.findByLabelText('Experiment name')).toHaveValue('Saved draft');
  expect(screen.getByRole('checkbox', { name: /Response relevancy/ })).not.toBeChecked();
  await user.click(screen.getByRole('button', { name: 'Reset draft' }));
  expect(screen.getByLabelText('Experiment name')).toHaveValue('');
  expect(screen.getByRole('checkbox', { name: /Response relevancy/ })).toBeChecked();
});

it('removes stale saved IDs before allowing a run', async () => {
  sessionStorage.setItem(
    'experiment-draft:v1:p',
    JSON.stringify({
      name: 'Old',
      dataset: 'missing',
      a: 'missing',
      b: '',
      metrics: ['faithfulness'],
    }),
  );
  render(<ExperimentsPage projectId="p" />);
  expect(await screen.findByLabelText('Dataset version')).toHaveValue('');
  expect(screen.getByLabelText('Candidate A')).toHaveValue('');
  expect(screen.getByRole('button', { name: 'Run experiment' })).toBeDisabled();
});
