import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import { ComparisonSummary } from '../../../src/features/experiments/components/ComparisonSummary';
import { ExperimentForm } from '../../../src/features/experiments/components/ExperimentForm';
import type { Detail } from '../../../src/features/experiments/model';
import type { IndexVersion } from '../../../src/features/documents/model';
import type { PipelineVersion } from '../../../src/features/pipelines/model';

const pipeline = (id: string, indexId: string): PipelineVersion => ({
  id,
  pipeline_id: `pipeline-${id}`,
  project_id: 'project-1',
  name: `Pipeline ${id}`,
  version: 1,
  created_at: '2026-09-22T00:00:00Z',
  execution: {
    schema_version: 2,
    nodes: [
      { id: 'retriever', type: 'retriever', index_id: indexId, top_k: 5 },
      {
        id: 'llm',
        type: 'llm',
        model: 'test/model',
        temperature: 0,
        max_tokens: 256,
      },
    ],
    edges: [],
  },
  layout: { positions: {} },
});

const index = (id: string, snapshotId: string, snapshotNumber: number): IndexVersion => ({
  id,
  project_id: 'project-1',
  knowledge_set_id: `set-${id}`,
  knowledge_set_name: `Index ${id}`,
  version: 1,
  embedding_config: {
    provider: 'test',
    model: 'embedding',
    dimensions: 3,
    endpoint_id: 'test',
    revision: '1',
  },
  status: 'succeeded',
  chunk_count: 4,
  embedded_count: 4,
  attempts: 1,
  failures: 0,
  processing_run_count: 1,
  is_current: true,
  source_kind: 'website',
  source_snapshot: {
    id: snapshotId,
    snapshot_number: snapshotNumber,
    status: 'ready',
    source_kind: 'website',
    included_count: 2,
    collected_at: '2026-09-22T00:00:00Z',
  },
  ingestion_pipeline: null,
  processing_summary: null,
  error: null,
  created_at: '2026-09-22T00:00:00Z',
});

const versions = [pipeline('A', 'index-a'), pipeline('B', 'index-b')];
const baseProps = {
  projectId: 'project-1',
  datasets: [],
  pipelines: versions,
  options: {
    model: 'test/judge',
    error: null,
    max_rows: 20,
    max_bytes: 1000,
    metrics: {
      faithfulness: 'Support in context.',
      response_relevancy: 'Question alignment.',
      context_recall: 'Reference coverage.',
    },
  },
  name: 'Comparison',
  datasetId: '',
  candidateA: 'A',
  candidateB: 'B',
  selectedMetrics: ['faithfulness' as const],
  busy: false,
  storageError: '',
  onNameChange: vi.fn(),
  onDatasetChange: vi.fn(),
  onCandidateAChange: vi.fn(),
  onCandidateBChange: vi.fn(),
  onMetricsChange: vi.fn(),
  onReset: vi.fn(),
  onSubmit: vi.fn(),
};

test('confirms same-snapshot setup and warns when candidate lineage differs', () => {
  const { rerender } = render(
    <ExperimentForm
      {...baseProps}
      indexes={[index('index-a', 'snapshot-1', 3), index('index-b', 'snapshot-1', 3)]}
    />,
  );
  expect(screen.getByText(/Same source snapshot\. Differences are caused/)).toBeVisible();
  expect(screen.getAllByText('Source snapshot 3')).toHaveLength(2);

  rerender(
    <ExperimentForm
      {...baseProps}
      indexes={[index('index-a', 'snapshot-1', 3), index('index-b', 'snapshot-2', 4)]}
    />,
  );
  expect(screen.getByText(/These pipelines use different source snapshots/)).toBeVisible();
});

test('retains the immutable same-snapshot confirmation in results', () => {
  const candidate = (id: string, indexId: string) => ({
    ...pipeline(id, indexId),
    index_id: indexId,
    index_name: `Index ${id}`,
    index_version: 1,
    source_snapshot: {
      id: 'snapshot-1',
      snapshot_number: 3,
      collected_at: '2026-09-22T00:00:00Z',
    },
    generation_config: { model: 'test/model' },
    embedding_config: { model: 'embedding' },
  });
  const run = {
    snapshot: {
      dataset: { name: 'Reviewed', version: 1 },
      candidates: [candidate('A', 'index-a'), candidate('B', 'index-b')],
      evaluator: { model: 'test/judge', metrics: [], ragas_version: '0.4.3' },
      application: { source_sha256: 'hash' },
      source_comparison: {
        status: 'same',
        message:
          'Same source snapshot. Differences are caused by the selected index and pipeline configurations, not different collected content.',
      },
    },
    summary: { candidates: [], paired: {} },
  } as unknown as Detail;

  render(<ComparisonSummary run={run} />);
  expect(screen.getByText(/Same source snapshot\. Differences are caused/)).toBeVisible();
});
