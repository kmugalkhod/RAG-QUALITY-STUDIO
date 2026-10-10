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
      onSelectNode={() => undefined}
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

function PolicyHarness({
  kind,
  extractVersion = 'layout-ocr-v4',
}: {
  kind: 'extract' | 'clean';
  extractVersion?: string;
}) {
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
          config_version: extractVersion,
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
      onSelectNode={() => undefined}
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

test('makes irreversible sensitive-data actions explicit and keyboard-editable', () => {
  render(<PolicyHarness kind="clean" />);
  fireEvent.click(screen.getByText('Sensitive-data policy'));

  expect(
    screen.getByLabelText('Redact sensitive values before chunking and embedding'),
  ).toBeChecked();
  expect(screen.getByText(/Redaction is irreversible/)).toBeInTheDocument();
  expect(screen.getByText(/cannot detect every sensitive value/)).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('email action'), {
    target: { value: 'drop_document' },
  });
  expect(screen.getByLabelText('email action')).toHaveValue('drop_document');
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

test('offers a saved layout-ocr-v1 extractor an explicit upgrade', () => {
  render(<PolicyHarness kind="extract" extractVersion="layout-ocr-v1" />);
  expect(screen.getByText('Saved with layout-ocr-v1')).toBeInTheDocument();
  expect(screen.getByLabelText("If a file can't be read well")).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Upgrade extraction' }));

  expect(screen.queryByText('Saved with layout-ocr-v1')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Upgrade extraction' })).not.toBeInTheDocument();
  expect(screen.getByLabelText("If a file can't be read well")).toBeInTheDocument();
});

test('offers a saved layout-ocr-v3 extractor the v4 upgrade', () => {
  render(<PolicyHarness kind="extract" extractVersion="layout-ocr-v3" />);
  expect(screen.getByText('Saved with layout-ocr-v3')).toBeInTheDocument();
  expect(screen.getByText(/The current extractor, layout-ocr-v4,/)).toBeInTheDocument();
  expect(screen.getByText(/tables printed sideways and tables in PowerPoint/)).toBeInTheDocument();
  expect(screen.getByLabelText("If a file can't be read well")).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Upgrade extraction' }));

  expect(screen.queryByText('Saved with layout-ocr-v3')).not.toBeInTheDocument();
});

test('shows no upgrade for the current extractor', () => {
  render(<PolicyHarness kind="extract" />);
  expect(screen.queryByRole('button', { name: 'Upgrade extraction' })).not.toBeInTheDocument();
});

test('explains that legacy native-text findings are warnings only', () => {
  render(<PolicyHarness kind="extract" extractVersion="native-text-v1" />);
  expect(
    screen.getByText(/quality findings for this extractor as warnings only/),
  ).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Enable robust extraction' })).toBeInTheDocument();
});

function SourcesHarness({
  kinds,
  version = 'layout-ocr-v4',
}: {
  kinds: string[];
  version?: string;
}) {
  const extract: IngestionNode = {
    id: 'extract',
    type: 'extract',
    strategy: 'layout_aware',
    ocr: {
      mode: 'off',
      languages: ['eng'],
      rotate_pages: true,
      deskew: true,
      dpi: 200,
      max_pages: 50,
      timeout_seconds: 30,
    },
    tables: 'plain_text',
    config_version: version,
  };
  const sources = kinds.map(
    (kind, index) => ({ id: `source-${index}`, type: 'source', config: { kind } }) as IngestionNode,
  );
  return (
    <IngestionNodeSettings
      projectId="project"
      selected={extract}
      selectedNode="extract"
      nodes={[...sources, extract]}
      dirty={false}
      validation={[]}
      connections={[]}
      documents={[]}
      knowledgeSets={[]}
      websiteSource={kinds.includes('website')}
      schemaVersion={2}
      updateNode={() => undefined}
      changeSourceKind={() => undefined}
      onSelectNode={() => undefined}
    />
  );
}

test('shows only quality and language settings for page-based sources', () => {
  render(<SourcesHarness kinds={['website', 'website']} />);
  expect(screen.getByText('Quality and language only')).toBeInTheDocument();
  expect(screen.queryByText(/older custom setting/)).not.toBeInTheDocument();
  expect(screen.getByLabelText('Quality policy')).toBeInTheDocument();
  expect(screen.getByText('Language policy')).toBeInTheDocument();
});

test('names saved file-only settings for file sources', () => {
  for (const kinds of [['s3'], ['existing_files'], ['notion', 's3']]) {
    const { unmount } = render(<SourcesHarness kinds={kinds} />);
    expect(screen.queryByText('Quality and language only')).not.toBeInTheDocument();
    expect(
      screen.getByText(
        /Uses older custom settings: extraction strategy Layout-aware, table format Plain text\./,
      ),
    ).toBeInTheDocument();
    unmount();
  }
});

test('offers the extractor upgrade for every source kind', () => {
  const { unmount } = render(<SourcesHarness kinds={['website']} version="layout-ocr-v2" />);
  expect(screen.getByRole('button', { name: 'Upgrade extraction' })).toBeInTheDocument();
  unmount();
  render(<SourcesHarness kinds={['s3']} version="layout-ocr-v1" />);
  expect(screen.getByRole('button', { name: 'Upgrade extraction' })).toBeInTheDocument();
});
