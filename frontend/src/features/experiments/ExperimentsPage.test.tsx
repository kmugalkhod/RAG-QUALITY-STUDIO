import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ExperimentsPage } from './ExperimentsPage';
import * as api from './api';
import * as pipelines from '../pipelines/api';
vi.mock('./api', async original => ({ ...await original<typeof api>(), datasets: vi.fn(), history: vi.fn(), options: vi.fn(), preview: vi.fn(), importDataset: vi.fn() }));
vi.mock('../pipelines/api', async original => ({ ...await original<typeof pipelines>(), list: vi.fn() }));
beforeEach(() => {
  vi.mocked(api.datasets).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.mocked(api.history).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.mocked(pipelines.list).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.mocked(api.options).mockResolvedValue({ model: 'test/judge', error: null, max_rows: 200, max_bytes: 2097152, metrics: { faithfulness: 'Answer and context, not overall accuracy.', response_relevancy: 'Requires embeddings.', context_recall: 'Requires reference answer.' } });
});
describe('experiment setup', () => {
  it('explains requirements and prevents running without saved inputs', async () => {
    render(<ExperimentsPage projectId="p"/>);
    expect(await screen.findByText('Requires reference answer.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Run experiment' })).toBeDisabled();
    expect(screen.getByRole('link', { name: 'Download example CSV' })).toHaveAttribute('href', '/api/projects/p/datasets/example.csv');
  });
  it('shows row errors, blocks import, and clears preview when the file changes', async () => {
    const user = userEvent.setup();
    vi.mocked(api.preview).mockResolvedValue({ rows: [], errors: [{ row: 2, message: 'Question is empty.' }], content_hash: 'hash' });
    render(<ExperimentsPage projectId="p"/>);
    await user.upload(await screen.findByLabelText('CSV file'), new File(['question\n'], 'bad.csv', { type: 'text/csv' }));
    await user.click(screen.getByRole('button', { name: 'Preview CSV' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Row 2: Question is empty.');
    expect(screen.getByRole('button', { name: 'Import reviewed dataset' })).toBeDisabled();
    await user.upload(screen.getByLabelText('CSV file'), new File(['question\nvalid'], 'good.csv', { type: 'text/csv' }));
    await waitFor(() => expect(screen.queryByText('Row 2: Question is empty.')).not.toBeInTheDocument());
  });
});
