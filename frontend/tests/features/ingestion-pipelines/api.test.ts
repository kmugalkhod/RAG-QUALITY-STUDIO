import {
  createIngestionPipeline,
  createIngestionPipelineVersion,
} from '../../../src/features/ingestion-pipelines/api';
import type { IngestionPipelineDraft } from '../../../src/features/ingestion-pipelines/model';

const draft = {
  kind: 'ingestion',
  name: 'Sources',
  execution: { schema_version: 1, nodes: [], edges: [] },
  layout: { positions: {} },
} satisfies IngestionPipelineDraft;

beforeEach(() => vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response('{}')));

test('sends explicit ingestion kind for create and immutable-version operations', async () => {
  await createIngestionPipeline('project', draft);
  await createIngestionPipelineVersion('project', 'pipeline', draft);
  expect(fetch).toHaveBeenNthCalledWith(
    1,
    '/api/projects/project/pipelines',
    expect.objectContaining({ method: 'POST', body: JSON.stringify(draft) }),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    2,
    '/api/projects/project/pipelines/pipeline/versions',
    expect.objectContaining({ method: 'POST', body: JSON.stringify(draft) }),
  );
});
