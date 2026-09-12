import { ApiError, postJson, request } from '../../src/lib/api';

function respond(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

afterEach(() => vi.useRealTimers());

test('serializes JSON once and preserves server validation messages across features', async () => {
  const fetch = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(
      respond({ detail: [{ loc: ['body', 'chunk_size'], msg: 'Must be positive' }] }, 422),
    );
  await expect(
    postJson('/projects/project/documents/document/runs', { chunk_size: -1 }),
  ).rejects.toMatchObject({ status: 422, message: 'chunk_size: Must be positive' });
  expect(fetch).toHaveBeenCalledWith(
    '/api/projects/project/documents/document/runs',
    expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{"chunk_size":-1}',
    }),
  );
});

test('preserves a readable server error and its status', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(respond({ detail: 'Index is not ready.' }, 409));
  await expect(request('/projects/p/pipelines')).rejects.toEqual(
    new ApiError('Index is not ready.', 409),
  );
});

test('handles a non-JSON service failure without exposing its body', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response('<html>proxy failure</html>', { status: 503 }),
  );
  await expect(request('/projects')).rejects.toMatchObject({
    status: 503,
    message: 'The service is temporarily unavailable. Please try again.',
  });
});

test('keeps the timeout active while the response body is being read', async () => {
  vi.useFakeTimers();
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    async (_url, options) =>
      ({
        ok: true,
        json: () =>
          new Promise((_resolve, reject) => {
            options?.signal?.addEventListener('abort', () =>
              reject(new DOMException('Aborted', 'AbortError')),
            );
          }),
      }) as Response,
  );
  const result = request('/projects', {}, 100);
  const assertion = expect(result).rejects.toThrow('The request timed out');
  await vi.advanceTimersByTimeAsync(100);
  await assertion;
  expect(vi.getTimerCount()).toBe(0);
});

test('forwards cancellation supplied by the caller', async () => {
  const abort = new AbortController();
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(
    (_url, options) =>
      new Promise((_resolve, reject) => {
        options?.signal?.addEventListener('abort', () =>
          reject(new DOMException('Aborted', 'AbortError')),
        );
      }),
  );
  const result = request('/projects', { signal: abort.signal });
  const assertion = expect(result).rejects.toMatchObject({ name: 'AbortError' });
  abort.abort();
  await assertion;
  expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
});
