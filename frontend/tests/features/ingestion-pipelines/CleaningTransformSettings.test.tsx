import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import { CleaningTransformSettings } from '../../../src/features/ingestion-pipelines/components/CleaningTransformSettings';
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
  quality_policies: ['default-v1'],
  cleaning_profiles: [
    {
      id: 'structure-aware-v1',
      name: 'Structure-aware standard',
      config_version: 'structure-clean-v1',
      steps,
    },
  ],
} satisfies ExtractionCapabilities;

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
  render(<CleaningTransformSettings node={node} capabilities={capabilities} update={update} />);

  fireEvent.click(screen.getByRole('button', { name: 'Use Structure-aware standard' }));
  expect(update).toHaveBeenCalledWith(
    expect.objectContaining({
      profile: 'structure-aware-v1',
      config_version: 'structure-clean-v1',
      steps,
    }),
  );
});

test('reorders and disables transforms with labelled keyboard-safe controls', () => {
  const update = vi.fn();
  const node = {
    id: 'clean',
    type: 'clean',
    profile: 'structure-aware-v1',
    config_version: 'structure-clean-v1',
    normalize_whitespace: true,
    repeated_boilerplate: [],
    exact_content_deduplication: true,
    steps,
  } satisfies Extract<IngestionNode, { type: 'clean' }>;
  const { rerender } = render(
    <CleaningTransformSettings node={node} capabilities={capabilities} update={update} />,
  );

  fireEvent.click(screen.getByRole('button', { name: 'Move Normalize Unicode down' }));
  expect(update.mock.calls.at(-1)?.[0].steps.map((step: { type: string }) => step.type)).toEqual([
    'validate_useful_content',
    'unicode_normalize',
  ]);

  rerender(<CleaningTransformSettings node={node} capabilities={capabilities} update={update} />);
  fireEvent.click(screen.getByRole('checkbox', { name: /1. Normalize Unicode/ }));
  expect(update.mock.calls.at(-1)?.[0].steps[0].enabled).toBe(false);
  expect(screen.getByRole('button', { name: 'Reset profile' })).toBeEnabled();
});

test('inserts a newly added transform before final validation', () => {
  const update = vi.fn();
  const node = {
    id: 'clean',
    type: 'clean',
    profile: 'structure-aware-v1',
    config_version: 'structure-clean-v1',
    steps,
  } satisfies Extract<IngestionNode, { type: 'clean' }>;
  render(<CleaningTransformSettings node={node} capabilities={capabilities} update={update} />);

  fireEvent.change(screen.getByRole('combobox', { name: 'Transform to add' }), {
    target: { value: 'remove_literal_boilerplate' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add' }));

  expect(update.mock.calls.at(-1)?.[0].steps.map((step: { type: string }) => step.type)).toEqual([
    'unicode_normalize',
    'remove_literal_boilerplate',
    'validate_useful_content',
  ]);
});
