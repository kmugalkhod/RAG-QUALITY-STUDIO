import {
  uploadDocument,
  startProcessingRun,
  cancelProcessingRun,
  listDocumentChunks,
} from '../../../src/features/documents/api';

beforeEach(() => vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response('{}')));

test('uploads the file as multipart without overriding the browser boundary', async () => {
  const file = new File(['Source text'], 'source.txt', { type: 'text/plain' });
  await uploadDocument('project', file);
  const [url, options] = vi.mocked(fetch).mock.calls[0];
  expect(url).toBe('/api/projects/project/documents');
  expect(options?.body).toBeInstanceOf(FormData);
  expect((options?.body as FormData).get('file')).toBe(file);
  expect(options?.headers).toBeUndefined();
});

test('scopes processing, cancellation and chunk reads to their project and document', async () => {
  await startProcessingRun('project', 'document', 800, 80);
  await cancelProcessingRun('project', 'document', 'run');
  await listDocumentChunks('project', 'document', 'run', 20);
  expect(fetch).toHaveBeenNthCalledWith(
    1,
    '/api/projects/project/documents/document/runs',
    expect.objectContaining({ method: 'POST', body: '{"chunk_size":800,"overlap":80}' }),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    2,
    '/api/projects/project/documents/document/runs/run/cancel',
    expect.objectContaining({ method: 'POST' }),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    3,
    '/api/projects/project/documents/document/runs/run/chunks?offset=20',
    expect.anything(),
  );
});
