import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, test } from 'vitest';

import { IngestionNodeSettings } from '../../../src/features/ingestion-pipelines/components/IngestionNodeSettings';
import type { IngestionNode } from '../../../src/features/ingestion-pipelines/model';

let lastChunk: IngestionNode | undefined;

function Harness({
  chunkVersion = 'section-token-v5',
  initial,
}: {
  chunkVersion?: string;
  initial?: IngestionNode;
}) {
  const [node, setNode] = useState<IngestionNode>(
    initial ?? {
      id: 'chunk',
      type: 'chunk',
      algorithm: 'section_token',
      unit: 'tokens',
      tokenizer_version: 'utf8-byte-v1',
      target_tokens: 600,
      maximum_tokens: 800,
      overlap_tokens: 80,
      add_heading_context: true,
      config_version: chunkVersion,
    },
  );
  lastChunk = node;
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

test('edits method-specific chunk settings without mixing incompatible fields', () => {
  render(<Harness />);

  expect(screen.getByRole('radio', { name: /Section-aware \(recommended\)/ })).toBeChecked();
  expect(screen.getByRole('radio', { name: /Medium \(recommended\)/ })).toBeChecked();
  expect(screen.getByLabelText('Target size (bytes)')).toHaveValue(600);
  expect(screen.getByLabelText('Maximum size (bytes)')).toHaveValue(800);
  expect(screen.queryByLabelText('Chunk size (characters)')).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('radio', { name: /Parent and child/ }));
  expect(screen.getByLabelText('Child target size (bytes)')).toHaveValue(240);
  expect(screen.getByLabelText('Parent maximum size (bytes)')).toHaveValue(1200);
  expect(screen.getByText(/Child passages are embedded/)).toBeInTheDocument();
  expect(screen.queryByLabelText('Target size (bytes)')).not.toBeInTheDocument();
  // New choices offer the two methods only; the character window is for saved versions.
  expect(screen.queryByRole('radio', { name: /Character window/ })).not.toBeInTheDocument();
});

test('passage sizes say about how many words they hold and set the exact bytes', () => {
  render(<Harness />);
  expect(screen.getByRole('radio', { name: /Small about 50 words/ })).toBeInTheDocument();
  expect(
    screen.getByRole('radio', { name: /Medium \(recommended\) about 100 words/ }),
  ).toBeChecked();
  fireEvent.click(screen.getByRole('radio', { name: /Large about 200 words/ }));
  expect(lastChunk).toMatchObject({
    target_tokens: 1200,
    maximum_tokens: 1600,
    overlap_tokens: 160,
  });
  expect(screen.getByText(/Advanced chunking settings/)).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('Target size (bytes)'), { target: { value: '1000' } });
  expect(screen.getByText('Custom sizes, listed under Advanced.')).toBeInTheDocument();
  expect(screen.getByText('· 1 changed')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Reset to recommended' }));
  expect(lastChunk).toMatchObject({ target_tokens: 600, maximum_tokens: 800, overlap_tokens: 80 });
});

test('a saved character window opens with its sizes under Advanced', () => {
  render(
    <Harness
      initial={{
        id: 'chunk',
        type: 'chunk',
        algorithm: 'character_window',
        unit: 'characters',
        size: 1000,
        overlap: 100,
        config_version: 'character-window-v1',
      }}
    />,
  );
  expect(screen.getByText('Saved with the character window')).toBeInTheDocument();
  expect(screen.getByLabelText('Chunk size (characters)')).toHaveValue(1000);
  expect(screen.getByRole('radio', { name: /Section-aware/ })).not.toBeChecked();
});

test('a new token chunker uses the current version and shows no upgrade', () => {
  render(<Harness />);
  expect(screen.queryByRole('button', { name: 'Upgrade chunking' })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('radio', { name: /Parent and child/ }));
  expect(lastChunk).toMatchObject({ config_version: 'parent-child-v5' });
  expect(screen.queryByRole('button', { name: 'Upgrade chunking' })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('radio', { name: /Section-aware/ }));
  expect(lastChunk).toMatchObject({ config_version: 'section-token-v5' });
});

test('offers a saved section-token-v1 chunker an explicit upgrade that keeps its settings', () => {
  render(<Harness chunkVersion="section-token-v1" />);
  expect(screen.getByText('Saved with section-token-v1')).toBeInTheDocument();
  expect(screen.getByText(/The current\s+chunking, section-token-v5:/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Target size (bytes)'), { target: { value: '500' } });

  fireEvent.click(screen.getByRole('button', { name: 'Upgrade chunking' }));

  expect(screen.queryByText('Saved with section-token-v1')).not.toBeInTheDocument();
  expect(lastChunk).toMatchObject({ config_version: 'section-token-v5', target_tokens: 500 });
});

function PolicyHarness({
  kind,
  extractVersion = 'layout-ocr-v6',
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
  // Spec 0012 D9: the switch is visible on the panel, the rules are under Advanced.
  expect(screen.getByLabelText(/Redact emails, phone numbers and IDs/)).toBeChecked();
  expect(screen.getByText(/Redaction cannot be undone/)).toBeInTheDocument();
  expect(screen.getByText(/cannot find every one/)).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('Email addresses'), {
    target: { value: 'drop_document' },
  });
  expect(screen.getByLabelText('Email addresses')).toHaveValue('drop_document');
  expect(screen.getByText('· 1 changed')).toBeInTheDocument();
});

test('edits exact and near-duplicate decisions with a visible threshold', () => {
  render(<PolicyHarness kind="clean" />);
  fireEvent.click(screen.getByLabelText('Nearly identical text'));
  expect(screen.getByLabelText('Near-duplicate similarity threshold')).toHaveValue(0.92);
  fireEvent.change(screen.getByLabelText('Pinned canonical locations'), {
    target: { value: 'project-file:one, https://example.com/copy' },
  });
  expect(screen.getByLabelText('Pinned canonical locations')).toHaveValue(
    'project-file:one, https://example.com/copy',
  );
  expect(screen.getByText(/The copy kept is the pinned source/i)).toBeInTheDocument();
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

test.each(['layout-ocr-v3', 'layout-ocr-v4', 'layout-ocr-v5'])(
  'offers a saved %s extractor the v6 upgrade',
  (version) => {
    render(<PolicyHarness kind="extract" extractVersion={version} />);
    expect(screen.getByText(`Saved with ${version}`)).toBeInTheDocument();
    expect(screen.getByText(/The current extractor, layout-ocr-v6,/)).toBeInTheDocument();
    expect(screen.getByText(/reads charts as text/)).toBeInTheDocument();
    expect(screen.getByText(/files each table\s+under its caption/)).toBeInTheDocument();
    expect(
      screen.getByText(/labels the columns of tables rebuilt from printed lines/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("If a file can't be read well")).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Upgrade extraction' }));

    expect(screen.queryByText(`Saved with ${version}`)).not.toBeInTheDocument();
  },
);

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
  version = 'layout-ocr-v6',
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
