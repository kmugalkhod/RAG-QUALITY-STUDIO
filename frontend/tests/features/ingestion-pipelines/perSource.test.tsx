import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import { IngestionGroupStrip } from '../../../src/features/ingestion-pipelines/components/IngestionGroupStrip';
import {
  addWebsiteSource,
  branchChain,
  branchExecution,
  defaultIngestionDraft,
  defaultWebsite,
  nodeLabel,
  removeSource,
  setIndexLayout,
  sourceNodes,
} from '../../../src/features/ingestion-pipelines/editorModel';
import type {
  IngestionPipelineDraft,
  IngestionRun,
  IngestionRunGroup,
} from '../../../src/features/ingestion-pipelines/model';

const embedding = {
  provider: 'test',
  model: 'embedding-v1',
  dimensions: 3,
  revision: 'revision-1',
  endpoint_id: 'endpoint-1',
};

function twoSites(): IngestionPipelineDraft {
  const base = defaultIngestionDraft(embedding, []);
  const draft: IngestionPipelineDraft = {
    ...base,
    name: 'Docs',
    execution: {
      ...base.execution,
      nodes: base.execution.nodes.map((node) =>
        node.type === 'source'
          ? {
              ...node,
              config: {
                ...defaultWebsite(),
                selection: { mode: 'crawl', start_url: 'https://a.example/docs/' },
              },
            }
          : node,
      ),
    },
  };
  return addWebsiteSource(draft).draft;
}

test('one index per source gives every source its own chain and index name', () => {
  const draft = setIndexLayout(twoSites(), 'per_source');
  expect(draft.execution.index_layout).toBe('per_source');
  const [first, second] = sourceNodes(draft);
  const firstChain = branchChain(draft, first.id);
  const secondChain = branchChain(draft, second.id);
  expect(firstChain.map((node) => node.type)).toEqual([
    'extract',
    'clean',
    'chunk',
    'embed',
    'publish_index',
  ]);
  expect(secondChain.map((node) => node.type)).toEqual(firstChain.map((node) => node.type));
  expect(new Set([...firstChain, ...secondChain].map((node) => node.id)).size).toBe(10);
  expect(firstChain.at(-1)).toMatchObject({ knowledge_set_name: 'Docs · a.example' });
  expect(secondChain.at(-1)).toMatchObject({ knowledge_set_name: 'Docs · Website 2' });
  expect(draft.execution.edges).toHaveLength(10);
  expect(nodeLabel(draft, secondChain[2])).toBe('Chunk · Website 2');
  expect(Object.keys(draft.layout.positions)).toHaveLength(12);

  const preview = branchExecution(draft, second.id);
  expect(preview.index_layout).toBe('merged');
  expect(preview.nodes.map((node) => node.id)).toEqual([
    second.id,
    ...secondChain.map((node) => node.id),
  ]);
  expect(preview.edges).toHaveLength(5);
});

test('adding and removing sources keeps one complete chain per source', () => {
  let draft = setIndexLayout(twoSites(), 'per_source');
  const added = addWebsiteSource(draft);
  draft = added.draft;
  expect(branchChain(draft, added.nodeId)).toHaveLength(5);
  expect(draft.execution.nodes).toHaveLength(18);

  draft = removeSource(draft, sourceNodes(draft)[1].id);
  expect(draft.execution.nodes).toHaveLength(12);
  expect(draft.execution.edges).toHaveLength(10);
  for (const source of sourceNodes(draft)) {
    expect(branchChain(draft, source.id)).toHaveLength(5);
  }
});

test('switching back to one index keeps the first branch and wires every source to it', () => {
  const perSource = setIndexLayout(twoSites(), 'per_source');
  const firstChain = branchChain(perSource, sourceNodes(perSource)[0].id);
  const merged = setIndexLayout(perSource, 'merged');
  expect(merged.execution.index_layout).toBe('merged');
  expect(merged.execution.nodes).toHaveLength(7);
  const extract = firstChain[0].id;
  for (const source of sourceNodes(merged)) {
    expect(merged.execution.edges).toContainEqual({ source: source.id, target: extract });
  }
  expect(merged.execution.nodes.at(-1)).toMatchObject({ knowledge_set_name: 'Docs' });
});

function run(overrides: Partial<IngestionRun>): IngestionRun {
  return {
    id: 'run',
    status: 'succeeded',
    stage: 'complete',
    progress: 100,
    knowledge_set_name: 'Docs · a.example',
    published_index_id: null,
    published_index_version: null,
    error: null,
    ...overrides,
  } as IngestionRun;
}

test('the group strip lists each source index with its outcome', () => {
  const onShowDetails = vi.fn();
  const group: IngestionRunGroup = {
    id: 'group',
    project_id: 'project',
    pipeline_version_id: 'version',
    schedule_id: null,
    trigger_kind: 'manual',
    status: 'partial',
    completion: null,
    created_at: '2026-10-05T00:00:00Z',
    runs: [
      run({
        id: 'a',
        branch_source_node_id: 'source',
        published_index_id: 'index-a',
        published_index_version: 1,
      }),
      run({
        id: 'b',
        branch_source_node_id: 'source-2',
        status: 'failed',
        knowledge_set_name: 'Docs · b.example',
        error: 'The sitemap could not be read.',
      }),
    ],
  };
  render(
    <IngestionGroupStrip
      projectId="project"
      group={group}
      busy={false}
      label={(id) => (id === 'source' ? 'Website 1' : 'Website 2')}
      onCancel={vi.fn()}
      onShowDetails={onShowDetails}
      onDismiss={vi.fn()}
    />,
  );
  expect(screen.getByText('Some indexes failed')).toBeVisible();
  expect(screen.getByText('2 indexes, one per source')).toBeVisible();
  expect(screen.getByText('Docs · a.example · version 1')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Inspect index' })).toHaveAttribute(
    'href',
    '#/projects/project/knowledge-base?view=indexes&index=index-a',
  );
  expect(screen.getByRole('alert')).toHaveTextContent('The sitemap could not be read.');
  fireEvent.click(screen.getAllByRole('button', { name: 'Run details' })[1]);
  expect(onShowDetails).toHaveBeenCalledWith(expect.objectContaining({ id: 'b' }));
});
