import {
  loadAskStage,
  loadCompareStage,
  loadPrepareStage,
  primaryStage,
  type StageResult,
} from '../../../src/features/workspace/stages';

// covers: AC-6 (stage copy, counts and states in Value sourcing; single primary rule)

const projectId = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const page = (items: unknown[], total = items.length, limit = 20, offset = 0) => ({
  items,
  total,
  limit,
  offset,
});

function respond(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

type Route = (url: string) => Promise<Response>;

// Route each list request by its path segment, the way the API client calls it.
function mockApi(routes: Record<string, Route>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const url = String(input);
    const key = Object.keys(routes).find((name) => url.includes(`/${name}?`));
    if (!key) {
      throw new Error(`Unexpected request ${url}`);
    }
    return routes[key](url);
  });
}

const loaded = (state: 'empty' | 'in-progress' | 'ready'): StageResult => ({
  status: 'loaded',
  summary: { state, counts: '', status: '' },
});

describe('loadPrepareStage', () => {
  test('a project with no documents and no indexes is empty', async () => {
    mockApi({ documents: () => respond(page([])), indexes: () => respond(page([])) });
    await expect(loadPrepareStage(projectId)).resolves.toEqual({
      state: 'empty',
      counts: '0 documents · 0 ready indexes',
      status: 'No documents',
    });
  });

  test('documents without a succeeded index need indexing', async () => {
    mockApi({
      documents: () => respond(page([{}], 1)),
      indexes: () => respond(page([{ status: 'running' }, { status: 'failed' }])),
    });
    await expect(loadPrepareStage(projectId)).resolves.toEqual({
      state: 'in-progress',
      counts: '1 document · 0 ready indexes',
      status: 'Needs indexing',
    });
  });

  test('only succeeded indexes count as ready, using singular and plural copy', async () => {
    mockApi({
      documents: () => respond(page([{}, {}], 3)),
      indexes: () => respond(page([{ status: 'succeeded' }, { status: 'cancelled' }])),
    });
    await expect(loadPrepareStage(projectId)).resolves.toMatchObject({
      state: 'ready',
      counts: '3 documents · 1 ready index',
      status: 'Ready',
    });
  });

  test('a ready index from an ingestion pipeline counts as prepared with zero uploads', async () => {
    mockApi({
      documents: () => respond(page([])),
      indexes: () => respond(page([{ status: 'succeeded' }, { status: 'succeeded' }])),
    });
    await expect(loadPrepareStage(projectId)).resolves.toMatchObject({
      state: 'ready',
      counts: '0 documents · 2 ready indexes',
    });
  });

  test('counts ready indexes across every page, not just the first', async () => {
    mockApi({
      documents: () => respond(page([])),
      indexes: (url) =>
        url.includes('offset=1')
          ? respond(page([{ status: 'succeeded' }], 2, 1, 1))
          : respond(page([{ status: 'succeeded' }], 2, 1, 0)),
    });
    await expect(loadPrepareStage(projectId)).resolves.toMatchObject({
      counts: '0 documents · 2 ready indexes',
    });
  });

  test('rejects with the safe server message when a request fails', async () => {
    mockApi({
      documents: () => respond({ detail: 'Documents unavailable' }, 500),
      indexes: () => respond(page([])),
    });
    await expect(loadPrepareStage(projectId)).rejects.toThrow('Documents unavailable');
  });
});

describe('loadAskStage', () => {
  test('no answer pipelines is empty', async () => {
    mockApi({ pipelines: () => respond(page([])) });
    await expect(loadAskStage(projectId)).resolves.toEqual({
      state: 'empty',
      counts: '0 answer pipelines',
      status: 'No pipelines',
    });
  });

  test('one saved answer pipeline is ready with singular copy', async () => {
    mockApi({ pipelines: () => respond(page([{}], 1)) });
    await expect(loadAskStage(projectId)).resolves.toEqual({
      state: 'ready',
      counts: '1 answer pipeline',
      status: 'Ready',
    });
  });

  test('asks the API for answer pipelines only', async () => {
    const fetchMock = mockApi({ pipelines: () => respond(page([])) });
    await loadAskStage(projectId);
    expect(String(fetchMock.mock.calls[0][0])).toContain('answer');
  });
});

describe('loadCompareStage', () => {
  test('no datasets is empty', async () => {
    mockApi({ datasets: () => respond(page([])), experiments: () => respond(page([])) });
    await expect(loadCompareStage(projectId)).resolves.toEqual({
      state: 'empty',
      counts: '0 datasets · 0 completed runs',
      status: 'No datasets',
    });
  });

  test('a dataset without a succeeded experiment has no completed runs', async () => {
    mockApi({
      datasets: () => respond(page([{}], 1)),
      experiments: () => respond(page([{ status: 'running' }, { status: 'failed' }])),
    });
    await expect(loadCompareStage(projectId)).resolves.toEqual({
      state: 'in-progress',
      counts: '1 dataset · 0 completed runs',
      status: 'No completed runs',
    });
  });

  test('a succeeded experiment makes Compare ready', async () => {
    mockApi({
      datasets: () => respond(page([{}, {}], 2)),
      experiments: () => respond(page([{ status: 'succeeded' }])),
    });
    await expect(loadCompareStage(projectId)).resolves.toEqual({
      state: 'ready',
      counts: '2 datasets · 1 completed run',
      status: 'Ready',
    });
  });

  test('rejects when the datasets request fails', async () => {
    mockApi({
      datasets: () => respond({ detail: 'Datasets unavailable' }, 500),
      experiments: () => respond(page([])),
    });
    await expect(loadCompareStage(projectId)).rejects.toThrow('Datasets unavailable');
  });
});

describe('primaryStage', () => {
  test('returns null while any stage is still loading', () => {
    expect(
      primaryStage({
        prepare: { status: 'loading' },
        ask: loaded('empty'),
        compare: loaded('empty'),
      }),
    ).toBeNull();
  });

  test('picks the first stage that is not ready, in Prepare, Ask, Compare order', () => {
    expect(
      primaryStage({ prepare: loaded('empty'), ask: loaded('empty'), compare: loaded('empty') }),
    ).toBe('prepare');
    expect(
      primaryStage({ prepare: loaded('ready'), ask: loaded('empty'), compare: loaded('empty') }),
    ).toBe('ask');
    expect(
      primaryStage({
        prepare: loaded('ready'),
        ask: loaded('ready'),
        compare: loaded('in-progress'),
      }),
    ).toBe('compare');
  });

  test('an in progress Prepare keeps the primary even when later stages are empty', () => {
    expect(
      primaryStage({
        prepare: loaded('in-progress'),
        ask: loaded('empty'),
        compare: loaded('empty'),
      }),
    ).toBe('prepare');
  });

  test('skips a failed stage and gives the primary to the next loaded one', () => {
    expect(
      primaryStage({
        prepare: { status: 'failed', message: 'x' },
        ask: loaded('empty'),
        compare: loaded('empty'),
      }),
    ).toBe('ask');
  });

  test('returns null when every stage is ready but Compare itself failed', () => {
    expect(
      primaryStage({
        prepare: loaded('ready'),
        ask: loaded('ready'),
        compare: { status: 'failed', message: 'x' },
      }),
    ).toBeNull();
  });

  test('returns null when every stage failed', () => {
    const failed: StageResult = { status: 'failed', message: 'x' };
    expect(primaryStage({ prepare: failed, ask: failed, compare: failed })).toBeNull();
  });
});
