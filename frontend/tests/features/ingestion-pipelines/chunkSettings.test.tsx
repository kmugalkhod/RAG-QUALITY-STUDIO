import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, test, vi } from 'vitest';

import { ChunkSettings } from '../../../src/features/ingestion-pipelines/components/ChunkSettings';
import { IngestionRunStrip } from '../../../src/features/ingestion-pipelines/components/IngestionRunStrip';
import { chunkFieldProblems } from '../../../src/features/ingestion-pipelines/editorModel';
import type { ChunkNode, IngestionRun } from '../../../src/features/ingestion-pipelines/model';

const section: ChunkNode = {
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
};

let latest: ChunkNode | undefined;

function Harness({
  initial = section,
  serverErrors = {},
}: {
  initial?: ChunkNode;
  serverErrors?: Record<string, string>;
}) {
  const [node, setNode] = useState(initial);
  latest = node;
  return (
    <ChunkSettings node={node} websiteSource={false} serverErrors={serverErrors} update={setNode} />
  );
}

test('an empty field is invalid on its own field, not read as 0', () => {
  render(<Harness />);
  const target = screen.getByLabelText('Target tokens');
  fireEvent.change(target, { target: { value: '' } });
  expect(target).toHaveValue(null);
  expect(target).toHaveAttribute('aria-invalid', 'true');
  expect(target).toHaveAccessibleDescription('Enter a whole number.');
  expect(Number.isNaN((latest as { target_tokens: number }).target_tokens)).toBe(true);
});

test('overlap at or above the target is an error on the overlap field', () => {
  render(<Harness />);
  fireEvent.change(screen.getByLabelText('Overlap tokens'), { target: { value: '600' } });
  expect(screen.getByLabelText('Overlap tokens')).toHaveAccessibleDescription(
    'Overlap must be smaller than the target.',
  );
  expect(screen.getByLabelText('Target tokens')).not.toHaveAttribute('aria-invalid', 'true');
});

test('a maximum that can exceed the embedding limit is flagged and can be reset', () => {
  render(<Harness initial={{ ...section, maximum_tokens: 16384 }} />);
  expect(screen.getByLabelText('Hard maximum tokens')).toHaveAccessibleDescription(
    /At most 7,891 bytes/,
  );
  expect(screen.getByText('Passages can be too large to embed')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Reset sizes to recommended' }));
  expect(latest).toMatchObject({ maximum_tokens: 800, target_tokens: 600, overlap_tokens: 80 });
  expect(screen.queryByText('Passages can be too large to embed')).toBeNull();
});

test('a server error shows on its field', () => {
  render(<Harness serverErrors={{ 'chunk.target_tokens': 'Input should be at least 64' }} />);
  expect(screen.getByLabelText('Target tokens')).toHaveAccessibleDescription(
    'Input should be at least 64',
  );
});

test('parent and child limits name the field that breaks them', () => {
  expect(
    chunkFieldProblems({
      id: 'chunk',
      type: 'chunk',
      algorithm: 'parent_child',
      child_target_tokens: 240,
      child_maximum_tokens: 1300,
      child_overlap_tokens: 240,
      parent_target_tokens: 900,
      parent_maximum_tokens: 1200,
      add_heading_context: true,
    }),
  ).toEqual({
    child_overlap_tokens: 'Child overlap must be smaller than the child target.',
    parent_maximum_tokens: 'The parent maximum cannot be smaller than the child maximum.',
  });
});

function runStrip(run: Partial<IngestionRun>) {
  render(
    <IngestionRunStrip
      projectId="project"
      run={
        {
          stage: 'indexing',
          progress: 50,
          knowledge_set_name: 'Docs',
          new_count: 0,
          changed_count: 0,
          unchanged_count: 0,
          removed_count: 0,
          failed_count: 0,
          embedded_count: 32,
          chunk_count: 64,
          ...run,
        } as IngestionRun
      }
      displayStatus={run.status === 'running' ? 'running' : 'failed'}
      busy={false}
      detailsOpen={false}
      onCancel={vi.fn()}
      onToggleDetails={vi.fn()}
      onDismiss={vi.fn()}
    />,
  );
}

test('a running run says why its embedding waits', () => {
  runStrip({
    status: 'running',
    waiting_reason: 'Waiting for embedding request budget, resumes in 20 s',
  });
  expect(screen.getByText('Waiting for embedding request budget, resumes in 20 s')).toBeVisible();
});

test('a failed run without an index says no embedding was requested', () => {
  runStrip({ status: 'failed', embedding_usage: null, error: 'A file could not be read.' });
  expect(screen.getByText('No embedding requests were made.')).toBeVisible();
});
