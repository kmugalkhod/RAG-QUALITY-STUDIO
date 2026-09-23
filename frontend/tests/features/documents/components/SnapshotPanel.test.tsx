import { render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

import { SnapshotPanel } from '../../../../src/features/documents/components/SnapshotPanel';
import * as indexApi from '../../../../src/features/documents/indexApi';
import type { SourceSnapshot, SourceSnapshotIndex } from '../../../../src/features/documents/model';
import * as pipelineApi from '../../../../src/features/pipelines/api';
import * as ingestionApi from '../../../../src/features/ingestion-pipelines/api';

vi.mock('../../../../src/features/documents/indexApi');
vi.mock('../../../../src/features/pipelines/api');
vi.mock('../../../../src/features/ingestion-pipelines/api');

const page = <T,>(items: T[]) => ({ items, total: items.length, limit: 20, offset: 0 });
const snapshot: SourceSnapshot = {
  id: 'snapshot-1',
  project_id: 'project-1',
  source_kind: 'website',
  source_identity: { origins: ['https://example.com'], mode: 'crawl' },
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
  creating_ingestion_run_id: 'run-1',
  downstream_index_count: 1,
  error: null,
  created_at: '2026-09-20T00:00:00Z',
  collected_at: '2026-09-20T00:01:00Z',
};
const readyIndex: SourceSnapshotIndex = {
  id: 'index-1',
  knowledge_set_id: 'set-1',
  knowledge_set_name: 'Website knowledge',
  version: 2,
  status: 'succeeded',
  chunk_count: 8,
  embedded_count: 8,
  is_current: true,
  ingestion_pipeline_id: 'pipeline-1',
  ingestion_pipeline_version_id: 'pipeline-version-1',
  ingestion_pipeline_name: 'Website collection',
  ingestion_pipeline_version: 3,
  created_at: '2026-09-20T00:02:00Z',
};

beforeEach(() => {
  vi.resetAllMocks();
  window.history.replaceState(
    null,
    '',
    '#/projects/project-1/knowledge-base?view=indexes&mode=snapshots&snapshot=snapshot-1',
  );
  vi.mocked(indexApi.getSourceSnapshot).mockResolvedValue(snapshot);
  vi.mocked(indexApi.listSourceSnapshots).mockResolvedValue(page([snapshot]));
  vi.mocked(indexApi.listSourceSnapshotItems).mockResolvedValue(page([]));
  vi.mocked(indexApi.listSourceSnapshotIndexes).mockResolvedValue(page([readyIndex]));
  vi.mocked(indexApi.listKnowledgeSets).mockResolvedValue(page([]));
  vi.mocked(pipelineApi.listPipelines).mockResolvedValue(page([]));
  vi.mocked(ingestionApi.listIngestionPipelineVersions).mockResolvedValue(page([]));
});

test('opens an answer pipeline with the current published index already selected', async () => {
  render(<SnapshotPanel projectId="project-1" />);

  expect(
    await screen.findByRole('link', { name: 'Use current index in answer pipeline' }),
  ).toHaveAttribute('href', '#/projects/project-1/pipelines/new?index=index-1');
  expect(screen.getByRole('heading', { name: 'Create another index version' })).toBeVisible();
  expect(screen.getByText(/This is optional/)).toBeVisible();
});
