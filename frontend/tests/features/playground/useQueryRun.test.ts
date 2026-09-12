import { act, renderHook } from '@testing-library/react';
import { getQueryRun } from '../../../src/features/playground/api';
import type { QueryRun } from '../../../src/features/playground/model';
import { useQueryRun } from '../../../src/features/playground/useQueryRun';

vi.mock('../../../src/features/playground/api', () => ({ getQueryRun: vi.fn() }));
const running: QueryRun = {
  id: 'first',
  project_id: 'project',
  index_id: 'index',
  index_version: 1,
  question: 'Question?',
  answer: null,
  status: 'running',
  error: null,
  created_at: '2026-09-12',
  snapshot: {
    top_k: 5,
    evidence: [],
    prompt_version: 'v1',
    retrieval_ms: null,
    generation_ms: null,
    total_ms: null,
    usage: null,
    cost_usd: null,
    cost_basis: null,
  },
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(getQueryRun).mockReset();
});
afterEach(() => vi.useRealTimers());

test('waits for an in-flight read and stops polling when the answer finishes', async () => {
  let finish!: (run: QueryRun) => void;
  vi.mocked(getQueryRun).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const { result, unmount } = renderHook(() => useQueryRun('project'));
  act(() => result.current.setRun(running));
  await act(() => vi.advanceTimersByTimeAsync(5000));
  expect(getQueryRun).toHaveBeenCalledTimes(1);
  await act(async () => finish({ ...running, status: 'succeeded', answer: 'Answer' }));
  await act(() => vi.advanceTimersByTimeAsync(5000));
  expect(result.current.run?.answer).toBe('Answer');
  expect(result.current.completedRuns).toBe(1);
  expect(getQueryRun).toHaveBeenCalledTimes(1);
  unmount();
});

test('ignores an old response after selecting another run and cleans up its timer', async () => {
  let finish!: (run: QueryRun) => void;
  vi.mocked(getQueryRun).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const { result, unmount } = renderHook(() => useQueryRun('project'));
  act(() => result.current.setRun(running));
  await act(() => vi.advanceTimersByTimeAsync(1000));
  act(() => result.current.setRun({ ...running, id: 'second' }));
  await act(async () => finish({ ...running, status: 'succeeded', answer: 'Old answer' }));
  expect(result.current.run?.id).toBe('second');
  expect(result.current.completedRuns).toBe(0);
  unmount();
  await vi.advanceTimersByTimeAsync(5000);
  expect(getQueryRun).toHaveBeenCalledTimes(1);
});

test('shows a polling failure, retries, and clears it after recovery', async () => {
  vi.mocked(getQueryRun)
    .mockRejectedValueOnce(new Error('Connection interrupted'))
    .mockResolvedValueOnce({ ...running, status: 'failed', error: 'Generation failed' });
  const { result, unmount } = renderHook(() => useQueryRun('project'));
  act(() => result.current.setRun(running));
  await act(() => vi.advanceTimersByTimeAsync(1000));
  expect(result.current.pollError).toBe('Connection interrupted');
  expect(result.current.run?.status).toBe('running');
  await act(() => vi.advanceTimersByTimeAsync(1000));
  expect(result.current.pollError).toBe('');
  expect(result.current.run?.status).toBe('failed');
  expect(result.current.completedRuns).toBe(1);
  unmount();
});
