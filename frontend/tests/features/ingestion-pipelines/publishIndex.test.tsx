import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, test } from 'vitest';

import { PublishIndexSettings } from '../../../src/features/ingestion-pipelines/components/PublishIndexSettings';
import {
  defaultIngestionDraft,
  renameIngestionDraft,
  serverFieldErrors,
  setIndexLayout,
} from '../../../src/features/ingestion-pipelines/editorModel';
import type { IngestionNode } from '../../../src/features/ingestion-pipelines/model';
import type { KnowledgeSet } from '../../../src/features/documents/model';

type Publish = Extract<IngestionNode, { type: 'publish_index' }>;

const embedding = {
  provider: 'openrouter',
  model: 'openai/text-embedding-3-small',
  dimensions: 1536,
  revision: '1',
  endpoint_id: 'endpoint',
};

const sets: KnowledgeSet[] = [
  {
    id: 'set-docs',
    project_id: 'project',
    name: 'Docs',
    current_ready_index_id: 'index-3',
    current_version: 3,
    latest_version: 3,
    publishing_pipelines: [
      { id: 'pipeline-a', name: 'Docs pipeline' },
      { id: 'pipeline-b', name: 'Nightly docs' },
    ],
    created_at: '2026-10-17T00:00:00Z',
  },
];

let latest: Publish | undefined;

function Harness({
  initial,
  pipelineId,
  serverError,
}: {
  initial: Publish;
  pipelineId?: string;
  serverError?: string;
}) {
  const [node, setNode] = useState(initial);
  latest = node;
  return (
    <PublishIndexSettings
      node={node}
      knowledgeSets={sets}
      pipelineId={pipelineId}
      defaultName="My pipeline"
      serverError={serverError}
      update={setNode}
    />
  );
}

const fresh: Publish = {
  id: 'publish',
  type: 'publish_index',
  knowledge_set_name: 'My pipeline',
  destination: 'new',
};

test('switching to an existing index and back restores the typed new name', () => {
  render(<Harness initial={fresh} />);
  fireEvent.change(screen.getByLabelText('Index name'), { target: { value: 'Handbook' } });
  fireEvent.click(screen.getByRole('radio', { name: /Add a version to an existing index/ }));
  expect(latest).toMatchObject({
    knowledge_set_id: 'set-docs',
    knowledge_set_name: 'Docs',
    destination: 'existing',
  });
  expect(screen.getByLabelText('Index')).toHaveValue('set-docs');

  fireEvent.click(screen.getByRole('radio', { name: /New index/ }));
  expect(screen.getByLabelText('Index name')).toHaveValue('Handbook');
  expect(latest).toEqual({ ...fresh, knowledge_set_name: 'Handbook' });
});

test('a new name that another pipeline already uses is a field error, ignoring case', () => {
  render(<Harness initial={fresh} />);
  const field = screen.getByLabelText('Index name');
  fireEvent.change(field, { target: { value: 'docs' } });
  expect(field).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByRole('alert')).toHaveTextContent('An index named "Docs" already exists.');
  expect(field).toHaveAccessibleDescription(/already exists/);
});

test("a pipeline's own index name is not a clash", () => {
  render(<Harness initial={{ ...fresh, knowledge_set_name: 'Docs' }} pipelineId="pipeline-a" />);
  expect(screen.getByLabelText('Index name')).not.toHaveAttribute('aria-invalid', 'true');
});

test('the server error is shown on the name field', () => {
  render(<Harness initial={fresh} serverError='An index named "X" already exists.' />);
  expect(screen.getByLabelText('Index name')).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByRole('alert')).toBeVisible();
});

test('an existing index shown with the other pipelines that publish to it', () => {
  render(
    <Harness
      initial={{
        id: 'publish',
        type: 'publish_index',
        knowledge_set_name: 'Docs',
        knowledge_set_id: 'set-docs',
        destination: 'existing',
      }}
      pipelineId="pipeline-a"
    />,
  );
  expect(
    screen.getByText('Also published by Nightly docs. Each run replaces its current version.'),
  ).toBeVisible();
});

test('a new draft publishes to its own name and the name follows a rename', () => {
  const draft = defaultIngestionDraft(embedding, []);
  const publish = () =>
    renamed.execution.nodes.find((node) => node.type === 'publish_index') as Publish;
  let renamed = renameIngestionDraft(draft, 'Python tutorial');
  expect(publish()).toMatchObject({
    knowledge_set_name: 'Python tutorial',
    destination: 'new',
  });

  // A name the user typed no longer follows the pipeline name.
  renamed = {
    ...renamed,
    execution: {
      ...renamed.execution,
      nodes: renamed.execution.nodes.map((node) =>
        node.type === 'publish_index' ? { ...node, knowledge_set_name: 'Handbook' } : node,
      ),
    },
  };
  renamed = renameIngestionDraft(renamed, 'Python docs');
  expect(publish().knowledge_set_name).toBe('Handbook');
});

test('per-source branches publish new indexes that follow the pipeline name', () => {
  let draft = renameIngestionDraft(defaultIngestionDraft(embedding, []), 'Docs');
  draft = {
    ...draft,
    execution: {
      ...draft.execution,
      nodes: draft.execution.nodes.map((node) =>
        node.type === 'source'
          ? {
              ...node,
              config: {
                kind: 'website',
                selection: { mode: 'crawl', start_url: 'https://a.example/' },
                allowed_origins: ['https://a.example'],
                include_path_prefixes: [],
                exclude_path_prefixes: [],
                max_pages: 10,
                max_depth: 2,
                requests_per_second: 1,
              },
            }
          : node,
      ),
    },
  } as typeof draft;
  const perSource = setIndexLayout(draft, 'per_source');
  const renamed = renameIngestionDraft(perSource, 'Handbook');
  expect(renamed.execution.nodes.find((node) => node.type === 'publish_index')).toMatchObject({
    knowledge_set_name: 'Handbook · a.example',
    destination: 'new',
  });
});

test('a server error on the index name maps to the Publish field', () => {
  const nodes = defaultIngestionDraft(embedding, []).execution.nodes;
  const position = nodes.findIndex((node) => node.type === 'publish_index');
  expect(
    serverFieldErrors(
      [{ loc: ['execution', 'nodes', position, 'knowledge_set_name'], msg: 'Taken.' }],
      nodes,
    ),
  ).toEqual({ 'publish:publish.knowledge_set_name': 'Taken.' });
});
