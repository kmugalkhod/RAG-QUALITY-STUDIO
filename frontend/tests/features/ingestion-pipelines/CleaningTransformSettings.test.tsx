import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import { CleanSettings } from '../../../src/features/ingestion-pipelines/components/CleanSettings';
import { CleaningTransformSettings } from '../../../src/features/ingestion-pipelines/components/CleaningTransformSettings';
import { defaultQualityPolicy } from '../../../src/features/ingestion-pipelines/editorModel';
import type {
  ExtractionCapabilities,
  IngestionNode,
} from '../../../src/features/ingestion-pipelines/model';

const steps = [
  { id: 'unicode', type: 'unicode_normalize', enabled: true, form: 'NFC' },
  {
    id: 'validate',
    type: 'validate_useful_content',
    enabled: true,
    minimum_characters: 1,
    maximum_characters: 2_000_000,
  },
] satisfies NonNullable<Extract<IngestionNode, { type: 'clean' }>['steps']>;

const capabilities = {
  schema_version: 1,
  media_types: ['application/pdf', 'text/plain'],
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
      description: 'Balanced extraction-quality thresholds.',
      settings: defaultQualityPolicy,
    },
  ],
  cleaning_profiles: [
    {
      id: 'structure-aware-v1',
      name: 'Structure-aware standard',
      config_version: 'structure-clean-v1',
      steps,
    },
  ],
} satisfies ExtractionCapabilities;

const structure = {
  id: 'clean',
  type: 'clean',
  profile: 'structure-aware-v1',
  config_version: 'structure-clean-v1',
  normalize_whitespace: true,
  repeated_boilerplate: [],
  exact_content_deduplication: true,
  steps,
} satisfies Extract<IngestionNode, { type: 'clean' }>;

test('upgrades a compatibility draft from the named server profile without saving it', () => {
  const update = vi.fn();
  const node = {
    id: 'clean',
    type: 'clean',
    profile: 'standard-v1',
    config_version: 'deterministic-clean-v1',
    normalize_whitespace: true,
    repeated_boilerplate: [],
    exact_content_deduplication: true,
  } satisfies Extract<IngestionNode, { type: 'clean' }>;
  render(<CleanSettings node={node} capabilities={capabilities} errors={{}} update={update} />);

  expect(screen.getByText('Saved with the compatibility cleaner')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Upgrade cleaning' }));
  expect(update).toHaveBeenCalledWith(
    expect.objectContaining({
      profile: 'structure-aware-v1',
      config_version: 'structure-clean-v1',
      steps,
    }),
  );
});

test('switches a step off with a labelled control, and offers no reorder or delete', () => {
  const update = vi.fn();
  render(<CleaningTransformSettings node={structure} update={update} />);

  expect(screen.queryByRole('button', { name: /Move|Remove/ })).toBeNull();
  fireEvent.click(screen.getByRole('checkbox', { name: /1. Normalize Unicode/ }));
  expect(update.mock.calls.at(-1)?.[0].steps[0].enabled).toBe(false);
});

test('adds a missing step at its place in the server order', () => {
  const update = vi.fn();
  render(<CleaningTransformSettings node={structure} update={update} />);

  fireEvent.change(screen.getByRole('combobox', { name: 'Transform to add' }), {
    target: { value: 'website_selectors' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add' }));

  expect(update.mock.calls.at(-1)?.[0].steps.map((step: { type: string }) => step.type)).toEqual([
    'unicode_normalize',
    'website_selectors',
    'validate_useful_content',
  ]);
  expect(
    screen.queryByRole('option', { name: 'Remove literal boilerplate' }),
  ).not.toBeInTheDocument();
});
