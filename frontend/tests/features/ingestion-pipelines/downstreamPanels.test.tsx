import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import {
  EmbedSettings,
  previewEstimateText,
  runUsageText,
} from '../../../src/features/ingestion-pipelines/components/EmbedSettings';
import { IngestionGroupStrip } from '../../../src/features/ingestion-pipelines/components/IngestionGroupStrip';
import { chunkSummaryText } from '../../../src/features/ingestion-pipelines/components/IngestionResults';
import { replacedVersionText } from '../../../src/features/ingestion-pipelines/components/IngestionRunStrip';
import { publishedVersionText } from '../../../src/features/ingestion-pipelines/components/PublishIndexSettings';
import { describeIngestionNode } from '../../../src/features/ingestion-pipelines/editorModel';
import type {
  IngestionNode,
  IngestionRun,
  IngestionRunGroup,
  SourcePreview,
} from '../../../src/features/ingestion-pipelines/model';
import type { KnowledgeSet } from '../../../src/features/documents/model';

type Embed = Extract<IngestionNode, { type: 'embed' }>;

const embed: Embed = {
  id: 'embed',
  type: 'embed',
  provider: 'openrouter',
  model: 'openai/text-embedding-3-small',
  dimensions: 1536,
  config_version: '1',
};

const preview = {
  status: 'succeeded',
  cost_basis: { embedding_estimate: { chunks: 469, embedding_bytes: 324_000 } },
} as unknown as SourcePreview;

test('the Embed stage names the server model and estimates a preview at list price', () => {
  render(<EmbedSettings node={embed} preview={preview} update={vi.fn()} />);
  expect(
    screen.getByText('Uses openai/text-embedding-3-small (1,536 dimensions), set by the server.'),
  ).toBeVisible();
  // 324,000 bytes / 4 bytes per token × $0.02 per million tokens.
  expect(
    screen.getByText(
      /About 469 chunks, about 324 KB, estimated \$0\.0016 \(list price, estimate\)/,
    ),
  ).toBeVisible();
  expect(previewEstimateText({ ...preview, status: 'running' } as SourcePreview, embed.model)).toBe(
    undefined,
  );
  expect(previewEstimateText(preview, 'other/model')).toMatch(/cost unknown/);
});

test('the Embed stage reports new and reused vectors and the reported cost of the last run', () => {
  const run = {
    status: 'succeeded',
    embedded_count: 469,
    embedding_usage: { tokens: 74_728, cost_usd: 0.00149456, reused_vectors: 69 },
  } as IngestionRun;
  expect(runUsageText(run)).toBe('400 new, 69 reused, cost $0.0015.');
  expect(
    runUsageText({ ...run, embedding_usage: { tokens: null, cost_usd: null } } as IngestionRun),
  ).toBe('469 passages embedded, cost unknown.');
  render(<EmbedSettings node={embed} lastRun={run} update={vi.fn()} />);
  expect(screen.getByText('Last run: 400 new, 69 reused, cost $0.0015.')).toBeVisible();
});

test('a stale embedding model can be switched to the server settings in one click', () => {
  const update = vi.fn();
  render(
    <EmbedSettings
      node={{ ...embed, model: 'openai/text-embedding-3-large', dimensions: 3072 }}
      serverEmbedding={{
        provider: 'openrouter',
        model: 'openai/text-embedding-3-small',
        dimensions: 1536,
        revision: '1',
        endpoint_id: 'endpoint',
      }}
      update={update}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: "Use the server's embedding settings" }));
  expect(update).toHaveBeenCalledWith(embed);
});

test('the Publish stage says which version the next run publishes', () => {
  const set = {
    id: 'set',
    project_id: 'project',
    name: 'Python tutorial',
    current_ready_index_id: 'index-3',
    current_version: 3,
    latest_version: 3,
    created_at: '2026-10-18T00:00:00Z',
  } as KnowledgeSet;
  expect(publishedVersionText(set)).toBe(
    'This run publishes version 4 of Python tutorial. Version 3 stays available. Answer pipelines keep their version until you switch.',
  );
  expect(publishedVersionText(undefined, 'Docs')).toBe(
    'This run publishes version 1 of the new index Docs.',
  );
});

test('a run says what happened to the version answers use', () => {
  expect(
    replacedVersionText({
      status: 'succeeded',
      prior_index_version: 3,
      published_index_version: 4,
    } as IngestionRun),
  ).toBe('Replaced version 3; it remains available.');
  expect(replacedVersionText({ status: 'failed', prior_index_version: 3 } as IngestionRun)).toBe(
    'Version 3 is still current.',
  );
  expect(replacedVersionText({ status: 'succeeded' } as IngestionRun)).toBe(undefined);
});

test('a preview item summarizes its passages', () => {
  expect(
    chunkSummaryText({
      chunk_summary: {
        count: 133,
        median_bytes: 651,
        minimum_bytes: 12,
        maximum_bytes: 800,
        under_40_bytes: 2,
        over_embed_limit: 0,
      },
    }),
  ).toBe('133 passages · median 651 bytes · smallest 12 · largest 800 · 2 under 40 bytes');
});

test('canvas summaries say what was chosen', () => {
  const clean = {
    id: 'clean',
    type: 'clean',
    profile: 'standard-v1',
    config_version: 'deterministic-clean-v1',
  } as IngestionNode;
  expect(describeIngestionNode(clean, [])).toBe('Compatibility cleaner · upgrade available');
  expect(
    describeIngestionNode(
      {
        id: 'chunk',
        type: 'chunk',
        algorithm: 'parent_child',
        child_target_tokens: 160,
        child_maximum_tokens: 240,
        child_overlap_tokens: 24,
        parent_target_tokens: 600,
        parent_maximum_tokens: 800,
        add_heading_context: false,
        config_version: 'parent-child-v2',
      },
      [],
    ),
  ).toBe('Parent and child · Small · 1 changed');
});

test('a published branch can be used in an answer pipeline', () => {
  const group: IngestionRunGroup = {
    id: 'group',
    project_id: 'project',
    pipeline_version_id: 'version',
    schedule_id: null,
    trigger_kind: 'manual',
    status: 'succeeded',
    completion: 'complete',
    created_at: '2026-10-18T00:00:00Z',
    runs: [
      {
        id: 'a',
        branch_source_node_id: 'source',
        status: 'succeeded',
        stage: 'complete',
        progress: 100,
        knowledge_set_name: 'Docs · a.example',
        published_index_id: 'index-a',
        published_index_version: 2,
        error: null,
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
  fireEvent.click(screen.getByRole('button', { name: 'Details' }));
  expect(screen.getByRole('link', { name: 'Use in answer pipeline' })).toHaveAttribute(
    'href',
    '#/projects/project/pipelines/new?index=index-a',
  );
});
