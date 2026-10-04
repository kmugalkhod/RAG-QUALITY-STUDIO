import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, test } from 'vitest';

import { IngestionNodeSettings } from '../../../src/features/ingestion-pipelines/components/IngestionNodeSettings';
import {
  addWebsiteSource,
  addWebsiteSourceBlocked,
  defaultIngestionDraft,
  defaultWebsite,
  fieldErrorsForNode,
  removeSource,
  serverFieldErrors,
  sourceLabel,
  sourceNodes,
  websitePageTotal,
} from '../../../src/features/ingestion-pipelines/editorModel';
import type { IngestionPipelineDraft } from '../../../src/features/ingestion-pipelines/model';

const embedding = {
  provider: 'test',
  model: 'embedding-v1',
  dimensions: 3,
  revision: 'revision-1',
  endpoint_id: 'endpoint-1',
};

function websiteDraft(): IngestionPipelineDraft {
  const draft = defaultIngestionDraft(embedding, []);
  return {
    ...draft,
    execution: {
      ...draft.execution,
      nodes: draft.execution.nodes.map((node) =>
        node.type === 'source' ? { ...node, config: defaultWebsite() } : node,
      ),
    },
  };
}

test('adds Website sources wired into the shared Extract stage, up to five', () => {
  let draft = websiteDraft();
  expect(draft.execution.index_layout).toBe('merged');
  const added = addWebsiteSource(draft);
  draft = added.draft;

  expect(added.nodeId).toBe('source-2');
  expect(draft.execution.nodes.map((node) => node.id).slice(0, 3)).toEqual([
    'source',
    'source-2',
    'extract',
  ]);
  expect(draft.execution.edges).toContainEqual({ source: 'source-2', target: 'extract' });
  expect(draft.layout.positions['source-2']).toEqual({
    x: draft.layout.positions.source.x + 260,
    y: draft.layout.positions.source.y,
  });
  expect(sourceLabel(draft, 'source-2')).toBe('Website 2');

  for (let count = 0; count < 3; count += 1) {
    draft = addWebsiteSource(draft).draft;
  }
  expect(sourceNodes(draft)).toHaveLength(5);
  expect(addWebsiteSourceBlocked(draft)).toBe('A pipeline can read at most 5 Website sources.');
  expect(websitePageTotal(draft)).toBe(250);
});

test('only Website pipelines on schema 2 can add sources', () => {
  expect(addWebsiteSourceBlocked(defaultIngestionDraft(embedding, []))).toBe(
    'Only Website sources can be combined for now.',
  );
  const legacy = websiteDraft();
  legacy.execution.schema_version = 1;
  expect(addWebsiteSourceBlocked(legacy)).toBe('Upgrade this pipeline before adding sources.');
});

test('removes a source with its edge and position but never the last one', () => {
  const single = websiteDraft();
  expect(removeSource(single, 'source')).toBe(single);

  const { draft } = addWebsiteSource(single);
  const removed = removeSource(draft, 'source');
  expect(sourceNodes(removed).map((node) => node.id)).toEqual(['source-2']);
  expect(removed.execution.edges.some((edge) => edge.source === 'source')).toBe(false);
  expect(removed.layout.positions.source).toBeUndefined();
  expect(sourceLabel(removed, 'source-2')).toBe('Website');
});

test('scopes server field errors to the node they belong to', () => {
  const { draft } = addWebsiteSource(websiteDraft());
  const errors = serverFieldErrors(
    [0, 1].map((position) => ({
      loc: ['execution', 'nodes', position, 'config', 'website', 'max_pages'],
      msg: `Too many pages ${position}`,
    })),
    draft.execution.nodes,
  );
  expect(errors).toEqual({
    'source:website.max_pages': 'Too many pages 0',
    'source-2:website.max_pages': 'Too many pages 1',
  });
  expect(fieldErrorsForNode(errors, 'source-2')).toEqual({
    'website.max_pages': 'Too many pages 1',
  });
  expect(fieldErrorsForNode({ 'website.max_pages': 'shared' }, 'source')).toEqual({
    'website.max_pages': 'shared',
  });
});

function Harness() {
  const [draft, setDraft] = useState(() => addWebsiteSource(websiteDraft()).draft);
  const [selected, setSelected] = useState('source-2');
  const node = draft.execution.nodes.find((candidate) => candidate.id === selected);
  return (
    <IngestionNodeSettings
      projectId="project"
      selected={node}
      selectedNode={selected}
      nodes={draft.execution.nodes}
      dirty
      validation={[]}
      connections={[]}
      documents={[]}
      knowledgeSets={[]}
      websiteSource
      schemaVersion={2}
      updateNode={() => undefined}
      changeSourceKind={() => undefined}
      sourceCount={sourceNodes(draft).length}
      sourceLabel={(id) => sourceLabel(draft, id)}
      addSourceBlocked={addWebsiteSourceBlocked(draft)}
      websitePageTotal={websitePageTotal(draft)}
      onAddSource={() => {
        const added = addWebsiteSource(draft);
        setDraft(added.draft);
        setSelected(added.nodeId);
      }}
      onRemoveSource={(id) => {
        const next = removeSource(draft, id);
        setDraft(next);
        setSelected(sourceNodes(next)[0].id);
      }}
      onSelectNode={setSelected}
    />
  );
}

test('adds and removes Website sources from labeled settings controls', () => {
  render(<Harness />);

  expect(screen.getByRole('heading', { name: 'Website 2 settings' })).toBeVisible();
  expect(screen.getByLabelText('Source type')).toBeDisabled();
  expect(screen.getByText('Remove the other sources to change the source type.')).toBeVisible();
  expect(screen.getByText(/2 of 5 Website sources/)).toBeVisible();
  expect(screen.getByText('Maximum pages across sources: 100 of 2,500.')).toBeVisible();

  fireEvent.click(screen.getByRole('button', { name: 'Add website source' }));
  expect(screen.getByRole('heading', { name: 'Website 3 settings' })).toBeVisible();
  expect(screen.getByRole('option', { name: '2 · Website 2' })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Remove Website 3' }));
  fireEvent.click(screen.getByRole('button', { name: 'Remove Website 1' }));
  expect(screen.getByRole('heading', { name: 'Website settings' })).toBeVisible();
  expect(screen.getByLabelText('Source type')).toBeEnabled();
  expect(screen.queryByRole('button', { name: /^Remove/ })).toBeNull();
});
