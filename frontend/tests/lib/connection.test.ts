import { request } from '../../src/lib/api';
import { getConnection, resetConnection } from '../../src/lib/connection';

function respond(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

beforeEach(() => resetConnection());
afterEach(() => vi.useRealTimers());

test('a gateway status marks the server unreachable and a 2xx clears it', async () => {
  const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(respond({}, 502));
  await expect(request('/projects')).rejects.toMatchObject({ status: 502 });
  expect(getConnection()).toMatchObject({ status: 'unreachable', lastOkAt: null });
  expect(getConnection().message).not.toBe('');

  fetch.mockResolvedValueOnce(respond({ items: [] }));
  await request('/projects');
  expect(getConnection().status).toBe('ok');
  expect(getConnection().lastOkAt).toEqual(expect.any(Number));
});

test('a network failure marks it unreachable but other errors and cancels do not', async () => {
  const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(respond({}, 500));
  await expect(request('/projects')).rejects.toMatchObject({ status: 500 });
  expect(getConnection().status).toBe('ok');

  const abort = new AbortController();
  fetch.mockImplementationOnce(() => {
    abort.abort();
    return Promise.reject(new DOMException('Aborted', 'AbortError'));
  });
  await expect(request('/projects', { signal: abort.signal })).rejects.toThrow();
  expect(getConnection().status).toBe('ok');

  fetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));
  await expect(request('/projects')).rejects.toThrow('Could not reach the server');
  expect(getConnection()).toMatchObject({
    status: 'unreachable',
    message: 'Could not reach the server. Check your connection and try again.',
  });
});

test('the 12 second timeout marks it unreachable', async () => {
  vi.useFakeTimers();
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    (_path, init) =>
      new Promise((_resolve, reject) =>
        init?.signal?.addEventListener('abort', () => reject(new DOMException('', 'AbortError'))),
      ),
  );
  const result = request('/projects');
  const assertion = expect(result).rejects.toThrow('The request timed out');
  await vi.advanceTimersByTimeAsync(12000);
  await assertion;
  expect(getConnection().status).toBe('unreachable');
});
