import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import { IngestionRunStrip } from '../../../src/features/ingestion-pipelines/components/IngestionRunStrip';
import type { IngestionRun } from '../../../src/features/ingestion-pipelines/model';

test('shows live Website crawl progress while discovering', () => {
  render(
    <IngestionRunStrip
      projectId="project-1"
      run={
        {
          status: 'running',
          stage: 'discovering',
          progress: 17,
          discovered_count: 1000,
          processed_count: 412,
          knowledge_set_name: 'Docs',
          new_count: 0,
          changed_count: 0,
          unchanged_count: 0,
          removed_count: 0,
          fetch_policies: { source: { max_pages: 1000 } },
        } as unknown as IngestionRun
      }
      displayStatus="running"
      busy={false}
      detailsOpen={false}
      onCancel={vi.fn()}
      onToggleDetails={vi.fn()}
      onDismiss={vi.fn()}
    />,
  );
  expect(screen.getByText('412 / 1000 discovered URLs checked')).toBeVisible();
});

test('marks a multi-source run that published with a failed site', () => {
  render(
    <IngestionRunStrip
      projectId="project-1"
      run={
        {
          status: 'succeeded',
          stage: 'complete',
          progress: 100,
          knowledge_set_name: 'Docs',
          new_count: 1,
          changed_count: 0,
          unchanged_count: 0,
          removed_count: 0,
          failed_count: 0,
          published_index_id: 'index-1',
          published_index_version: 2,
          completion: 'with_warnings',
          source_outcomes: [
            {
              source_node_id: 'source',
              location: 'https://a.example/',
              status: 'succeeded',
              error_code: null,
              message: null,
              included_count: 1,
              failed_count: 0,
              carried_forward_count: 0,
            },
            {
              source_node_id: 'source-2',
              location: 'https://b.example/',
              status: 'failed',
              error_code: 'sitemap_unavailable',
              message: 'The sitemap could not be read.',
              included_count: 0,
              failed_count: 0,
              carried_forward_count: 3,
            },
          ],
        } as unknown as IngestionRun
      }
      displayStatus="succeeded"
      busy={false}
      detailsOpen={false}
      onCancel={vi.fn()}
      onToggleDetails={vi.fn()}
      onDismiss={vi.fn()}
    />,
  );
  expect(screen.getByText('with warnings')).toBeVisible();
  expect(screen.getByText(/3 kept from earlier/)).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent(
    '1 of 2 sources failed; their earlier pages were kept. Open Run details for the reasons.',
  );
  expect(screen.getByText('Index version 2 is ready to use')).toBeVisible();
});
