import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import * as api from '../../../src/features/ingestion-pipelines/api';
import {
  IngestionPreviewResults,
  IngestionRunResults,
} from '../../../src/features/ingestion-pipelines/components/IngestionResults';
import type {
  ContentDerivation,
  IngestionRun,
  IngestionRunItem,
  SourcePreview,
  SourcePreviewItem,
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
  media_type: 'application/pdf',
  measurements: {
    character_count: 30,
    block_count: 2,
    page_count: 1,
    native_page_count: 0,
    layout_page_count: 1,
    ocr_page_count: 0,
    table_count: 1,
    quality_decision: 'warn',
    extraction_duration_ms: 18,
  },
  findings: [
    {
      code: 'suspicious_reading_order',
      severity: 'warning',
      count: 1,
      message: 'Reading order needs review.',
      page_numbers: [1],
      remediation: 'Review the page overlays.',
    },
  ],
  transforms: [],
  created_at: '2026-09-24T00:00:00Z',
} satisfies ContentDerivation;

const preview = {
  id: 'preview-1',
  project_id: 'project-1',
  status: 'succeeded',
  progress: 100,
  discovered_count: 1,
  included_count: 1,
  excluded_count: 0,
  duplicate_count: 0,
  failed_count: 0,
  pass_count: 0,
  warn_count: 1,
  exclude_count: 0,
  quality_fail_count: 0,
  known_compute_ms: 12,
  configuration_hash: 'f'.repeat(64),
  fetch_mode: 'cached-artifact',
  cost_basis: { known_monetary_cost: null },
  attempts: 1,
  failures: 0,
  error: null,
  created_at: '2026-09-24T00:00:00Z',
  updated_at: '2026-09-24T00:00:01Z',
  started_at: '2026-09-24T00:00:00Z',
  finished_at: '2026-09-24T00:00:01Z',
  expires_at: '2026-09-25T00:00:00Z',
} satisfies SourcePreview;

const previewItem = {
  ordinal: 0,
  source_node_id: 'source',
  external_id: 'guide',
  display_name: 'guide.txt',
  canonical_location: 'document://guide',
  provider_revision: 'revision-1',
  media_type: 'text/plain',
  status: 'included',
  reason: 'Selected for processing preview.',
  size_bytes: 42,
  depth: null,
  error_code: null,
  quality_decision: 'warn',
  processing_status: 'succeeded',
  fetch_mode: 'cached-artifact',
  processing_config_hash: 'f'.repeat(64),
  findings: [
    {
      code: 'review_order',
      severity: 'warning',
      message: 'Review reading order.',
      remediation: 'Inspect extracted blocks.',
    },
  ],
  metrics: { character_count: 42 },
  stage_timings: { extract_ms: 4, clean_ms: 3, chunk_ms: 5 },
  cost_basis: { known_monetary_cost: null },
} satisfies SourcePreviewItem;

test('shows quality, cached mode, and synchronized processing representations', async () => {
  vi.mocked(api.listSourcePreviewRepresentations).mockResolvedValue({
    items: [
      {
        stage: 'raw',
        ordinal: 0,
        block_type: 'text',
        text: '<script>not executed</script> source',
        metadata: {},
      },
    ],
    total: 1,
    limit: 20,
    offset: 0,
  });

  render(
    <IngestionPreviewResults
      projectId="project-1"
      preview={preview}
      page={{ items: [previewItem], total: 1, limit: 20, offset: 0 }}
      busy={false}
      onCancel={vi.fn()}
      onRetry={vi.fn()}
      onPageChange={vi.fn()}
    />,
  );

  expect(screen.getByText(/Quality: 0 pass · 1 warn/)).toBeVisible();
  expect(screen.getAllByText(/cached artifact/).length).toBeGreaterThan(0);
  expect(screen.getByText(/monetary cost unknown/)).toBeVisible();
  expect(screen.getByText(/Review reading order/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Inspect stages' }));
  expect(await screen.findByText('<script>not executed</script> source')).toBeVisible();
  expect(document.querySelector('script')).toBeNull();
  expect(screen.getByRole('tab', { name: 'Raw' })).toHaveAttribute('aria-selected', 'true');
});

test('offers retry for an expired preview without requesting expired representations', () => {
  const retry = vi.fn();
  render(
    <IngestionPreviewResults
      projectId="project-1"
      preview={{ ...preview, status: 'expired' }}
      page={{ items: [previewItem], total: 1, limit: 20, offset: 0 }}
      busy={false}
      onCancel={vi.fn()}
      onRetry={retry}
      onPageChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Retry preview' }));
  expect(retry).toHaveBeenCalledOnce();
  expect(screen.queryByRole('button', { name: 'Inspect stages' })).not.toBeInTheDocument();
});

test('loads the immutable extracted content inspector for a run item', async () => {
  vi.mocked(api.contentPageThumbnailUrl).mockReturnValue('/api/thumbnail');
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
        bounding_box: { left: 0.1, top: 0.1, right: 0.8, bottom: 0.2 },
        heading_path: ['Introduction'],
        source_span: { kind: 'artifact_text', start_char: 0, end_char: 12 },
        attributes: { origin: 'layout' },
      },
      {
        derivation_id: derivation.id,
        ordinal: 1,
        block_id: 'e'.repeat(16),
        block_type: 'table',
        text: '| Header | Value |',
        page_number: 1,
        bounding_box: { left: 0.1, top: 0.3, right: 0.8, bottom: 0.5 },
        heading_path: [],
        source_span: { kind: 'artifact_text', page_number: 1, start_char: 12, end_char: 30 },
        attributes: {
          origin: 'layout',
          table: {
            rows: [
              ['Header', 'Value'],
              ['A', 'B'],
            ],
          },
        },
      },
    ],
    total: 2,
    limit: 20,
    offset: 0,
  });

  render(<IngestionRunResults projectId="project-1" run={run} items={[item]} />);
  fireEvent.click(screen.getByRole('button', { name: 'Inspect content' }));

  expect(await screen.findByText('Source text.')).toBeVisible();
  expect(screen.getByRole('tab', { name: 'Extracted' })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByText('Introduction')).toBeVisible();
  expect(screen.getByText('warning · suspicious reading order')).toBeVisible();
  expect(screen.getByRole('img', { name: 'Rendered PDF page 1' })).toHaveAttribute(
    'src',
    '/api/thumbnail',
  );
  expect(screen.getAllByRole('button', { name: /Select Layout/ })).toHaveLength(2);
  expect(screen.getByRole('table')).toHaveTextContent('HeaderValueAB');
  expect(api.listContentDerivations).toHaveBeenCalledWith('project-1', 'processing-1');
});

test('shows the safe per-item processing failure', () => {
  render(
    <IngestionRunResults
      projectId="project-1"
      run={{ ...run, status: 'failed', error: 'One or more files failed.' }}
      items={[
        {
          ...item,
          status: 'failed',
          error:
            'Extraction did not satisfy the saved quality policy. Review the source and extraction settings before retrying.',
        },
      ]}
    />,
  );

  expect(screen.getAllByRole('alert')).toHaveLength(2);
  expect(screen.getByText(/Review the source and extraction settings/)).toBeVisible();
});

test('shows a reconstructed cleaning diff with transform attribution', async () => {
  vi.mocked(api.listContentDerivations).mockResolvedValue({ items: [derivation], total: 1 });
  vi.mocked(api.listContentBlocks).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.mocked(api.listCleaningDiff).mockResolvedValue({
    items: [
      {
        block_id: 'd'.repeat(16),
        block_type: 'paragraph',
        page_number: 1,
        before_text: 'inter-\nnational REMOVE',
        after_text: 'international',
        action: 'rewritten',
        transforms: ['dehyphenate', 'remove_literal_boilerplate'],
        reasons: ['dehyphenate', 'remove_literal_boilerplate'],
      },
    ],
    total: 1,
    limit: 20,
    offset: 0,
  });

  render(<IngestionRunResults projectId="project-1" run={run} items={[item]} />);
  fireEvent.click(screen.getByRole('button', { name: 'Inspect content' }));
  await screen.findByRole('tab', { name: 'Extracted' });
  fireEvent.click(screen.getByRole('tab', { name: 'Changes' }));

  expect((await screen.findByLabelText('Before cleaning')).querySelector('pre')).toHaveTextContent(
    /inter-\s*national REMOVE/,
  );
  expect(screen.getByText('international')).toBeVisible();
  expect(screen.getByText(/dehyphenate → remove_literal_boilerplate/)).toBeVisible();
  expect(api.listCleaningDiff).toHaveBeenCalledWith('project-1', 'processing-1');
});

test('inspects evidence text, embedding prefix, spans, and parent links', async () => {
  vi.mocked(api.listContentDerivations).mockResolvedValue({ items: [derivation], total: 1 });
  vi.mocked(api.listContentBlocks).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.mocked(api.listProcessingChunks).mockResolvedValue({
    items: [
      {
        run_id: 'processing-1',
        ordinal: 1,
        page_number: 1,
        start_char: 0,
        end_char: 13,
        evidence_text: 'Faithful text',
        embedding_text: 'Section: Guide\n\nFaithful text',
        embedding_prefix: 'Section: Guide\n\n',
        token_count: 13,
        embedding_token_count: 29,
        chunk_role: 'child',
        parent_ordinal: 0,
        section_path: ['Guide'],
        findings: [],
        spans: [
          {
            run_id: 'processing-1',
            chunk_ordinal: 1,
            span_ordinal: 0,
            derivation_id: 'derivation-1',
            derivation_kind: 'cleaned',
            block_ordinal: 0,
            block_start_char: 0,
            block_end_char: 13,
            chunk_start_char: 0,
            chunk_end_char: 13,
          },
        ],
      },
    ],
    summary: {
      minimum: 13,
      median: 13,
      p95: 13,
      maximum: 13,
      indexed_count: 1,
      stored_count: 2,
      parent_count: 1,
      oversize_finding_count: 0,
    },
    total: 1,
    limit: 20,
    offset: 0,
  });

  render(<IngestionRunResults projectId="project-1" run={run} items={[item]} />);
  fireEvent.click(screen.getByRole('button', { name: 'Inspect content' }));
  await screen.findByRole('tab', { name: 'Extracted' });
  fireEvent.click(screen.getByRole('tab', { name: 'Chunks' }));

  expect(await screen.findByText('Faithful text')).toBeVisible();
  expect(screen.getByText('Section: Guide')).toBeVisible();
  expect(screen.getByText('Supplies saved parent 1')).toBeVisible();
  expect(screen.getByText(/1 source span/)).toBeVisible();
  expect(screen.getByText('13 min · 13 median · 13 p95 · 13 max')).toBeVisible();
  expect(api.listProcessingChunks).toHaveBeenCalledWith('project-1', 'processing-1');
});
