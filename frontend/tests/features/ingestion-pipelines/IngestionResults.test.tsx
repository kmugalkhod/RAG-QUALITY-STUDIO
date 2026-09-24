import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import * as api from '../../../src/features/ingestion-pipelines/api';
import { IngestionRunResults } from '../../../src/features/ingestion-pipelines/components/IngestionResults';
import type {
  ContentDerivation,
  IngestionRun,
  IngestionRunItem,
} from '../../../src/features/ingestion-pipelines/model';

vi.mock('../../../src/features/ingestion-pipelines/api');

const run = {
  status: 'succeeded',
  new_count: 1,
  changed_count: 0,
  unchanged_count: 0,
  removed_count: 0,
  error: null,
  published_index_id: null,
} as IngestionRun;

const item = {
  source_kind: 'existing_files',
  document_id: 'document-1',
  filename: 'guide.txt',
  content_hash: 'a'.repeat(64),
  media_type: 'text/plain',
  source_node_id: 'source',
  processing_run_id: 'processing-1',
  processing_version: 2,
  processing_created: true,
  status: 'succeeded',
  chunk_count: 1,
  error: null,
  processing_versions: {
    extractor: 'native-text-v1',
    cleaner: 'deterministic-clean-v1',
    chunker: 'character-window-v1',
  },
  updated_at: '2026-09-24T00:00:00Z',
} satisfies IngestionRunItem;

const derivation = {
  id: 'derivation-1',
  project_id: 'project-1',
  document_id: 'document-1',
  processing_run_id: 'processing-1',
  kind: 'extracted',
  schema_version: 1,
  engine_version: 'native-text-v1',
  configuration_hash: 'b'.repeat(64),
  input_hash: 'c'.repeat(64),
  output_hash: 'c'.repeat(64),
  title: 'guide.txt',
  media_type: 'text/plain',
  measurements: { character_count: 12, block_count: 1, page_count: 1 },
  findings: [],
  transforms: [],
  created_at: '2026-09-24T00:00:00Z',
} satisfies ContentDerivation;

test('loads the immutable extracted content inspector for a run item', async () => {
  vi.mocked(api.listContentDerivations).mockResolvedValue({
    items: [derivation],
    total: 1,
  });
  vi.mocked(api.listContentBlocks).mockResolvedValue({
    items: [
      {
        derivation_id: derivation.id,
        ordinal: 0,
        block_id: 'd'.repeat(16),
        block_type: 'paragraph',
        text: 'Source text.',
        page_number: 1,
        bounding_box: null,
        heading_path: ['Introduction'],
        source_span: { kind: 'artifact_text', start_char: 0, end_char: 12 },
        attributes: {},
      },
    ],
    total: 1,
    limit: 20,
    offset: 0,
  });

  render(<IngestionRunResults projectId="project-1" run={run} items={[item]} />);
  fireEvent.click(screen.getByRole('button', { name: 'Inspect content' }));

  expect(await screen.findByText('Source text.')).toBeVisible();
  expect(screen.getByRole('tab', { name: 'Extracted' })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByText('Introduction')).toBeVisible();
  expect(api.listContentDerivations).toHaveBeenCalledWith('project-1', 'processing-1');
});
