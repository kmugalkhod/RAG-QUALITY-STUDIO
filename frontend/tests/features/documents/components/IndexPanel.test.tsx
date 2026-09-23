import { beforeEach, expect, test, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import * as api from '../../../../src/features/documents/indexApi';
import * as apiModel from '../../../../src/features/documents/model';
import { IndexPanel } from '../../../../src/features/documents/components/IndexPanel';
vi.mock('../../../../src/features/documents/indexApi');
const config: apiModel.EmbeddingConfig = {
  provider: 'openrouter',
  model: 'openai/text-embedding-3-small',
  dimensions: 1536,
  endpoint_id: 'endpoint',
  revision: '1',
};
const index: apiModel.IndexVersion = {
  id: 'i1',
  project_id: 'p1',
  knowledge_set_id: 'k1',
  knowledge_set_name: 'Uploaded documents',
  version: 1,
  embedding_config: config,
  status: 'succeeded',
  chunk_count: 3,
  embedded_count: 3,
  attempts: 1,
  failures: 0,
  processing_run_count: 1,
  is_current: true,
  error: null,
  created_at: '2026-09-09T00:00:00Z',
};
const page = (items: apiModel.IndexVersion[]) => ({
  items,
  total: items.length,
  limit: 20,
  offset: 0,
});
beforeEach(() => {
  vi.resetAllMocks();
  window.history.replaceState(null, '', '/');
  vi.mocked(api.getIndex).mockResolvedValue(index);
  vi.mocked(api.getEmbeddingSettings).mockResolvedValue({ configured: true, config, error: null });
  vi.mocked(api.listIndexes).mockResolvedValue(page([]));
});

test('shows missing server configuration and keeps paid action disabled', async () => {
  vi.mocked(api.getEmbeddingSettings).mockResolvedValue({
    configured: false,
    config: null,
    error: 'Set OPENROUTER_API_KEY in the server environment.',
  });
  render(<IndexPanel projectId="p1" />);
  expect(await screen.findByText(/Set OPENROUTER_API_KEY/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Publish prepared documents' })).toBeDisabled();
  expect(screen.getByRole('heading', { name: 'No searchable collections yet' })).toBeVisible();
});

test('creates an index, shows progress and cancels', async () => {
  const queued = { ...index, status: 'queued' as const, embedded_count: 1 };
  vi.mocked(api.createIndex).mockImplementation(async () => {
    vi.mocked(api.listIndexes).mockResolvedValue(page([queued]));
    return queued;
  });
  vi.mocked(api.cancelIndex).mockResolvedValue({ ...queued, status: 'cancelled' });
  render(<IndexPanel projectId="p1" />);
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Publish prepared documents' })).toBeEnabled(),
  );
  await userEvent.click(screen.getByRole('button', { name: 'Publish prepared documents' }));
  expect(
    await screen.findByText(/version 1 is queued for publication with 3 passages/i),
  ).toBeVisible();
  expect(await screen.findByRole('progressbar')).toHaveAttribute(
    'aria-valuenow',
    '33.33333333333333',
  );
  expect(screen.getByRole('button', { name: 'Publish prepared documents' })).toBeDisabled();
  await userEvent.click(screen.getByRole('tab', { name: 'Versions' }));
  await userEvent.click(screen.getByRole('button', { name: 'Cancel collection version 1' }));
  expect(api.cancelIndex).toHaveBeenCalledWith('p1', 'i1');
  expect(await screen.findByText(/Uploaded documents version 1 is cancelled/)).toBeVisible();
});

test('retrieves from explicit version and exposes source evidence and distance', async () => {
  vi.mocked(api.listIndexes).mockResolvedValue(page([index]));
  vi.mocked(api.retrieve).mockResolvedValue({
    index_id: 'i1',
    index_version: 1,
    embedding_config: config,
    score_semantics: 'Cosine distance',
    items: [
      {
        rank: 1,
        document_id: 'd1',
        filename: 'source.pdf',
        content_hash: 'hash',
        run_id: 'r1',
        processing_version: 2,
        ordinal: 0,
        page_number: 3,
        start_char: 0,
        end_char: 9,
        text: 'Evidence.',
        cosine_distance: 0.1234,
      },
    ],
  });
  render(<IndexPanel projectId="p1" />);
  await userEvent.click(
    await screen.findByRole('button', { name: 'Open Uploaded documents collection' }),
  );
  expect(screen.getByRole('heading', { name: 'Uploaded documents' })).toBeVisible();
  expect(screen.getByText('Current', { exact: true })).toBeVisible();
  expect(screen.getByText(/1 prepared document version/)).toBeVisible();
  expect(screen.getByRole('link', { name: 'Use version 1 in a pipeline' })).toHaveAttribute(
    'href',
    '#/projects/p1/pipelines/new?index=i1',
  );
  await userEvent.click(screen.getByRole('tab', { name: 'Test retrieval' }));
  await userEvent.type(screen.getByLabelText('Search query'), 'Where is the evidence?');
  await userEvent.click(screen.getByRole('button', { name: 'Run retrieval test' }));
  expect(api.retrieve).toHaveBeenCalledWith('p1', 'i1', 'Where is the evidence?', {
    mode: 'vector',
    top_k: 5,
    max_vector_distance: null,
  });
  expect(await screen.findByText('Evidence.')).toBeVisible();
  expect(screen.getByText(/Cosine distance 0.1234/)).toHaveTextContent('PDF page 3');
  expect(screen.getByText(/1 passages from immutable collection version 1/)).toBeVisible();
});

test('validates queries and top k; retry preserves error until a new action', async () => {
  vi.mocked(api.listIndexes).mockResolvedValue(page([index]));
  vi.mocked(api.retrieve)
    .mockRejectedValueOnce(new Error('Provider unavailable.'))
    .mockResolvedValue({
      index_id: 'i1',
      index_version: 1,
      embedding_config: config,
      items: [],
      score_semantics: '',
    });
  render(<IndexPanel projectId="p1" />);
  await userEvent.click(
    await screen.findByRole('button', { name: 'Open Uploaded documents collection' }),
  );
  await userEvent.click(screen.getByRole('tab', { name: 'Test retrieval' }));
  await userEvent.click(screen.getByRole('button', { name: 'Run retrieval test' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('enter a query');
  expect(api.retrieve).not.toHaveBeenCalled();
  await userEvent.type(screen.getByLabelText('Search query'), 'query');
  await userEvent.clear(screen.getByLabelText('Top k'));
  await userEvent.type(screen.getByLabelText('Top k'), '51');
  await userEvent.click(screen.getByRole('button', { name: 'Run retrieval test' }));
  expect(api.retrieve).not.toHaveBeenCalled();
  await userEvent.clear(screen.getByLabelText('Top k'));
  await userEvent.type(screen.getByLabelText('Top k'), '5');
  await userEvent.click(screen.getByRole('button', { name: 'Run retrieval test' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Provider unavailable');
  await userEvent.click(screen.getByRole('button', { name: 'Refresh collections' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Provider unavailable');
  await userEvent.click(screen.getByRole('button', { name: 'Run retrieval test' }));
  expect(await screen.findByText('No matching passages in this document set.')).toBeVisible();
});

test('loading errors can be retried; index failures are visible', async () => {
  vi.mocked(api.listIndexes)
    .mockRejectedValueOnce(new Error('Indexes unavailable.'))
    .mockResolvedValue(page([{ ...index, status: 'failed', error: 'Invalid vector dimensions.' }]));
  render(<IndexPanel projectId="p1" />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Indexes unavailable');
  await userEvent.click(screen.getByRole('button', { name: 'Refresh collections' }));
  await userEvent.click(
    await screen.findByRole('button', { name: 'Open Uploaded documents collection' }),
  );
  expect(await screen.findByText('Invalid vector dimensions.')).toBeVisible();
  expect(screen.getAllByText(/failed/i).length).toBeGreaterThan(0);
});

test('restores an explicitly selected ready index from a direct link', async () => {
  window.history.replaceState(null, '', '#/projects/p1/knowledge-base?view=indexes&index=i1');
  vi.mocked(api.listIndexes).mockResolvedValue(page([index]));
  render(<IndexPanel projectId="p1" />);
  expect(await screen.findByRole('heading', { name: 'Uploaded documents' })).toBeVisible();
  expect(api.getIndex).toHaveBeenCalledWith('p1', 'i1');
  expect(
    screen.getByRole('button', { name: 'Open Uploaded documents collection' }),
  ).toHaveAttribute('aria-pressed', 'true');
  await userEvent.click(screen.getByRole('tab', { name: 'Test retrieval' }));
  expect(
    screen.getByText(/Testing Uploaded documents · immutable version 1 · current/),
  ).toBeVisible();
  expect(window.location.hash).toBe(
    '#/projects/p1/knowledge-base?view=indexes&index=i1&mode=indexes&section=retrieval',
  );
});

test('explains a stale direct-link selection and returns to the collection list', async () => {
  window.history.replaceState(
    null,
    '',
    '#/projects/p1/knowledge-base?view=indexes&mode=indexes&index=missing',
  );
  vi.mocked(api.listIndexes).mockResolvedValue(page([index]));
  vi.mocked(api.getIndex).mockRejectedValue(new Error('Index not found.'));
  render(<IndexPanel projectId="p1" />);
  expect(await screen.findByRole('heading', { name: 'Version unavailable' })).toBeVisible();
  expect(screen.getByRole('alert')).toHaveTextContent('no longer available in this project');
  await userEvent.click(screen.getByRole('button', { name: 'Back to collections' }));
  expect(await screen.findByRole('heading', { name: 'Select a collection' })).toBeVisible();
  expect(window.location.hash).not.toContain('index=missing');
});
