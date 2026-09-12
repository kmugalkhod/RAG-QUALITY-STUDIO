import {
  createConnection,
  getConnectionSettings,
  listConnections,
  rewrapConnection,
  rotateConnection,
  testConnection,
} from '../../../src/features/connections/api';

beforeEach(() => vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response('{}')));

test('keeps source credentials in POST bodies and out of every URL', async () => {
  const secret = 'body-only-private-value';
  const credentials = {
    kind: 'notion' as const,
    integration_token: secret,
  };
  await getConnectionSettings('project');
  await listConnections('project');
  await createConnection('project', 'Wiki', credentials);
  await rotateConnection('project', 'connection', credentials);
  await testConnection('project', 'connection');
  await rewrapConnection('project', 'connection');
  for (const [url] of vi.mocked(fetch).mock.calls) {
    expect(String(url)).not.toContain(secret);
  }
  expect(vi.mocked(fetch).mock.calls[2][1]?.body).toBe(
    JSON.stringify({ name: 'Wiki', credentials }),
  );
  expect(vi.mocked(fetch).mock.calls[3][1]?.body).toBe(JSON.stringify({ credentials }));
});
