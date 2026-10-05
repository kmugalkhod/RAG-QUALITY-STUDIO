import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import { StageScope } from '../../../src/features/ingestion-pipelines/components/StageScope';
import {
  addWebsiteSource,
  branchChain,
  defaultIngestionDraft,
  defaultWebsite,
  setIndexLayout,
  sourceNodes,
} from '../../../src/features/ingestion-pipelines/editorModel';
import type {
  IngestionNode,
  IngestionPipelineDraft,
  IngestionRun,
  IngestionRunGroup,
} from '../../../src/features/ingestion-pipelines/model';
import {
  addSharedWebsiteSource,
  combinedState,
  customStagesOf,
  resetToShared,
  setSharedIndexLayout,
  sharedStage,
  sharedTargets,
  sourceRunStatus,
  sourcesViewCards,
  stageNodes,
  updateNodes,
  usesSourcesPanel,
} from '../../../src/features/ingestion-pipelines/sourcesView';

const embedding = {
  provider: 'test',
  model: 'embedding-v1',
  dimensions: 3,
  revision: 'revision-1',
  endpoint_id: 'endpoint-1',
};

function sites(count: number): IngestionPipelineDraft {
  const base = defaultIngestionDraft(embedding, []);
  let draft: IngestionPipelineDraft = {
    ...base,
    name: 'Docs',
    execution: {
      ...base.execution,
      nodes: base.execution.nodes.map((node) =>
        node.type === 'source' ? { ...node, config: defaultWebsite() } : node,
      ),
    },
  };
  for (let index = 1; index < count; index += 1) {
    draft = addWebsiteSource(draft).draft;
  }
  return draft;
}

const describe = (node: IngestionNode) => (node.type === 'embed' ? node.model : node.type);

function embedOf(draft: IngestionPipelineDraft, sourceId: string) {
  return branchChain(draft, sourceId).find((node) => node.type === 'embed') as Extract<
    IngestionNode,
    { type: 'embed' }
  >;
}

function withEmbedModel(draft: IngestionPipelineDraft, sourceId: string, model: string) {
  return updateNodes(draft, [embedOf(draft, sourceId).id], (node) =>
    node.type === 'embed' ? { ...node, model } : node,
  );
}

test('Website pipelines on schema 2 use the sources panel', () => {
  expect(usesSourcesPanel(sites(1))).toBe(true);
  const legacy = sites(1);
  expect(
    usesSourcesPanel({ ...legacy, execution: { ...legacy.execution, schema_version: 1 } }),
  ).toBe(false);
});

test('a stage is shared until one source changes it', () => {
  let draft = setIndexLayout(sites(3), 'per_source');
  const [first, second, third] = sourceNodes(draft);
  expect(sharedStage(draft, 'embed').custom).toEqual([]);

  draft = withEmbedModel(draft, third.id, 'embedding-large');
  const shared = sharedStage(draft, 'embed');
  expect(shared.custom).toEqual([third.id]);
  expect(shared.node).toMatchObject({ model: 'embedding-v1' });
  expect(customStagesOf(draft, third.id)).toEqual(['embed']);
  expect(customStagesOf(draft, second.id)).toEqual([]);

  // Shared edits change every source that does not customize the stage.
  const targets = sharedTargets(draft, 'embed');
  expect(targets).toEqual([embedOf(draft, first.id).id, embedOf(draft, second.id).id]);
  draft = updateNodes(draft, targets, (node) =>
    node.type === 'embed' ? { ...node, dimensions: 8 } : node,
  );
  expect(embedOf(draft, second.id).dimensions).toBe(8);
  expect(embedOf(draft, third.id).dimensions).toBe(3);
});

test('a source marked customized keeps its own settings before they differ', () => {
  const draft = setIndexLayout(sites(2), 'per_source');
  const [first, second] = sourceNodes(draft);
  const customized = { embed: [first.id] };
  const shared = sharedStage(draft, 'embed', customized);
  expect(shared.custom).toEqual([first.id]);
  expect(sharedTargets(draft, 'embed', customized)).toEqual([embedOf(draft, second.id).id]);
});

test('using the shared settings again copies them back to the source', () => {
  let draft = setIndexLayout(sites(3), 'per_source');
  const third = sourceNodes(draft)[2];
  draft = withEmbedModel(draft, third.id, 'embedding-large');
  draft = resetToShared(draft, 'embed', third.id);
  expect(embedOf(draft, third.id).model).toBe('embedding-v1');
  expect(sharedStage(draft, 'embed').custom).toEqual([]);
});

test('a new source and a switch back to one index use the shared settings', () => {
  // The first source customizes the stage, so the shared settings are the others'.
  let draft = setIndexLayout(sites(3), 'per_source');
  const first = sourceNodes(draft)[0];
  draft = withEmbedModel(draft, first.id, 'embedding-large');

  const added = addSharedWebsiteSource(draft);
  expect(embedOf(added.draft, added.nodeId).model).toBe('embedding-v1');
  expect(branchChain(added.draft, added.nodeId)).toHaveLength(5);

  const merged = setSharedIndexLayout(draft, 'merged');
  expect(merged.execution.index_layout).toBe('merged');
  expect(merged.execution.nodes.find((node) => node.type === 'embed')).toMatchObject({
    model: 'embedding-v1',
  });
});

test('the canvas shows the sources once and every stage once', () => {
  const merged = sites(5);
  expect(sourcesViewCards(merged, describe).cards.map((card) => card.label)).toEqual([
    '5 website sources',
    'Extract',
    'Clean',
    'Chunk',
    'Embed',
    'Publish index',
  ]);

  let perSource = setIndexLayout(merged, 'per_source');
  perSource = withEmbedModel(perSource, sourceNodes(perSource)[4].id, 'embedding-large');
  const { cards, edges } = sourcesViewCards(perSource, describe);
  expect(cards).toHaveLength(11);
  expect(cards.find((card) => card.label === 'Embed')?.detail).toBe(
    '1 source customizes this · embedding-v1',
  );
  expect(cards.find((card) => card.label === 'Publish 5 indexes')).toBeDefined();
  expect(cards.filter((card) => card.id.startsWith('view:index:'))).toHaveLength(5);
  expect(edges).toHaveLength(10);
  expect(cards.find((card) => card.label === 'Chunk')?.members).toEqual(
    stageNodes(perSource, 'chunk').map((entry) => entry.node.id),
  );
});

test('several stage states combine into the most urgent one', () => {
  expect(combinedState([undefined, undefined])).toBeUndefined();
  expect(combinedState(['succeeded', 'succeeded'])).toBe('succeeded');
  expect(combinedState(['succeeded', 'failed'])).toBe('failed');
  expect(combinedState(['failed', 'running', 'queued'])).toBe('running');
});

function run(overrides: Partial<IngestionRun>): IngestionRun {
  return {
    id: 'run',
    status: 'succeeded',
    progress: 100,
    discovered_count: 3,
    new_count: 3,
    changed_count: 0,
    unchanged_count: 0,
    error: null,
    source_outcomes: [],
    ...overrides,
  } as unknown as IngestionRun;
}

const outcome = (sourceId: string, values: object) => ({
  source_node_id: sourceId,
  location: null,
  status: 'succeeded',
  error_code: null,
  message: null,
  included_count: 0,
  failed_count: 0,
  carried_forward_count: 0,
  ...values,
});

test('each source card says what the last run did for it', () => {
  const merged = run({
    source_outcomes: [
      outcome('source', { included_count: 12 }),
      outcome('source-2', {
        status: 'failed',
        message: 'The sitemap could not be read.',
        carried_forward_count: 2,
      }),
      outcome('source-3', { status: 'skipped', carried_forward_count: 4 }),
    ] as IngestionRun['source_outcomes'],
  });
  expect(sourceRunStatus('source', merged, undefined)).toEqual({
    tone: 'succeeded',
    label: 'Collected',
    detail: '12 pages included',
  });
  expect(sourceRunStatus('source-2', merged, undefined)).toEqual({
    tone: 'failed',
    label: 'Failed',
    detail: 'The sitemap could not be read. · 2 pages kept from earlier',
  });
  expect(sourceRunStatus('source-3', merged, undefined)?.label).toBe('Not refreshed');
  // A source added after the run was never read by it.
  expect(sourceRunStatus('source-4', merged, undefined)).toBeUndefined();

  const group = {
    runs: [
      run({ branch_source_node_id: 'source', source_outcomes: [] }),
      run({ branch_source_node_id: 'source-2', status: 'running', progress: 40 }),
    ],
  } as unknown as IngestionRunGroup;
  expect(sourceRunStatus('source', group.runs[0], group)?.label).toBe('Published');
  expect(sourceRunStatus('source-2', undefined, group)).toMatchObject({
    tone: 'running',
    label: 'Running',
  });
  expect(sourceRunStatus('source-3', undefined, group)).toBeUndefined();
});

test('a stage can be customized for one source and reset', () => {
  const onCustomize = vi.fn();
  const onUseShared = vi.fn();
  const onChange = vi.fn();
  const options = [
    { value: 'all', label: 'All sources (shared)' },
    { value: 'source-2', label: 'Only b.example' },
  ];
  const { rerender } = render(
    <StageScope
      stageNoun="chunking"
      value="source-2"
      options={options}
      mode={{ kind: 'inherit', sourceName: 'b.example', sharedSummary: '800 tokens' }}
      onChange={onChange}
      onCustomize={onCustomize}
      onUseShared={onUseShared}
    />,
  );
  expect(screen.getByLabelText('Applies to')).toHaveValue('source-2');
  expect(screen.getByText('b.example follows the shared settings: 800 tokens.')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Customize chunking for this source' }));
  expect(onCustomize).toHaveBeenCalledOnce();

  rerender(
    <StageScope
      stageNoun="chunking"
      value="source-2"
      options={options}
      mode={{ kind: 'custom', sourceName: 'b.example' }}
      onChange={onChange}
      onCustomize={onCustomize}
      onUseShared={onUseShared}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Use shared settings' }));
  expect(onUseShared).toHaveBeenCalledOnce();

  rerender(
    <StageScope
      stageNoun="chunking"
      value="all"
      options={options}
      mode={{ kind: 'shared', customized: [{ id: 'source-2', name: 'b.example' }] }}
      onChange={onChange}
      onCustomize={onCustomize}
      onUseShared={onUseShared}
    />,
  );
  expect(screen.getByText(/does not follow changes to the shared chunking settings/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Show settings for b.example' }));
  expect(onChange).toHaveBeenCalledWith('source-2');
});
