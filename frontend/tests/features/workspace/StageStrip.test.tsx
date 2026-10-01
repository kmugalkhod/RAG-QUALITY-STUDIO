import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StageStrip } from '../../../src/features/workspace/components/StageStrip';
import { primaryStage } from '../../../src/features/workspace/stages';

const projectId = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const page = (items: unknown[], total = items.length) => ({ items, total, limit: 20, offset: 0 });

function respond(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

// Route each list request by path so the three stages can be controlled independently.
function mockApi(overrides: Record<string, () => Promise<Response>> = {}) {
  const defaults: Record<string, () => Promise<Response>> = {
    documents: () => respond(page([])),
    indexes: () => respond(page([])),
    pipelines: () => respond(page([])),
    datasets: () => respond(page([])),
    experiments: () => respond(page([])),
  };
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const path = String(input);
    const key = Object.keys(defaults).find((name) => path.includes(`/${name}?`))!;
    return (overrides[key] ?? defaults[key])();
  });
}

function primaryButtons() {
  return screen
    .queryAllByRole('link')
    .filter((link) => link.getAttribute('data-variant') === 'primary');
}

test('a fresh project gives Prepare the only primary button', async () => {
  mockApi();
  render(<StageStrip projectId={projectId} />);
  const prepare = await screen.findByRole('listitem', { name: 'Prepare knowledge' });
  expect(await within(prepare).findByText('0 documents · 0 ready indexes')).toBeVisible();
  expect(within(prepare).getByText('No documents')).toBeVisible();
  await screen.findByText('0 datasets · 0 completed runs');
  expect(primaryButtons()).toHaveLength(1);
  expect(within(prepare).getByRole('link', { name: 'Upload documents' })).toHaveAttribute(
    'data-variant',
    'primary',
  );
});

test('a ready index moves the primary button to Ask', async () => {
  mockApi({
    documents: () => respond(page([{}], 1)),
    indexes: () => respond(page([{ status: 'succeeded' }, { status: 'failed' }])),
  });
  render(<StageStrip projectId={projectId} />);
  const ask = await screen.findByRole('listitem', { name: 'Ask a question' });
  await screen.findByText('1 document · 1 ready index');
  await screen.findByText('0 answer pipelines');
  await screen.findByText('0 datasets · 0 completed runs');
  expect(primaryButtons()).toHaveLength(1);
  expect(within(ask).getByRole('link', { name: 'Ask a question' })).toHaveAttribute(
    'data-variant',
    'primary',
  );
});

test('a failed datasets request shows Retry on Compare only and retries it', async () => {
  let fail = true;
  mockApi({
    datasets: () => (fail ? respond({ detail: 'Datasets unavailable' }, 500) : respond(page([]))),
  });
  render(<StageStrip projectId={projectId} />);
  const compare = await screen.findByRole('listitem', { name: 'Compare results' });
  expect(await within(compare).findByText('Datasets unavailable')).toBeVisible();
  expect(screen.getAllByRole('button', { name: 'Retry' })).toHaveLength(1);
  fail = false;
  await userEvent.click(within(compare).getByRole('button', { name: 'Retry' }));
  expect(await within(compare).findByText('0 datasets · 0 completed runs')).toBeVisible();
});

test('no stage is primary until every request settles, then Compare when all are ready', () => {
  const ready = {
    status: 'loaded' as const,
    summary: { state: 'ready' as const, counts: '', status: 'Ready' },
  };
  expect(primaryStage({ prepare: ready, ask: { status: 'loading' }, compare: ready })).toBeNull();
  expect(primaryStage({ prepare: ready, ask: ready, compare: ready })).toBe('compare');
  expect(
    primaryStage({ prepare: { status: 'failed', message: 'x' }, ask: ready, compare: ready }),
  ).toBe('compare');
});
