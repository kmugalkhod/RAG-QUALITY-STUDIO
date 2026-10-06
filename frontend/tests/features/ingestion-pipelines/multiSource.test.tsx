import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, test, vi } from 'vitest';

import { IngestionNodeSettings } from '../../../src/features/ingestion-pipelines/components/IngestionNodeSettings';
import { IngestionSourcesPanel } from '../../../src/features/ingestion-pipelines/components/IngestionSourcesPanel';
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
    x: draft.layout.positions.source.x + 340,
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

function PanelHarness({
  refreshBlocked = null,
  onRefresh = () => undefined,
}: {
  refreshBlocked?: string | null;
  onRefresh?: (nodeId: string) => void;
}) {
  const [draft, setDraft] = useState(() => addWebsiteSource(websiteDraft()).draft);
  const [selected, setSelected] = useState('source-2');
  return (
    <IngestionSourcesPanel
      sources={sourceNodes(draft).map((node) => ({
        id: node.id,
        label: sourceLabel(draft, node.id),
        host: null,
        customized: [],
      }))}
      selectedSource={selected}
      indexLayout="merged"
      layoutLocked={null}
      maxSources={5}
      pageTotal={websitePageTotal(draft)}
      maxPages={2500}
      addBlocked={addWebsiteSourceBlocked(draft)}
      refreshLabel="Refresh only"
      refreshBlocked={refreshBlocked}
      onSelect={setSelected}
      onAdd={() => {
        const added = addWebsiteSource(draft);
        setDraft(added.draft);
        setSelected(added.nodeId);
      }}
      onRemove={(id) => {
        const next = removeSource(draft, id);
        setDraft(next);
        setSelected(sourceNodes(next)[0].id);
      }}
      onRefresh={onRefresh}
      onLayoutChange={() => undefined}
    />
  );
}

// A source's run and remove actions open in its card from the "⋯" button.
function action(source: string, name: string) {
  fireEvent.click(screen.getByRole('button', { name: `Actions for ${source}` }));
  return screen.getByRole('button', { name });
}

test('adds and removes Website sources from the sources panel', () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
  render(<PanelHarness />);

  expect(screen.getByText('2 of 5')).toBeVisible();
  expect(screen.getByText('Maximum pages across sources: 100 of 2,500.')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Website 2 settings' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  fireEvent.click(screen.getByRole('button', { name: 'Add website' }));
  expect(screen.getByRole('button', { name: 'Website 3 settings' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  expect(screen.queryByRole('button', { name: 'Remove Website 3' })).toBeNull();
  fireEvent.click(action('Website 3', 'Remove Website 3'));
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining('Remove Website 3'));
  // Cancelling the confirmation keeps the source.
  confirm.mockReturnValueOnce(false);
  fireEvent.click(action('Website 1', 'Remove Website 1'));
  expect(screen.getByText('2 of 5')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Remove Website 1' }));
  expect(screen.getByText('1 of 5')).toBeVisible();
  expect(screen.queryByRole('button', { name: /^Actions for/ })).toBeNull();
});

test('the source type is fixed while a pipeline has several sources', () => {
  const draft = addWebsiteSource(websiteDraft()).draft;
  render(
    <IngestionNodeSettings
      projectId="project"
      selected={draft.execution.nodes.find((node) => node.id === 'source-2')}
      selectedNode="source-2"
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
      sourceCount={2}
      sourceLabel={(id) => sourceLabel(draft, id)}
      onSelectNode={() => undefined}
    />,
  );
  expect(screen.getByRole('heading', { name: 'Website 2 settings' })).toBeVisible();
  expect(screen.getByLabelText('Source type')).toBeDisabled();
  expect(screen.getByText('Remove the other sources to change the source type.')).toBeVisible();
});

test('refreshes only one source when the saved version allows it', () => {
  const refreshed: string[] = [];
  const { unmount } = render(<PanelHarness onRefresh={(id) => refreshed.push(id)} />);
  fireEvent.click(action('Website 2', 'Refresh only Website 2'));
  expect(refreshed).toEqual(['source-2']);
  unmount();

  render(
    <PanelHarness
      refreshBlocked="Save or discard your changes first."
      onRefresh={(id) => refreshed.push(id)}
    />,
  );
  const button = action('Website 2', 'Refresh only Website 2');
  expect(button).toHaveAttribute('aria-disabled', 'true');
  fireEvent.click(button);
  expect(refreshed).toEqual(['source-2']);
  expect(button).toHaveAccessibleDescription('Save or discard your changes first.');
});
