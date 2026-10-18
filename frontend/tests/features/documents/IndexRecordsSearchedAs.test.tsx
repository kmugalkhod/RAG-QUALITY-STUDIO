import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import * as api from '../../../src/features/documents/indexApi';
import { IndexRecords } from '../../../src/features/documents/components/IndexRecords';
import type { IndexRecord, IndexVersion } from '../../../src/features/documents/model';

vi.mock('../../../src/features/documents/indexApi');

const record = (overrides: Partial<IndexRecord>): IndexRecord => ({
  run_id: 'run-1',
  ordinal: 0,
  document_id: 'doc-1',
  filename: 'census.pdf',
  processing_version: 1,
  page_number: 30,
  start_char: 0,
  end_char: 10,
  text: '| Year | Median |\n| --- | --- |\n| 2015 | 68,410 |',
  source_url: null,
  section_path: ['APPENDIX A'],
  dimensions: 1536,
  embedded: true,
  embedding_norm: 1,
  embedding_preview: [],
  ...overrides,
});

test('the index inspector shows what a table row is searched as', async () => {
  vi.mocked(api.listIndexRecords).mockResolvedValue({
    items: [
      record({
        embedding_prefix: 'Section: APPENDIX A\n\n',
        embedding_text: 'Section: APPENDIX A\n\nYear: 2015; Median: 68,410',
      }),
      record({
        ordinal: 1,
        text: 'Plain passage.',
        embedding_prefix: '',
        embedding_text: 'Plain passage.',
      }),
    ],
    total: 2,
    limit: 20,
    offset: 0,
  });
  render(<IndexRecords projectId="p" index={{ id: 'i' } as IndexVersion} />);
  const row = await screen.findByRole('region', { name: 'Chunk 1 searched as' });
  expect(row.querySelector('pre')?.textContent).toBe(
    'Section: APPENDIX A\n\nYear: 2015; Median: 68,410',
  );
  expect(screen.queryByRole('region', { name: 'Chunk 2 searched as' })).not.toBeInTheDocument();
});
