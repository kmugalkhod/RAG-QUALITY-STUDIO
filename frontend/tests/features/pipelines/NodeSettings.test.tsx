import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import { NodeSettings } from '../../../src/features/pipelines/components/NodeSettings';
import type { IndexVersion } from '../../../src/features/documents/model';
import type { FlowNode } from '../../../src/features/pipelines/components/WorkflowNode';

const index = {
  id: 'index-1',
  project_id: 'project-1',
  knowledge_set_id: 'set-1',
  knowledge_set_name: 'Balanced Website',
  version: 2,
  status: 'succeeded',
  chunk_count: 12,
  embedded_count: 12,
  attempts: 1,
  failures: 0,
  processing_run_count: 1,
  is_current: true,
  source_kind: 'website',
  source_snapshot: {
    id: 'snapshot-1',
    snapshot_number: 3,
    status: 'ready',
    source_kind: 'website',
    included_count: 4,
    collected_at: '2026-09-22T00:00:00Z',
  },
  ingestion_pipeline: null,
  processing_summary: null,
  embedding_config: {
    provider: 'test',
    model: 'embedding',
    dimensions: 3,
    endpoint_id: 'test',
    revision: '1',
  },
  error: null,
  created_at: '2026-09-22T00:00:00Z',
} satisfies IndexVersion;

const retriever = {
  id: 'retriever',
  type: 'workflow',
  position: { x: 0, y: 0 },
  data: {
    label: 'Retriever',
    vertical: true,
    config: { id: 'retriever', type: 'retriever', index_id: 'index-1', top_k: 5 },
  },
} as FlowNode;

test('shows the exact selected index and read-only source snapshot lineage', () => {
  render(
    <NodeSettings
      open
      config={retriever.data.config}
      selected="retriever"
      nodes={[retriever]}
      indexes={[index]}
      onSelect={vi.fn()}
      onUpdate={vi.fn()}
      onDelete={vi.fn()}
    />,
  );

  expect(screen.getByLabelText('Documents to search')).toHaveValue('index-1');
  expect(screen.getByLabelText('Selected index source lineage')).toHaveTextContent(
    'Source snapshot 3 · collected Sep 22, 2026',
  );
});
