import {
  ingestionNodeExecutionStates,
  ingestionRunDisplayStatus,
} from '../../../src/features/ingestion-pipelines/executionState';
import type { IngestionNode, IngestionRun } from '../../../src/features/ingestion-pipelines/model';

const nodes: IngestionNode[] = [
  { id: 'source', type: 'source', config: { kind: 'existing_files', document_ids: [] } },
  { id: 'extract', type: 'extract', strategy: 'media_type_registry', config_version: '1' },
  {
    id: 'clean',
    type: 'clean',
    normalize_whitespace: true,
    repeated_boilerplate: [],
    minimum_text_chars: 1,
    maximum_text_chars: 1000,
    exact_content_deduplication: true,
  },
  {
    id: 'chunk',
    type: 'chunk',
    algorithm: 'character_window',
    unit: 'characters',
    size: 1000,
    overlap: 100,
    config_version: '1',
  },
  {
    id: 'embed',
    type: 'embed',
    provider: 'test',
    model: 'test',
    dimensions: 3,
    config_version: '1',
  },
  { id: 'publish', type: 'publish_index', knowledge_set_name: 'Knowledge' },
];

const run: IngestionRun = {
  id: 'run',
  project_id: 'project',
  pipeline_version_id: 'version',
  knowledge_set_id: 'set',
  knowledge_set_name: 'Knowledge',
  schedule_id: null,
  source_snapshot_id: null,
  trigger_kind: 'manual',
  status: 'running',
  stage: 'discovering',
  progress: 5,
  discovered_count: 0,
  processed_count: 0,
  failed_count: 0,
  new_count: 0,
  changed_count: 0,
  unchanged_count: 0,
  removed_count: 0,
  chunk_count: 10,
  embedded_count: 0,
  published_count: 0,
  attempts: 1,
  failures: 0,
  node_states: [],
  error: null,
  published_index_id: null,
  published_index_version: null,
  created_at: '2026-09-23T00:00:00Z',
  updated_at: '2026-09-23T00:00:00Z',
  started_at: '2026-09-23T00:00:00Z',
  finished_at: null,
};

test('advances the active node only when the durable backend checkpoint advances', () => {
  expect(ingestionNodeExecutionStates(run, nodes)).toMatchObject({
    source: 'running',
    extract: 'queued',
  });
  expect(
    ingestionNodeExecutionStates({ ...run, stage: 'processing', progress: 20 }, nodes),
  ).toMatchObject({ source: 'succeeded', extract: 'running', clean: 'queued' });
  expect(
    ingestionNodeExecutionStates(
      { ...run, stage: 'indexing', progress: 70, embedded_count: 5 },
      nodes,
    ),
  ).toMatchObject({ chunk: 'succeeded', embed: 'running', publish: 'queued' });
  expect(
    ingestionNodeExecutionStates(
      { ...run, stage: 'indexing', progress: 99, embedded_count: 10 },
      nodes,
    ),
  ).toMatchObject({ embed: 'succeeded', publish: 'running' });
});

test('uses persisted per-node checkpoints without inferring from broad run stages', () => {
  const node_states = nodes.map((node, ordinal) => ({
    node_id: node.id,
    node_type: node.type,
    ordinal,
    status: (ordinal < 2 ? 'succeeded' : ordinal === 2 ? 'running' : 'queued') as
      | 'queued'
      | 'running'
      | 'succeeded',
    started_at: ordinal <= 2 ? '2026-09-23T00:00:00Z' : null,
    finished_at: ordinal < 2 ? '2026-09-23T00:00:01Z' : null,
  }));

  expect(
    ingestionNodeExecutionStates({ ...run, stage: 'processing', progress: 1, node_states }, nodes),
  ).toEqual({
    source: 'succeeded',
    extract: 'succeeded',
    clean: 'running',
    chunk: 'queued',
    embed: 'queued',
    publish: 'queued',
  });
});

test.each(['queued', 'failed', 'cancelled'] as const)(
  'uses the real %s run outcome for the checkpoint node',
  (status) => {
    expect(
      ingestionNodeExecutionStates({ ...run, status, stage: 'indexing', embedded_count: 3 }, nodes),
    ).toMatchObject({ chunk: 'succeeded', embed: status, publish: 'queued' });
  },
);

test('keeps every node complete after successful publication', () => {
  expect(
    Object.values(
      ingestionNodeExecutionStates(
        {
          ...run,
          status: 'succeeded',
          stage: 'complete',
          progress: 100,
          embedded_count: 10,
          published_count: 1,
        },
        nodes,
      ),
    ),
  ).toEqual(Array(nodes.length).fill('succeeded'));
});

test('shows a running run-level state while a re-queued downstream worker is active', () => {
  expect(
    ingestionRunDisplayStatus({
      ...run,
      status: 'queued',
      stage: 'indexing',
      node_states: nodes.map((node, ordinal) => ({
        node_id: node.id,
        node_type: node.type,
        ordinal,
        status: ordinal < 4 ? 'succeeded' : ordinal === 4 ? 'running' : 'queued',
        started_at: ordinal <= 4 ? '2026-09-23T00:00:00Z' : null,
        finished_at: ordinal < 4 ? '2026-09-23T00:00:01Z' : null,
      })),
    }),
  ).toBe('running');
});

test.each(['succeeded', 'failed', 'cancelled'] as const)(
  'keeps the terminal %s run outcome authoritative',
  (status) => {
    expect(
      ingestionRunDisplayStatus({
        ...run,
        status,
        node_states: [
          {
            node_id: 'source',
            node_type: 'source',
            ordinal: 0,
            status: 'running',
            started_at: '2026-09-23T00:00:00Z',
            finished_at: null,
          },
        ],
      }),
    ).toBe(status);
  },
);
