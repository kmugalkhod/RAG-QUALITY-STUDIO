import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DisconnectedBanner } from '../../src/app/DisconnectedBanner';
import { markUnreachable, resetConnection } from '../../src/lib/connection';

beforeEach(() => resetConnection());

test('stays empty while the server is reachable', () => {
  render(<DisconnectedBanner />);
  expect(screen.getByRole('status')).toBeEmptyDOMElement();
});

test('retries readiness, shows Checking… and clears on a 200', async () => {
  let resolve!: (response: Response) => void;
  const fetch = vi
    .spyOn(globalThis, 'fetch')
    .mockReturnValue(new Promise((done) => (resolve = done)));
  render(<DisconnectedBanner />);
  act(() => markUnreachable('The service is temporarily unavailable. Please try again.'));
  expect(screen.getByText('Cannot reach the server')).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent('No successful response yet');

  await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
  expect(fetch).toHaveBeenCalledWith('/api/ready', expect.anything());
  expect(screen.getByText('Checking…')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Retry' })).toHaveAttribute('aria-busy', 'true');

  await act(async () => resolve(new Response('{"status":"ok"}', { status: 200 })));
  expect(screen.getByRole('status')).toBeEmptyDOMElement();
});

test('polls readiness 5 seconds after the last response and keeps failing to unreachable', async () => {
  vi.useFakeTimers();
  const fetch = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(new Response('{}', { status: 500 }));
  render(<DisconnectedBanner />);
  act(() => markUnreachable('Could not reach the server.'));
  await act(async () => vi.advanceTimersByTimeAsync(4999));
  expect(fetch).not.toHaveBeenCalled();
  await act(async () => vi.advanceTimersByTimeAsync(1));
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(screen.getByText('Cannot reach the server')).toBeVisible();
  vi.useRealTimers();
});
