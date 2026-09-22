import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';

import { SourceSnapshotsPanel } from '../../../../src/features/documents/components/SourceSnapshotsPanel';
import * as api from '../../../../src/features/documents/indexApi';
import type { SourceSnapshot } from '../../../../src/features/documents/model';
import type {
  IngestionPipelineVersion,
  IngestionRun,
} from '../../../../src/features/ingestion-pipelines/model';

vi.mock('../../../../src/features/documents/indexApi');

const page = <T,>(items: T[]) => ({ items, total: items.length, limit: 20, offset: 0 });

const snapshot: SourceSnapshot = {
  id: 'snapshot-1',
  project_id: 'project-1',
  source_kind: 'website',
  source_config_hash: 'hash',
  source_identity: { origins: ['https://example.com'], selection_modes: ['single_url'] },
  connector_version: 'website-v1',
  snapshot_number: 2,
  status: 'ready',
  discovered_count: 1,
  included_count: 1,
  excluded_count: 0,
  duplicate_count: 0,
  failed_count: 0,
  new_count: 1,
  changed_count: 0,
  unchanged_count: 0,
  removed_count: 0,
  total_bytes: 120,
  creating_ingestion_run_id: 'collection-run',
  collection_pipeline: {
    id: 'pipeline-1',
    version_id: 'pipeline-version-1',
    name: 'Website collection',
    version: 3,
  },
  downstream_index_count: 0,
  error: null,
  created_at: '2026-09-20T00:00:00Z',
  collected_at: '2026-09-20T00:01:00Z',
};

const version: IngestionPipelineVersion = {
  id: 'pipeline-version-1',
  pipeline_id: 'pipeline-1',
  project_id: 'project-1',
  version: 3,
  created_at: '2026-09-20T00:00:00Z',
  kind: 'ingestion',
  name: 'Website collection',
  execution: {
    schema_version: 1,
    nodes: [
      {
        id: 'source',
        type: 'source',
        config: {
          kind: 'website',
          selection: { mode: 'single_url', url: 'https://example.com' },
          allowed_origins: ['https://example.com'],
          max_pages: 10,
          max_depth: 1,
          max_response_bytes: 1000,
          max_total_bytes: 10000,
          request_timeout_seconds: 5,
          deadline_seconds: 30,
          concurrency: 1,
          requests_per_second: 1,
          redirect_limit: 2,
          user_agent: 'test',
        },
      },
      { id: 'chunk', type: 'chunk', size: 800, overlap: 80 },
      {
        id: 'embed',
        type: 'embed',
        provider: 'openrouter',
        model: 'embedding-model',
        dimensions: 1536,
        config_version: '1',
      },
    ],
    edges: [],
  },
  layout: { positions: {} },
};

beforeEach(() => {
  vi.resetAllMocks();
  window.history.replaceState(
    null,
    '',
    '#/projects/project-1/knowledge-base?view=indexes&mode=snapshots&snapshot=snapshot-1',
  );
  vi.mocked(api.listSourceSnapshots).mockResolvedValue(page([snapshot]));
  vi.mocked(api.getSourceSnapshot).mockResolvedValue(snapshot);
  vi.mocked(api.listSourceSnapshotItems).mockResolvedValue(
    page([
      {
        ordinal: 0,
        source_node_id: 'source',
        source_item_id: 'item-1',
        source_revision_id: 'revision-1',
        inclusion_state: 'included',
        canonical_location: 'https://example.com/page',
        media_type: 'text/html',
        size_bytes: 120,
        fetched_at: '2026-09-20T00:00:30Z',
        provider_revision: null,
        provenance: {},
      },
    ]),
  );
  vi.mocked(api.listSourceSnapshotIndexes).mockResolvedValue(page([]));
  vi.mocked(api.listIngestionPipelines).mockResolvedValue(
    page([{ id: 'pipeline-1', name: 'Website collection', kind: 'ingestion' }]),
  );
  vi.mocked(api.listIngestionPipelineVersions).mockResolvedValue(page([version]));
  vi.mocked(api.listKnowledgeSets).mockResolvedValue(page([]));
});

test('restores a linked snapshot and shows exact reusable membership', async () => {
  render(<SourceSnapshotsPanel projectId="project-1" />);

  expect(await screen.findByRole('heading', { name: 'Source snapshot 2' })).toBeVisible();
  expect(await screen.findByText('https://example.com/page')).toBeVisible();
  expect(screen.getByText('1 exact revisions')).toBeVisible();
  expect(screen.getByText('No index has been built from this snapshot yet.')).toBeVisible();
});

test('starts a new independently named index from the selected snapshot', async () => {
  const queued = {
    id: 'build-run',
    status: 'queued',
    stage: 'discovering',
    progress: 0,
  } as IngestionRun;
  vi.mocked(api.startSnapshotBuild).mockResolvedValue(queued);
  vi.mocked(api.getIngestionRun).mockResolvedValue({ ...queued, status: 'running' });
  render(<SourceSnapshotsPanel projectId="project-1" />);

  await userEvent.click(await screen.findByRole('button', { name: 'Build index variant' }));
  await userEvent.type(screen.getByLabelText('Index name'), 'Small chunks');
  await userEvent.click(screen.getByRole('button', { name: 'Build from source snapshot' }));

  await waitFor(() =>
    expect(api.startSnapshotBuild).toHaveBeenCalledWith(
      'project-1',
      'pipeline-1',
      'pipeline-version-1',
      'snapshot-1',
      { kind: 'new', name: 'Small chunks' },
    ),
  );
  expect(screen.getByText(/website will not be requested again/i)).toBeVisible();
});
