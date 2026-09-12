import {
  createPipeline,
  createPipelineVersion,
  previewPipeline,
  runPipelineVersion,
} from '../../../src/features/pipelines/api';
import { createPipelineDraft } from '../../../src/features/pipelines/pipelineTemplate';

const draft = createPipelineDraft(undefined, 'Support');

beforeEach(() => vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response('{}')));

test('creates a pipeline and appends a version through distinct endpoints', async () => {
  await createPipeline('project', draft);
  await createPipelineVersion('project', 'pipeline', draft);
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

test('runs the exact saved version and question', async () => {
  await runPipelineVersion('project', 'pipeline', 'version-2', 'What changed?');
  expect(fetch).toHaveBeenCalledWith(
    '/api/projects/project/pipelines/pipeline/versions/version-2/runs',
    expect.objectContaining({ body: JSON.stringify({ question: 'What changed?' }) }),
  );
});

test('records preview provenance only when based on a saved version', async () => {
  await previewPipeline('project', draft.execution, 'Question?');
  await previewPipeline('project', draft.execution, 'Question?', {
    pipeline_id: 'pipeline',
    id: 'version',
  });
  const calls = vi.mocked(fetch).mock.calls;
  expect(JSON.parse(calls[0][1]?.body as string)).toEqual({
    execution: draft.execution,
    question: 'Question?',
  });
  expect(JSON.parse(calls[1][1]?.body as string)).toEqual({
    execution: draft.execution,
    question: 'Question?',
    base_pipeline_id: 'pipeline',
    base_version_id: 'version',
  });
});
