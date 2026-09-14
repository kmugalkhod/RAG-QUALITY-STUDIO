import { act, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Comparison } from '../../../src/features/experiments/components/Comparison';
import * as api from '../../../src/features/experiments/api';
import type { Detail } from '../../../src/features/experiments/model';

vi.mock('../../../src/features/experiments/api', () => ({
  getExperiment: vi.fn(),
  cancelExperiment: vi.fn(),
}));
vi.mock('../../../src/features/experiments/components/ComparisonSummary', () => ({
  ComparisonSummary: () => null,
}));
vi.mock('../../../src/features/experiments/components/QuestionComparison', () => ({
  QuestionComparison: () => null,
}));

afterEach(() => vi.useRealTimers());

it('retries a transient experiment read and displays the recovered state', async () => {
  vi.useFakeTimers();
  vi.mocked(api.getExperiment)
    .mockRejectedValueOnce(new Error('Temporary read failure'))
    .mockResolvedValue({
      id: 'experiment-1',
      name: 'Recovered comparison',
      status: 'succeeded',
      progress: 6,
      total: 6,
      cancel_requested: false,
      error: null,
      created_at: '2026-09-14T00:00:00Z',
      snapshot: {},
      items: [],
      summary: {},
    } as unknown as Detail);

  render(<Comparison projectId="project-1" experimentId="experiment-1" />);
  await act(async () => Promise.resolve());
  expect(screen.getByRole('alert')).toHaveTextContent('Temporary read failure');

  await act(async () => vi.advanceTimersByTimeAsync(2000));

  expect(api.getExperiment).toHaveBeenCalledTimes(2);
  expect(screen.getByRole('status')).toHaveTextContent('succeeded 6 / 6 results completed');
  expect(screen.queryByText('Temporary read failure')).not.toBeInTheDocument();
});
