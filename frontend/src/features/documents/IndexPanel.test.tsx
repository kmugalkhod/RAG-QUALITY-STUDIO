import { beforeEach, expect, test, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import * as api from './indexApi';
import { IndexPanel } from './IndexPanel';
vi.mock('./indexApi');
const config: api.EmbeddingConfig = { provider: 'openrouter', model: 'openai/text-embedding-3-small', dimensions: 1536, endpoint_id: 'endpoint', revision: '1' };
const index: api.IndexVersion = { id: 'i1', project_id: 'p1', version: 1, embedding_config: config, status: 'succeeded', chunk_count: 3, embedded_count: 3, attempts: 1, failures: 0, error: null, created_at: '2026-09-09T00:00:00Z' };
const page = (items: api.IndexVersion[]) => ({ items, total: items.length, limit: 20, offset: 0 });
beforeEach(() => {
  vi.resetAllMocks();
  window.history.replaceState(null, '', '/');
  vi.mocked(api.getIndex).mockResolvedValue(index);
  vi.mocked(api.embeddingSettings).mockResolvedValue({ configured: true, config, error: null });
  vi.mocked(api.listIndexes).mockResolvedValue(page([]));
});

test('shows missing server configuration and keeps paid action disabled', async () => {
  vi.mocked(api.embeddingSettings).mockResolvedValue({ configured: false, config: null, error: 'Set OPENROUTER_API_KEY in the server environment.' });
  render(<IndexPanel projectId="p1"/>);
  expect(await screen.findByText(/Set OPENROUTER_API_KEY/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Prepare document set' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Search documents only' })).toBeDisabled();
});

test('creates an index, shows progress and cancels', async () => {
  const queued = { ...index, status: 'queued' as const, embedded_count: 1 };
  vi.mocked(api.createIndex).mockImplementation(async () => {
    vi.mocked(api.listIndexes).mockResolvedValue(page([queued]));
    return queued;
  });
  vi.mocked(api.cancelIndex).mockResolvedValue({ ...queued, status: 'cancelled' });
  render(<IndexPanel projectId="p1"/>);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Prepare document set' })).toBeEnabled());
  await userEvent.click(screen.getByRole('button', { name: 'Prepare document set' }));
  expect(await screen.findByText(/Document set version 1 created with 3 passages/)).toBeVisible();
  expect(await screen.findByRole('progressbar')).toHaveAttribute('value', '1');
  expect(screen.getByRole('button', { name: 'Prepare document set' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Cancel document set 1' }));
  expect(api.cancelIndex).toHaveBeenCalledWith('p1', 'i1');
  expect(await screen.findByText(/Document set version 1 cancelled/)).toBeVisible();
});

test('retrieves from explicit version and exposes source evidence and distance', async () => {
  vi.mocked(api.listIndexes).mockResolvedValue(page([index]));
  vi.mocked(api.retrieve).mockResolvedValue({ index_id: 'i1', index_version: 1, embedding_config: config, score_semantics: 'Cosine distance', items: [{ rank: 1, document_id: 'd1', filename: 'source.pdf', content_hash: 'hash', run_id: 'r1', processing_version: 2, ordinal: 0, page_number: 3, start_char: 0, end_char: 9, text: 'Evidence.', cosine_distance: 0.1234 }] });
  render(<IndexPanel projectId="p1"/>);
  await userEvent.click(await screen.findByRole('button', { name: 'Use document set 1' }));
  await userEvent.type(screen.getByLabelText('Search query'), 'Where is the evidence?');
  await userEvent.click(screen.getByRole('button', { name: 'Search documents only' }));
  expect(api.retrieve).toHaveBeenCalledWith('p1', 'i1', 'Where is the evidence?', { mode: 'vector', top_k: 5, max_vector_distance: null });
  expect(await screen.findByText('Evidence.')).toBeVisible();
  expect(screen.getByText(/Cosine distance 0.1234/)).toHaveTextContent('PDF page 3');
  expect(screen.getByText(/1 passages from document set version 1/)).toBeVisible();
});

test('validates queries and top k; retry preserves error until a new action', async () => {
  vi.mocked(api.listIndexes).mockResolvedValue(page([index]));
  vi.mocked(api.retrieve).mockRejectedValueOnce(new Error('Provider unavailable.')).mockResolvedValue({ index_id: 'i1', index_version: 1, embedding_config: config, items: [], score_semantics: '' });
  render(<IndexPanel projectId="p1"/>);
  await userEvent.click(await screen.findByRole('button', { name: 'Use document set 1' }));
  await userEvent.click(screen.getByRole('button', { name: 'Search documents only' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('enter a query');
  expect(api.retrieve).not.toHaveBeenCalled();
  await userEvent.type(screen.getByLabelText('Search query'), 'query');
  await userEvent.clear(screen.getByLabelText('Top k'));
  await userEvent.type(screen.getByLabelText('Top k'), '51');
  await userEvent.click(screen.getByRole('button', { name: 'Search documents only' }));
  expect(api.retrieve).not.toHaveBeenCalled();
  await userEvent.clear(screen.getByLabelText('Top k'));
  await userEvent.type(screen.getByLabelText('Top k'), '5');
  await userEvent.click(screen.getByRole('button', { name: 'Search documents only' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Provider unavailable');
  await userEvent.click(screen.getByRole('button', { name: 'Refresh document sets' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Provider unavailable');
  await userEvent.click(screen.getByRole('button', { name: 'Search documents only' }));
  expect(await screen.findByText('No matching passages in this document set.')).toBeVisible();
});

test('loading errors can be retried; index failures are visible', async () => {
  vi.mocked(api.listIndexes).mockRejectedValueOnce(new Error('Indexes unavailable.')).mockResolvedValue(page([{ ...index, status: 'failed', error: 'Invalid vector dimensions.' }]));
  render(<IndexPanel projectId="p1"/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Indexes unavailable');
  await userEvent.click(screen.getByRole('button', { name: 'Refresh document sets' }));
  expect(await screen.findByText('Invalid vector dimensions.')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Use document set 1' })).toBeNull();
});


test('restores an explicitly selected ready index from a direct link', async () => {
  window.history.replaceState(null, '', '#/projects/p1/knowledge-base?view=indexes&index=i1');
  vi.mocked(api.listIndexes).mockResolvedValue(page([index]));
  render(<IndexPanel projectId="p1"/>);
  expect(await screen.findByText(/Searching document set · Version 1/)).toBeVisible();
  expect(api.getIndex).toHaveBeenCalledWith('p1', 'i1');
  expect(screen.getByRole('button', { name: 'Use document set 1' })).toHaveAttribute('aria-pressed', 'true');
});
