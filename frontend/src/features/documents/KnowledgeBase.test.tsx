import { render, screen, waitFor, within, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { KnowledgeBase } from './KnowledgeBase';
import * as api from './api';
vi.mock('./api');
const doc: api.Document = { id: 'd1', filename: 'source.txt', size_bytes: 10, content_hash: 'abc', created_at: '2026-09-09T00:00:00Z', latest_run: null };
const run: api.Run = { id: 'r1', document_id: 'd1', version: 1, chunk_size: 4, overlap: 1, status: 'succeeded', progress: 100, error: null, chunk_count: 3, attempts: 1, config_version: 'characters-v1', parser_version: 'utf8-v1', created_at: doc.created_at };
const page = <T,>(items: T[]) => ({ items, total: items.length, offset: 0, limit: 20 });
beforeEach(() => {
  vi.mocked(api.getProject).mockResolvedValue({ id: 'p1', name: 'Research', description: '', created_at: doc.created_at });
  vi.mocked(api.getSettings).mockResolvedValue({ max_upload_bytes: 1024 });
  vi.mocked(api.listDocuments).mockResolvedValue(page([]));
  vi.mocked(api.listRuns).mockResolvedValue(page([]));
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });

test('shows loading, empty state and missing-file validation', async () => {
  render(<KnowledgeBase projectId="p1"/>);
  expect(screen.getByText('Loading documents…')).toBeVisible();
  expect(await screen.findByText('No documents yet')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Upload document' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Choose a PDF');
  expect(api.uploadDocument).not.toHaveBeenCalled();
});

test('uploads and validates chunk settings', async () => {
  vi.mocked(api.uploadDocument).mockResolvedValue(doc);
  render(<KnowledgeBase projectId="p1"/>);
  const input = screen.getByLabelText('PDF or UTF-8 TXT');
  await waitFor(() => expect(input).toBeEnabled());
  await userEvent.upload(input, new File(['abcdefghij'], 'source.txt', { type: 'text/plain' }));
  await userEvent.click(screen.getByRole('button', { name: 'Upload document' }));
  expect(await screen.findByRole('heading', { name: 'Process: source.txt' })).toBeVisible();
  await userEvent.clear(screen.getByLabelText('Chunk size (characters)'));
  await userEvent.type(screen.getByLabelText('Chunk size (characters)'), '10');
  await userEvent.click(screen.getByRole('button', { name: 'Start processing' }));
  expect(screen.getByRole('alert')).toHaveTextContent('smaller than chunk size');
  expect(api.startRun).not.toHaveBeenCalled();
});

test('shows upload progress and storage failure', async () => {
  let reject!: (reason: Error) => void;
  vi.mocked(api.uploadDocument).mockReturnValue(new Promise((_, fail) => { reject = fail; }));
  render(<KnowledgeBase projectId="p1"/>);
  const input = screen.getByLabelText('PDF or UTF-8 TXT');
  await waitFor(() => expect(input).toBeEnabled());
  await userEvent.upload(input, new File(['test'], 'source.txt', { type: 'text/plain' }));
  await userEvent.click(screen.getByRole('button', { name: 'Upload document' }));
  expect(screen.getByRole('button', { name: 'Uploading…' })).toBeDisabled();
  reject(new Error('Storage unavailable.'));
  expect(await screen.findByRole('alert')).toHaveTextContent('Storage unavailable');
  expect(screen.queryByRole('heading', { name: 'Process: source.txt' })).toBeNull();
});

test('loads saved chunks and retries a failed request', async () => {
  vi.mocked(api.listDocuments).mockResolvedValue(page([{ ...doc, latest_run: run }]));
  vi.mocked(api.listRuns).mockResolvedValue(page([run]));
  vi.mocked(api.listChunks).mockRejectedValueOnce(new Error('Connection interrupted.')).mockResolvedValue(page([{ ordinal: 0, page_number: 2, start_char: 0, end_char: 4, text: 'abcd' }]));
  render(<KnowledgeBase projectId="p1"/>);
  await userEvent.click(await screen.findByRole('button', { name: 'Manage source.txt' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Inspect 3 chunks' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Connection interrupted');
  await userEvent.click(screen.getByRole('button', { name: 'Retry loading chunks' }));
  const region = screen.getByRole('region', { name: 'Chunks · Version 1' });
  expect(await within(region).findByText('abcd')).toBeVisible();
  expect(within(region).getByText(/PDF page 2/)).toBeVisible();
  expect(api.listChunks).toHaveBeenLastCalledWith('p1', 'd1', 'r1', 0);
});

test('shows processing progress and cancels a queued run', async () => {
  const queued = { ...run, status: 'queued' as const, chunk_count: 0, progress: 0 };
  vi.mocked(api.listDocuments).mockResolvedValue(page([{ ...doc, latest_run: queued }]));
  vi.mocked(api.listRuns).mockResolvedValue(page([queued]));
  vi.mocked(api.cancelRun).mockResolvedValue({ ...queued, status: 'cancelled' });
  render(<KnowledgeBase projectId="p1"/>);
  await userEvent.click(await screen.findByRole('button', { name: 'Manage source.txt' }));
  expect(await screen.findByText(/Waiting for a worker/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Start processing' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Cancel run' }));
  await waitFor(() => expect(api.cancelRun).toHaveBeenCalledWith('p1', 'd1', 'r1'));
  expect(await screen.findByText(/Run cancelled. In-flight parsing/)).toBeVisible();
});

test('retains upload settings errors when the document list succeeds and offers retry', async () => {
  vi.mocked(api.getSettings).mockRejectedValueOnce(new Error('Settings unavailable.')).mockResolvedValue({ max_upload_bytes: 1024 });
  render(<KnowledgeBase projectId="p1"/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Settings unavailable');
  expect(screen.getByRole('button', { name: 'Upload document' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Retry upload settings' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Upload document' })).toBeEnabled());
  expect(screen.queryByRole('alert')).toBeNull();
});
