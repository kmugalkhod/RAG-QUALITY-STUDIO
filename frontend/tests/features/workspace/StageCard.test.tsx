import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StageCard } from '../../../src/features/workspace/components/StageCard';
import type { StageResult } from '../../../src/features/workspace/stages';

// covers: AC-6 (stage card copy, states, one action, per card Retry)

function renderCard(
  result: StageResult,
  overrides: { primary?: boolean; onRetry?: () => void } = {},
) {
  return render(
    <ul>
      <StageCard
        step={2}
        title="Ask a question"
        description="Try a saved answer pipeline."
        result={result}
        actionLabel="Open Playground"
        href="#/projects/p/playground"
        primary={overrides.primary ?? false}
        onRetry={overrides.onRetry ?? vi.fn()}
      />
    </ul>,
  );
}

const loaded: StageResult = {
  status: 'loaded',
  summary: { state: 'ready', counts: '1 answer pipeline', status: 'Ready' },
};

test('the card is a list item named by its title and shows its step', () => {
  renderCard(loaded);
  const card = screen.getByRole('listitem', { name: 'Ask a question' });
  expect(within(card).getByText('Step 2')).toBeVisible();
  expect(within(card).getByText('Try a saved answer pipeline.')).toBeVisible();
});

test('a loaded card shows its status, counts and a link to its destination', () => {
  renderCard(loaded);
  expect(screen.getByText('Ready')).toBeVisible();
  expect(screen.getByText('1 answer pipeline')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Open Playground' })).toHaveAttribute(
    'href',
    '#/projects/p/playground',
  );
});

test('the action is primary only when the card carries the primary', () => {
  const { unmount } = renderCard(loaded, { primary: true });
  expect(screen.getByRole('link', { name: 'Open Playground' })).toHaveAttribute(
    'data-variant',
    'primary',
  );
  unmount();
  renderCard(loaded, { primary: false });
  expect(screen.getByRole('link', { name: 'Open Playground' })).toHaveAttribute(
    'data-variant',
    'secondary',
  );
});

test('while loading, the card announces loading and offers no action or status', () => {
  renderCard({ status: 'loading' });
  expect(screen.getByRole('status')).toHaveTextContent(/Loading ask a question status/);
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
  expect(screen.queryByText('Ready')).not.toBeInTheDocument();
});

test('a failed card shows the safe message and retries without an action link', async () => {
  const user = userEvent.setup();
  const onRetry = vi.fn();
  renderCard({ status: 'failed', message: 'Pipelines unavailable' }, { onRetry, primary: true });
  expect(screen.getByText('Could not load counts')).toBeVisible();
  expect(screen.getByText('Pipelines unavailable')).toBeVisible();
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Retry' }));
  expect(onRetry).toHaveBeenCalledTimes(1);
});
