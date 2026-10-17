/**
 * Spec 0012, Slice 0: one reproduction per Part A bug that has a frontend path.
 * Each test states the fixed behaviour and is marked `test.fails` while the bug is
 * present; the slice that fixes the bug turns it into a plain `test`.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState, type ComponentProps } from 'react';
import { expect, test, vi } from 'vitest';

import { CleanSettings } from '../../../src/features/ingestion-pipelines/components/CleanSettings';
import { CleaningTransformSettings } from '../../../src/features/ingestion-pipelines/components/CleaningTransformSettings';
import { IngestionGroupStrip } from '../../../src/features/ingestion-pipelines/components/IngestionGroupStrip';
import { IngestionNodeSettings } from '../../../src/features/ingestion-pipelines/components/IngestionNodeSettings';
import {
  embeddingUsageText,
  IngestionRunStrip,
} from '../../../src/features/ingestion-pipelines/components/IngestionRunStrip';
import { ProcessingStep } from '../../../src/features/ingestion-pipelines/components/GuidedSetupSteps';
import {
  defaultChunkNode,
  defaultIngestionDraft,
  serverFieldErrors,
} from '../../../src/features/ingestion-pipelines/editorModel';
import { newGuidedDraft } from '../../../src/features/ingestion-pipelines/guidedModel';
import type {
  ExtractionCapabilities,
  IngestionNode,
  IngestionRun,
  IngestionRunGroup,
} from '../../../src/features/ingestion-pipelines/model';

const embedding = {
  provider: 'openrouter',
  model: 'openai/text-embedding-3-small',
  dimensions: 1536,
  revision: '1',
  endpoint_id: 'endpoint',
};

type Clean = Extract<IngestionNode, { type: 'clean' }>;

const structureClean: Clean = {
  id: 'clean',
  type: 'clean',
  normalize_whitespace: true,
  repeated_boilerplate: [],
  minimum_text_chars: 1,
  maximum_text_chars: 2_000_000,
  exact_content_deduplication: true,
  profile: 'structure-aware-v1',
  config_version: 'structure-clean-v1',
  steps: [
    {
      id: 'preserve-structure',
      type: 'preserve_structure',
      enabled: true,
      block_types: ['table', 'list_item', 'code', 'quote', 'footnote'],
    },
    { id: 'unicode-normalize', type: 'unicode_normalize', enabled: true, form: 'NFC' },
    {
      id: 'remove-literal-boilerplate',
      type: 'remove_literal_boilerplate',
      enabled: true,
      values: ['Confidential'],
      block_types: ['paragraph', 'unknown'],
    },
  ],
};

function settingsProps(
  node: IngestionNode,
  setNode: (update: (current: IngestionNode) => IngestionNode) => void,
  extra: Partial<ComponentProps<typeof IngestionNodeSettings>> = {},
): ComponentProps<typeof IngestionNodeSettings> {
  return {
    projectId: 'project',
    selected: node,
    selectedNode: node.id,
    nodes: [node],
    dirty: true,
    validation: [],
    connections: [],
    documents: [],
    knowledgeSets: [],
    websiteSource: false,
    schemaVersion: 2,
    updateNode: (_, update) => setNode(update),
    changeSourceKind: () => undefined,
    onSelectNode: () => undefined,
    ...extra,
  };
}

function NodeHarness({
  initial,
  extra,
  onChange,
}: {
  initial: IngestionNode;
  extra?: Partial<ComponentProps<typeof IngestionNodeSettings>>;
  onChange?: (node: IngestionNode) => void;
}) {
  const [node, setNode] = useState(initial);
  onChange?.(node);
  return (
    <IngestionNodeSettings
      {...settingsProps(node, (update) => setNode((current) => update(current)), extra)}
    />
  );
}

function CleanHarness({ onChange }: { onChange: (node: Clean) => void }) {
  const [node, setNode] = useState<Clean>(structuredClone(structureClean));
  onChange(node);
  return <CleaningTransformSettings node={node} update={setNode} />;
}

// A1: picking an existing index and switching back to "new" must not keep its name.
test('A1: switching back to a new index does not inherit the existing name', () => {
  render(
    <NodeHarness
      initial={{ id: 'publish', type: 'publish_index', knowledge_set_name: 'My pipeline' }}
      extra={{
        knowledgeSets: [
          {
            id: 'set-1',
            project_id: 'project',
            name: 'Docs',
            current_ready_index_id: null,
            created_at: '2026-10-17T00:00:00Z',
          },
        ],
      }}
    />,
  );
  // Slice 1 replaced the select with an explicit choice (D3).
  fireEvent.click(screen.getByRole('radio', { name: /Add a version to an existing index/ }));
  fireEvent.click(screen.getByRole('radio', { name: /New index/ }));
  expect(screen.getByLabelText('Index name')).not.toHaveValue('Docs');
});

// A2: a new draft publishes to an index named after the pipeline.
test('A2: a new draft does not publish to "Ingested knowledge"', () => {
  const draft = defaultIngestionDraft(embedding, []);
  const publish = draft.execution.nodes.find((node) => node.type === 'publish_index');
  expect(publish).toMatchObject({ knowledge_set_name: draft.name });
});

// A5: a branch whose index did not publish shows no version.
test('A5: a failed branch shows no index version', () => {
  const group: IngestionRunGroup = {
    id: 'group',
    project_id: 'project',
    pipeline_version_id: 'version',
    schedule_id: null,
    trigger_kind: 'manual',
    status: 'partial',
    completion: null,
    created_at: '2026-10-17T00:00:00Z',
    runs: [
      {
        id: 'b',
        branch_source_node_id: 'source',
        status: 'failed',
        stage: 'indexing',
        progress: 60,
        knowledge_set_name: 'Docs · b.example',
        // What the server returns today for an index that failed while embedding.
        published_index_id: 'index-b',
        published_index_version: 3,
        error: 'Embedding failed.',
      } as IngestionRun,
    ],
  };
  render(
    <IngestionGroupStrip
      projectId="project"
      group={group}
      busy={false}
      label={() => 'Website 1'}
      onCancel={vi.fn()}
      onShowDetails={vi.fn()}
      onDismiss={vi.fn()}
    />,
  );
  expect(screen.queryByText(/version 3/)).toBeNull();
});

// A11: a cancelled run that paid for embeddings still reports them.
test('A11: a cancelled run shows its embedding usage', () => {
  const usage = { tokens: 1200, cost_usd: 0.000024 };
  render(
    <IngestionRunStrip
      projectId="project"
      run={
        {
          status: 'cancelled',
          stage: 'indexing',
          progress: 60,
          knowledge_set_name: 'Docs',
          new_count: 0,
          changed_count: 0,
          unchanged_count: 0,
          removed_count: 0,
          failed_count: 0,
          embedding_usage: usage,
        } as unknown as IngestionRun
      }
      displayStatus="cancelled"
      busy={false}
      detailsOpen={false}
      onCancel={vi.fn()}
      onToggleDetails={vi.fn()}
      onDismiss={vi.fn()}
    />,
  );
  expect(screen.getByText(embeddingUsageText(usage))).toBeVisible();
});

// A12: an Embed node saved under another server model offers a one-click way out.
test('A12: a stale embedding model offers the server settings', () => {
  const extra = { serverEmbedding: embedding } as Partial<
    ComponentProps<typeof IngestionNodeSettings>
  >;
  render(
    <NodeHarness
      initial={{
        id: 'embed',
        type: 'embed',
        provider: 'openrouter',
        model: 'openai/text-embedding-3-large',
        dimensions: 3072,
        config_version: '1',
      }}
      extra={extra}
    />,
  );
  expect(screen.getByRole('button', { name: "Use the server's embedding settings" })).toBeVisible();
});

// A13: a Chunk validation issue is mapped to its field.
test('A13: a chunk server error maps to its field', () => {
  const nodes = defaultIngestionDraft(embedding, []).execution.nodes;
  const position = nodes.findIndex((node) => node.type === 'chunk');
  const errors = serverFieldErrors(
    [
      {
        loc: ['body', 'execution', 'nodes', position, 'chunk', 'section_token', 'target_tokens'],
        msg: 'Input should be a valid integer',
      },
    ],
    nodes,
  );
  expect(errors).toEqual({ 'chunk:chunk.target_tokens': 'Input should be a valid integer' });
});

// A15: a method starts from the server's capability defaults, not values of its own.
// Slice 4 replaced the method select with two choices; the character window is only for
// saved versions, so its defaults are checked on the model.
test('A15: switching the method starts from the capability defaults', () => {
  const capabilities = {
    quality_policies: [],
    chunking_profiles: [
      {
        id: 'parent_child',
        name: 'Parent and child',
        description: '',
        recommended: false,
        settings: {
          child_target_tokens: 200,
          child_maximum_tokens: 300,
          child_overlap_tokens: 30,
          parent_target_tokens: 800,
          parent_maximum_tokens: 1000,
          add_heading_context: true,
          config_version: 'parent-child-v2',
        },
      },
      {
        id: 'character_window',
        name: 'Character window (compatibility)',
        description: '',
        recommended: false,
        settings: { size: 800, overlap: 120, config_version: 'character-window-v1' },
      },
    ],
  } as unknown as ExtractionCapabilities;
  render(
    <NodeHarness
      initial={{
        id: 'chunk',
        type: 'chunk',
        algorithm: 'section_token',
        unit: 'tokens',
        tokenizer_version: 'utf8-byte-v1',
        target_tokens: 600,
        maximum_tokens: 800,
        overlap_tokens: 80,
        add_heading_context: true,
        config_version: 'section-token-v2',
      }}
      extra={{ extractionCapabilities: capabilities }}
    />,
  );
  fireEvent.click(screen.getByRole('radio', { name: /Parent and child/ }));
  expect(screen.getByLabelText('Child target size (bytes)')).toHaveValue(200);
  expect(screen.getByLabelText('Parent maximum size (bytes)')).toHaveValue(1000);
  expect(defaultChunkNode('chunk', 'character_window', capabilities)).toMatchObject({
    size: 800,
    overlap: 120,
  });
});

// A16: switching the chunking method says what was replaced and can be undone.
test('A16: switching the chunking method offers Undo', () => {
  let latest: IngestionNode | undefined;
  render(
    <NodeHarness
      initial={{
        id: 'chunk',
        type: 'chunk',
        algorithm: 'section_token',
        unit: 'tokens',
        tokenizer_version: 'utf8-byte-v1',
        target_tokens: 500,
        maximum_tokens: 800,
        overlap_tokens: 80,
        add_heading_context: true,
        config_version: 'section-token-v2',
      }}
      onChange={(node) => (latest = node)}
    />,
  );
  fireEvent.click(screen.getByRole('radio', { name: /Parent and child/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
  expect(latest).toMatchObject({ algorithm: 'section_token', target_tokens: 500 });
});

function CleanPanelHarness({ onChange }: { onChange: (node: Clean) => void }) {
  const [node, setNode] = useState<Clean>(structuredClone(structureClean));
  onChange(node);
  return <CleanSettings node={node} errors={{}} update={setNode} />;
}

// A17: the literal box keeps typed spaces and new lines (Slice 4: "Text to remove").
test('A17: the literal text box keeps spaces and new lines while typing', () => {
  render(<CleanPanelHarness onChange={() => undefined} />);
  const box = screen.getByLabelText('Text to remove');
  fireEvent.change(box, { target: { value: 'Page 1 of \n' } });
  expect(box).toHaveValue('Page 1 of \n');
});

// A18: "Preserve structured blocks" cannot be switched off, so it has no toggle.
test('A18: Preserve structured blocks has no on/off toggle', () => {
  render(<CleanHarness onChange={() => undefined} />);
  expect(screen.queryByRole('checkbox', { name: /Preserve structured blocks/ })).toBeNull();
});

// A19: no placeholder literal can be saved. Slice 4 adds literal text only through the
// "Text to remove" box: empty text removes the step, and the step list does not offer it.
test('A19: a new literal step saves no placeholder', () => {
  let latest: Clean | undefined;
  render(
    <CleanPanelHarness
      onChange={(node) => {
        latest = node;
      }}
    />,
  );
  const box = screen.getByLabelText('Text to remove');
  fireEvent.change(box, { target: { value: '' } });
  expect(latest?.steps?.some((step) => step.type === 'remove_literal_boilerplate')).toBe(false);
  expect(screen.queryByRole('option', { name: 'Remove literal boilerplate' })).toBeNull();
  fireEvent.change(box, { target: { value: 'Confidential' } });
  const step = latest?.steps?.find((value) => value.type === 'remove_literal_boilerplate');
  expect(step).toMatchObject({ values: ['Confidential'] });
});

// A20: a Clean server error is attached to its step's field.
test('A20: a clean step server error maps to its field', () => {
  const nodes = defaultIngestionDraft(embedding, []).execution.nodes;
  const position = nodes.findIndex((node) => node.type === 'clean');
  const errors = serverFieldErrors(
    [
      {
        loc: ['body', 'execution', 'nodes', position, 'clean', 'steps', 2, 'values'],
        msg: 'List should have at least 1 item after validation, not 0',
      },
    ],
    nodes,
  );
  expect(Object.keys(errors)).toEqual(['clean:clean.steps.2.values']);
});

// A22: guided setup creates new drafts, which offer only the structure-aware cleaner.
test('A22: guided setup offers no compatibility cleaner', () => {
  render(
    <ProcessingStep
      guided={newGuidedDraft(embedding)}
      onExtract={vi.fn()}
      onClean={vi.fn()}
      onChunk={vi.fn()}
      onUseShared={vi.fn()}
    />,
  );
  const clean = screen.getByLabelText(/Clean/);
  expect(within(clean).queryByRole('option', { name: 'Compatibility cleaner' })).toBeNull();
});
