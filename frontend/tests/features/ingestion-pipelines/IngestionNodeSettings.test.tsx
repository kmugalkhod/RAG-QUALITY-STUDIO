import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, test } from 'vitest';

import { IngestionNodeSettings } from '../../../src/features/ingestion-pipelines/components/IngestionNodeSettings';
import type { IngestionNode } from '../../../src/features/ingestion-pipelines/model';

function Harness() {
  const [node, setNode] = useState<IngestionNode>({
    id: 'chunk',
    type: 'chunk',
    algorithm: 'section_token',
    unit: 'tokens',
    tokenizer_version: 'utf8-byte-v1',
    target_tokens: 600,
    maximum_tokens: 800,
    overlap_tokens: 80,
    add_heading_context: true,
    config_version: 'section-token-v1',
  });
  return (
    <IngestionNodeSettings
      projectId="project"
      selected={node}
      selectedNode="chunk"
      nodes={[node]}
      dirty
      validation={[]}
      connections={[]}
      documents={[]}
      knowledgeSets={[]}
      websiteSource={false}
      schemaVersion={2}
      updateNode={(_, update) => setNode((current) => update(current))}
      changeSourceKind={() => undefined}
    />
  );
}

test('edits algorithm-specific chunk settings without mixing incompatible fields', () => {
  render(<Harness />);

  expect(screen.getByLabelText('Target tokens')).toHaveValue(600);
  expect(screen.getByLabelText('Hard maximum tokens')).toHaveValue(800);
  expect(screen.queryByLabelText('Chunk size (characters)')).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('Chunking algorithm'), {
    target: { value: 'parent_child' },
  });
  expect(screen.getByLabelText('Child target tokens')).toHaveValue(240);
  expect(screen.getByLabelText('Parent hard maximum tokens')).toHaveValue(1200);
  expect(screen.getByText(/Child chunks are embedded/)).toBeVisible();

  fireEvent.change(screen.getByLabelText('Chunking algorithm'), {
    target: { value: 'character_window' },
  });
  expect(screen.getByLabelText('Chunk size (characters)')).toHaveValue(1000);
  expect(screen.getByLabelText('Overlap (characters)')).toHaveValue(100);
  expect(screen.queryByLabelText('Target tokens')).not.toBeInTheDocument();
});

function PolicyHarness({ kind }: { kind: 'extract' | 'clean' }) {
  const [node, setNode] = useState<IngestionNode>(
    kind === 'extract'
      ? {
          id: 'extract',
          type: 'extract',
          strategy: 'auto',
          ocr: {
            mode: 'off',
            languages: ['eng'],
            rotate_pages: true,
            deskew: true,
            dpi: 200,
            max_pages: 50,
            timeout_seconds: 30,
          },
          tables: 'preserve',
          config_version: 'layout-ocr-v1',
        }
      : {
          id: 'clean',
          type: 'clean',
          normalize_whitespace: true,
          repeated_boilerplate: [],
          minimum_text_chars: 1,
          maximum_text_chars: 2_000_000,
          exact_content_deduplication: true,
          profile: 'standard-v1',
          config_version: 'deterministic-clean-v1',
        },
  );
  return (
    <IngestionNodeSettings
      projectId="project"
      selected={node}
      selectedNode={kind}
      nodes={[node]}
      dirty
      validation={[]}
      connections={[]}
      documents={[]}
      knowledgeSets={[]}
      websiteSource={false}
      schemaVersion={2}
      updateNode={(_, update) => setNode((current) => update(current))}
      changeSourceKind={() => undefined}
    />
  );
}

test('edits saved language behavior without offering translation', () => {
  render(<PolicyHarness kind="extract" />);
  fireEvent.change(screen.getByLabelText('Allowed language tags'), {
    target: { value: 'en, fr' },
  });
  fireEvent.change(screen.getByLabelText('Mixed-language documents'), {
    target: { value: 'fail' },
  });
  expect(screen.getByLabelText('Allowed language tags')).toHaveValue('en, fr');
  expect(screen.getByLabelText('Mixed-language documents')).toHaveValue('fail');
  expect(screen.getByText(/never translated/i)).toBeInTheDocument();
});

test('edits exact and near-duplicate decisions with a visible threshold', () => {
  render(<PolicyHarness kind="clean" />);
  fireEvent.click(screen.getByLabelText('Near-duplicate SimHash'));
  expect(screen.getByLabelText('Near-duplicate similarity threshold')).toHaveValue(0.92);
  fireEvent.change(screen.getByLabelText('Pinned canonical locations'), {
    target: { value: 'project-file:one, https://example.com/copy' },
  });
  expect(screen.getByLabelText('Pinned canonical locations')).toHaveValue(
    'project-file:one, https://example.com/copy',
  );
  expect(screen.getByText(/Canonical order: pinned source/i)).toBeInTheDocument();
});
