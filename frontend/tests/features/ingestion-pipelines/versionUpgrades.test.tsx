import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import { ChunkSettings } from '../../../src/features/ingestion-pipelines/components/ChunkSettings';
import { CleanSettings } from '../../../src/features/ingestion-pipelines/components/CleanSettings';
import {
  chunkUpgradeAvailable,
  chunkUpgradeChanges,
  chunkVersionChanges,
  cleanUpgradeChanges,
  defaultQualityPolicy,
  versionNumber,
} from '../../../src/features/ingestion-pipelines/editorModel';
import type {
  ChunkNode,
  ExtractionCapabilities,
  IngestionNode,
} from '../../../src/features/ingestion-pipelines/model';

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
  config_version: 'section-token-v1',
};

const steps = [
  { id: 'unicode', type: 'unicode_normalize', enabled: true, form: 'NFC' },
] satisfies NonNullable<Extract<IngestionNode, { type: 'clean' }>['steps']>;

function capabilities(version: 'structure-clean-v1' | 'structure-clean-v2') {
  return {
    schema_version: 1,
    media_types: ['text/plain'],
    profiles: [],
    ocr: {
      available: false,
      languages: [],
      reason: 'Unavailable',
      max_pages: 100,
      max_pixels_per_page: 20_000_000,
    },
    table_modes: ['preserve'],
    quality_policies: [
      {
        id: 'default-v1',
        name: 'Default',
        description: 'Default.',
        settings: defaultQualityPolicy,
      },
    ],
    cleaning_profiles: [
      { id: 'structure-aware-v1', name: 'Structure-aware', config_version: version, steps },
    ],
  } satisfies ExtractionCapabilities;
}

const clean = {
  id: 'clean',
  type: 'clean',
  profile: 'structure-aware-v1',
  config_version: 'structure-clean-v1',
  normalize_whitespace: true,
  repeated_boilerplate: [],
  exact_content_deduplication: true,
  steps,
} satisfies Extract<IngestionNode, { type: 'clean' }>;

test('version numbers read the label suffix, and a missing version is v1', () => {
  expect(versionNumber('section-token-v3')).toBe(3);
  expect(versionNumber('parent-child-v2')).toBe(2);
  expect(versionNumber(undefined)).toBe(1);
});

test('the chunk upgrade notice lists what each newer version changes', () => {
  render(<ChunkSettings node={section} websiteSource={false} serverErrors={{}} update={vi.fn()} />);
  expect(screen.getByText('Saved with section-token-v1')).toBeInTheDocument();
  for (const change of chunkUpgradeChanges(section)) {
    expect(screen.getByText(change)).toBeInTheDocument();
  }
  expect(chunkUpgradeChanges(section)[0]).toBe(chunkVersionChanges[2]);
  expect(chunkVersionChanges[3]).toMatch(/never inside one/);
  expect(chunkVersionChanges[3]).toMatch(/under 40 bytes/);
});

test('a saved v2 chunker is offered only the later changes', () => {
  const v2 = { ...section, config_version: 'section-token-v2' };
  expect(chunkUpgradeChanges(v2)).toEqual([
    chunkVersionChanges[3],
    chunkVersionChanges[4],
    chunkVersionChanges[5],
  ]);
  render(<ChunkSettings node={v2} websiteSource={false} serverErrors={{}} update={vi.fn()} />);
  expect(screen.getByText('Saved with section-token-v2')).toBeInTheDocument();
  expect(screen.getByText(chunkVersionChanges[3])).toBeInTheDocument();
  expect(screen.queryByText(chunkVersionChanges[2])).not.toBeInTheDocument();
});

test('the current chunker is never offered an upgrade or a downgrade', () => {
  const current = { ...section, config_version: 'section-token-v5' };
  expect(chunkUpgradeAvailable(current)).toBe(false);
  expect(chunkUpgradeChanges(current)).toEqual([]);
  // New drafts moved from v3 to v5 in the spec 0015 proof round.
  expect(chunkUpgradeChanges({ ...section, config_version: 'section-token-v3' })).toEqual([
    chunkVersionChanges[4],
    chunkVersionChanges[5],
  ]);
  render(<ChunkSettings node={current} websiteSource={false} serverErrors={{}} update={vi.fn()} />);
  expect(screen.queryByRole('button', { name: 'Upgrade chunking' })).not.toBeInTheDocument();
});

test('structure-aware cleaning shows no notice while the server recommends its version', () => {
  expect(cleanUpgradeChanges(clean, capabilities('structure-clean-v1'))).toEqual([]);
  render(
    <CleanSettings
      node={clean}
      capabilities={capabilities('structure-clean-v1')}
      errors={{}}
      update={vi.fn()}
    />,
  );
  expect(screen.queryByRole('button', { name: 'Upgrade cleaning' })).not.toBeInTheDocument();
});

test('structure-clean-v1 is offered the v2 changes once the server recommends v2', () => {
  const update = vi.fn();
  render(
    <CleanSettings
      node={clean}
      capabilities={capabilities('structure-clean-v2')}
      errors={{}}
      update={update}
    />,
  );
  expect(screen.getByText('Saved with structure-clean-v1')).toBeInTheDocument();
  expect(screen.getByText(/keeps tables, lists, code, quotes and footnotes/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Upgrade cleaning' }));
  // Only the engine version changes; the saved steps stay as they are.
  expect(update).toHaveBeenCalledWith({ ...clean, config_version: 'structure-clean-v2' });
});

test('a v2 cleaner is not offered a downgrade', () => {
  expect(
    cleanUpgradeChanges(
      { ...clean, config_version: 'structure-clean-v2' },
      capabilities('structure-clean-v1'),
    ),
  ).toEqual([]);
});
