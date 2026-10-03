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
