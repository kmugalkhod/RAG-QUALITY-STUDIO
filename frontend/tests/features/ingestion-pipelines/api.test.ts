import {
  cancelIngestionRun,
  cancelSourcePreview,
  createIngestionSchedule,
  createIngestionPipeline,
  createIngestionPipelineVersion,
  getIngestionRun,
  getExtractionCapabilities,
  getSourcePreview,
  listIngestionPipelineVersions,
  listIngestionRuns,
  listIngestionRunItems,
  listContentBlocks,
  listContentDerivations,
  listCleaningDiff,
  listProcessingChunks,
  listSourcePreviewItems,
  listIngestionSchedules,
  previewIngestion,
  startIngestionRun,
  runIngestionSchedule,
  updateIngestionSchedule,
  contentPageThumbnailUrl,
} from '../../../src/features/ingestion-pipelines/api';
import type {
  IngestionPipelineDraft,
  IngestionSchedule,
} from '../../../src/features/ingestion-pipelines/model';

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

test('keeps preview and durable run operations distinct', async () => {
  await previewIngestion('project', draft.execution);
  await getSourcePreview('project', 'preview');
  await listSourcePreviewItems('project', 'preview');
  await cancelSourcePreview('project', 'preview');
  await listIngestionPipelineVersions('project', 'pipeline');
  await listIngestionRuns('project', 'version');
  await startIngestionRun('project', 'pipeline', 'version', {
    source_input: { kind: 'refresh' },
  });
  await getIngestionRun('project', 'run');
  await listIngestionRunItems('project', 'run');
  await cancelIngestionRun('project', 'run');

  expect(fetch).toHaveBeenNthCalledWith(
    1,
    '/api/projects/project/ingestion-previews',
    expect.objectContaining({ method: 'POST' }),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    7,
    '/api/projects/project/pipelines/pipeline/versions/version/ingestion-runs',
    expect.objectContaining({ method: 'POST' }),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    10,
    '/api/projects/project/ingestion-runs/run/cancel',
    expect.objectContaining({ method: 'POST' }),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    4,
    '/api/projects/project/source-previews/preview/cancel',
    expect.objectContaining({ method: 'POST' }),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    6,
    '/api/projects/project/ingestion-runs?pipeline_version_id=version&limit=20&offset=0',
    expect.anything(),
  );
});

test('uses project-scoped canonical content inspection endpoints', async () => {
  await getExtractionCapabilities('project');
  await listContentDerivations('project', 'processing');
  await listContentBlocks('project', 'derivation', 20);
  await listCleaningDiff('project', 'processing', 40);
  await listProcessingChunks('project', 'processing', 60);

  expect(fetch).toHaveBeenNthCalledWith(
    1,
    '/api/projects/project/ingestion-capabilities',
    expect.anything(),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    2,
    '/api/projects/project/processing-runs/processing/derivations',
    expect.anything(),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    3,
    '/api/projects/project/content-derivations/derivation/blocks?offset=20',
    expect.anything(),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    4,
    '/api/projects/project/processing-runs/processing/cleaning-diff?offset=40',
    expect.anything(),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    5,
    '/api/projects/project/processing-runs/processing/chunks?offset=60',
    expect.anything(),
  );
  expect(contentPageThumbnailUrl('project', 'processing', 2)).toBe(
    '/api/projects/project/processing-runs/processing/pages/2/thumbnail',
  );
});

test('uses project-scoped schedule endpoints and paused-by-default payloads', async () => {
  const schedule = {
    id: 'schedule',
    name: 'Daily',
    cadence: { kind: 'interval', minutes: 60 },
    status: 'paused',
  } as IngestionSchedule;
  await listIngestionSchedules('project', 20);
  await createIngestionSchedule('project', {
    name: 'Daily',
    pipeline_id: 'pipeline',
    pipeline_version_id: 'version',
    cadence: { kind: 'interval', minutes: 60 },
    enabled: false,
  });
  await updateIngestionSchedule('project', schedule, true);
  await runIngestionSchedule('project', 'schedule');

  expect(fetch).toHaveBeenNthCalledWith(
    1,
    '/api/projects/project/ingestion-schedules?offset=20',
    expect.anything(),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    2,
    '/api/projects/project/ingestion-schedules',
    expect.objectContaining({ body: expect.stringContaining('"enabled":false') }),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    4,
    '/api/projects/project/ingestion-schedules/schedule/run',
    expect.objectContaining({ method: 'POST' }),
  );
});
