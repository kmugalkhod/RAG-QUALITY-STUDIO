import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, test } from 'vitest';

import { IngestionNodeSettings } from '../../../src/features/ingestion-pipelines/components/IngestionNodeSettings';
import {
  defaultQualityPolicy,
  extractDifferences,
  fallbackQualityPolicy,
  qualityChoice,
  recommendedExtractSettings,
} from '../../../src/features/ingestion-pipelines/editorModel';
import type {
  ExtractionCapabilities,
  IngestionNode,
  QualityPolicy,
} from '../../../src/features/ingestion-pipelines/model';

type ExtractNode = Extract<IngestionNode, { type: 'extract' }>;

const capabilities: ExtractionCapabilities = {
  schema_version: 1,
  media_types: ['application/pdf'],
  profiles: [],
  ocr: {
    available: true,
    languages: ['eng', 'hin'],
    reason: null,
    max_pages: 100,
    max_pixels_per_page: 20_000_000,
  },
  table_modes: ['preserve', 'markdown', 'plain_text'],
  quality_policies: (['default-v1', 'strict-v1', 'warn-v1'] as const).map((id) => ({
    id,
    name: id,
    description: `${id} description`,
    settings: fallbackQualityPolicy(id),
  })),
  cleaning_profiles: [],
};

function recommendedNode(): ExtractNode {
  return {
    id: 'extract',
    type: 'extract',
    ...recommendedExtractSettings(capabilities),
    config_version: 'layout-ocr-v3',
  };
}

let latest: ExtractNode;

function Harness({
  initial = recommendedNode(),
  kinds = ['existing_files'],
  serverFieldErrors = {},
  available = true,
}: {
  initial?: ExtractNode;
  kinds?: string[];
  serverFieldErrors?: Record<string, string>;
  available?: boolean;
}) {
  const [node, setNode] = useState<IngestionNode>(initial);
  latest = node as ExtractNode;
  const sources = kinds.map(
    (kind, index) => ({ id: `source-${index}`, type: 'source', config: { kind } }) as IngestionNode,
  );
  return (
    <IngestionNodeSettings
      projectId="project"
      selected={node}
      selectedNode="extract"
      nodes={[...sources, node]}
      dirty
      validation={[]}
      serverFieldErrors={serverFieldErrors}
      connections={[]}
      documents={[]}
      knowledgeSets={[]}
      websiteSource={kinds.includes('website')}
      extractionCapabilities={
        available
          ? capabilities
          : { ...capabilities, ocr: { ...capabilities.ocr, available: false, reason: 'No OCR.' } }
      }
      schemaVersion={2}
      updateNode={(_, update) => setNode((current) => update(current))}
      changeSourceKind={() => undefined}
      onSelectNode={() => undefined}
    />
  );
}

const advanced = () =>
  screen.getByText('Advanced extraction settings').closest('details') as HTMLDetailsElement;

test('a new pipeline shows the simple choices and collapsed recommended settings', () => {
  render(<Harness />);
  expect(screen.getByRole('checkbox', { name: /Read scanned pages \(OCR\)/ })).toBeChecked();
  expect(screen.getByText('Languages in scanned pages')).toBeInTheDocument();
  expect(screen.getByText('English (eng)')).toBeInTheDocument();
  expect(screen.getByText('Hindi (hin)')).toBeInTheDocument();
  expect(screen.getByLabelText("If a file can't be read well")).toHaveValue('stop');
  expect(screen.getByText(/stops the run, so nothing new is published/)).toBeInTheDocument();
  expect(advanced().open).toBe(false);
  expect(screen.getByText('Using recommended settings.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Reset to recommended' })).not.toBeInTheDocument();
});

test('the OCR checkbox writes the same mode as the advanced OCR policy', () => {
  render(<Harness />);
  const ocr = screen.getByRole('checkbox', { name: /Read scanned pages \(OCR\)/ });
  fireEvent.click(ocr);
  expect(latest.ocr?.mode).toBe('off');
  expect(screen.getByLabelText('OCR policy')).toHaveValue('off');
  expect(screen.queryByText('Languages in scanned pages')).not.toBeInTheDocument();
  fireEvent.click(ocr);
  expect(latest.ocr?.mode).toBe('auto');
  expect(screen.getByText('Using recommended settings.')).toBeInTheDocument();
});

test('a saved always OCR mode survives and counts as an advanced difference', () => {
  const initial = recommendedNode();
  initial.ocr = { ...initial.ocr!, mode: 'always' };
  render(<Harness initial={initial} />);
  expect(screen.getByRole('checkbox', { name: /Read scanned pages \(OCR\)/ })).toBeChecked();
  expect(screen.getByText(/1 setting differs from recommended: OCR policy\./)).toBeInTheDocument();
  fireEvent.click(screen.getByText('English (eng)'));
  expect(latest.ocr?.mode).toBe('always');
});

test('the quality choice writes the preset policies', () => {
  render(<Harness />);
  const select = screen.getByLabelText("If a file can't be read well");
  fireEvent.change(select, { target: { value: 'publish' } });
  expect(latest.quality_policy).toEqual(fallbackQualityPolicy('warn-v1'));
  expect(screen.getByLabelText('Quality policy')).toHaveValue('warn-v1');
  expect(screen.getByText(/Files that cannot be read at all are left out/)).toBeInTheDocument();
  expect(screen.queryByRole('option', { name: 'Custom (see Advanced)' })).not.toBeInTheDocument();
  fireEvent.change(select, { target: { value: 'stop' } });
  expect(latest.quality_policy).toEqual(fallbackQualityPolicy('default-v1'));
});

test('custom quality rules show as Custom and as an advanced difference', () => {
  const initial = recommendedNode();
  initial.quality_policy = {
    ...defaultQualityPolicy,
    thresholds: { ...defaultQualityPolicy.thresholds, minimum_ocr_confidence: 80 },
  };
  render(<Harness initial={initial} />);
  expect(screen.getByLabelText("If a file can't be read well")).toHaveValue('custom');
  expect(screen.getByRole('option', { name: 'Custom (see Advanced)' })).toBeDisabled();
  expect(screen.getByText(/differs from recommended: Quality policy\./)).toBeInTheDocument();
});

test('reset restores advanced settings but keeps the simple choices', () => {
  const initial = recommendedNode();
  initial.strategy = 'layout_aware';
  initial.tables = 'plain_text';
  initial.ocr = { ...initial.ocr!, mode: 'off', languages: ['hin'], dpi: 300 };
  initial.quality_policy = fallbackQualityPolicy('warn-v1');
  render(<Harness initial={initial} />);
  expect(
    screen.getByText(
      '3 settings differ from recommended: Extraction strategy, OCR resolution (DPI), Table evidence.',
    ),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Reset to recommended' }));
  expect(latest.strategy).toBe('auto');
  expect(latest.tables).toBe('preserve');
  expect(latest.ocr).toMatchObject({ mode: 'off', languages: ['hin'], dpi: 200 });
  expect(latest.quality_policy).toEqual(fallbackQualityPolicy('warn-v1'));
  expect(screen.getByText('Using recommended settings.')).toBeInTheDocument();
});

test('a server error on an advanced field opens the section', () => {
  render(<Harness serverFieldErrors={{ 'extract:ocr.dpi': 'DPI must be 150–300.' }} />);
  expect(advanced().open).toBe(true);
});

test('page-based sources keep only the quality choice outside Advanced', () => {
  render(<Harness kinds={['website']} />);
  expect(screen.getByText('Quality and language only')).toBeInTheDocument();
  expect(screen.queryByRole('checkbox', { name: /Read scanned pages/ })).not.toBeInTheDocument();
  expect(screen.getByLabelText("If a file can't be read well")).toHaveValue('stop');
});

test('without OCR the checkbox is disabled and explains why', () => {
  const initial = recommendedNode();
  initial.ocr = { ...initial.ocr!, mode: 'off' };
  render(<Harness initial={initial} available={false} />);
  expect(screen.getByRole('checkbox', { name: /Read scanned pages \(OCR\)/ })).toBeDisabled();
  expect(screen.getByText('No OCR.')).toBeInTheDocument();
});

test('the model helpers agree with each other', () => {
  const node = recommendedNode();
  expect(extractDifferences(node, capabilities, true)).toEqual([]);
  expect(qualityChoice('warn-v1', capabilities)).toBe('publish');
  expect(qualityChoice('strict-v1', capabilities)).toBe('custom');
  // Saved JSONB may reorder keys; that is not a difference.
  const policy = node.quality_policy as QualityPolicy;
  const reordered = Object.fromEntries(
    Object.entries({
      ...policy,
      thresholds: Object.fromEntries(Object.entries(policy.thresholds).reverse()),
    }).reverse(),
  ) as QualityPolicy;
  expect(Object.keys(reordered)).not.toEqual(Object.keys(policy));
  expect(qualityChoice(reordered, capabilities)).toBe('stop');
});
