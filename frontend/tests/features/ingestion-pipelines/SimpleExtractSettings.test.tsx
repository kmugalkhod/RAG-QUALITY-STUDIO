import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, test } from 'vitest';

import { IngestionNodeSettings } from '../../../src/features/ingestion-pipelines/components/IngestionNodeSettings';
import {
  defaultQualityPolicy,
  extractDifferences,
  extractLegacySettings,
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
    config_version: 'layout-ocr-v5',
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
  expect(screen.queryByRole('checkbox', { name: /Read scanned pages/ })).not.toBeInTheDocument();
  expect(screen.getByText('Languages in scanned pages')).toBeInTheDocument();
  expect(screen.getByText('English (eng)')).toBeInTheDocument();
  expect(screen.getByText('Hindi (hin)')).toBeInTheDocument();
  expect(screen.getByLabelText("If a file can't be read well")).toHaveValue('stop');
  expect(screen.getByText(/stops the run, so nothing new is published/)).toBeInTheDocument();
  expect(screen.queryByText(/older custom setting/)).not.toBeInTheDocument();
  expect(advanced().open).toBe(false);
  expect(screen.getByText('Using recommended settings.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Reset/ })).not.toBeInTheDocument();
});

test('settings that never changed a result are not in the panel', () => {
  render(<Harness />);
  for (const label of [
    'Extraction strategy',
    'OCR policy',
    'OCR resolution (DPI)',
    'Per-page timeout (seconds)',
    'Table evidence',
  ]) {
    expect(screen.queryByLabelText(label)).not.toBeInTheDocument();
  }
  expect(screen.queryByText('Detect page rotation')).not.toBeInTheDocument();
  expect(screen.queryByText('Deskew scans')).not.toBeInTheDocument();
  expect(screen.getByLabelText(/Maximum OCR pages/)).toHaveValue(recommendedNode().ocr!.max_pages);
  expect(screen.getByLabelText('Quality policy')).toBeInTheDocument();
});

test('a saved older setting is named, kept on edit and counted once', () => {
  const initial = recommendedNode();
  initial.ocr = { ...initial.ocr!, mode: 'always', dpi: 300 };
  initial.tables = 'plain_text';
  render(<Harness initial={initial} />);
  expect(
    screen.getByText(
      /Uses older custom settings: OCR on every page, OCR resolution 300 DPI, table format Plain text\./,
    ),
  ).toBeInTheDocument();
  expect(screen.getByText('· 1 changed')).toBeInTheDocument();
  fireEvent.click(screen.getByText('English (eng)'));
  fireEvent.change(screen.getByLabelText("If a file can't be read well"), {
    target: { value: 'publish' },
  });
  expect(latest.ocr).toMatchObject({ mode: 'always', dpi: 300 });
  expect(latest.tables).toBe('plain_text');
});

test('one older setting reads in the singular', () => {
  const initial = recommendedNode();
  initial.ocr = { ...initial.ocr!, dpi: 300 };
  render(<Harness initial={initial} />);
  expect(
    screen.getByText(/^Uses an older custom setting: OCR resolution 300 DPI\. The panel/),
  ).toBeInTheDocument();
});

test('the quality choice writes the preset policies', () => {
  render(<Harness />);
  const select = screen.getByLabelText("If a file can't be read well");
  fireEvent.change(select, { target: { value: 'publish' } });
  expect(latest.quality_policy).toEqual(fallbackQualityPolicy('warn-v1'));
  expect(screen.getByLabelText('Quality policy')).toHaveValue('warn-v1');
  expect(screen.getByText(/cannot be read at all is left out with its reason/)).toBeInTheDocument();
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

test('the older-settings reset restores hidden values and keeps the visible choices', () => {
  const initial = recommendedNode();
  initial.strategy = 'layout_aware';
  initial.tables = 'plain_text';
  initial.ocr = { ...initial.ocr!, mode: 'off', languages: ['hin'], dpi: 300, max_pages: 20 };
  initial.quality_policy = fallbackQualityPolicy('warn-v1');
  render(<Harness initial={initial} />);
  expect(
    screen.getByText(
      /Uses older custom settings: extraction strategy Layout-aware, OCR off, OCR resolution 300 DPI, table format Plain text\./,
    ),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Reset older settings to recommended' }));
  expect(latest.strategy).toBe('auto');
  expect(latest.tables).toBe('preserve');
  expect(latest.ocr).toMatchObject({ mode: 'auto', languages: ['hin'], dpi: 200, max_pages: 20 });
  expect(latest.quality_policy).toEqual(fallbackQualityPolicy('warn-v1'));
  expect(screen.queryByText(/older custom setting/)).not.toBeInTheDocument();
  expect(screen.getByText(/differs from recommended: Maximum OCR pages\./)).toBeInTheDocument();
});

test('the advanced reset restores the visible advanced settings only', () => {
  const initial = recommendedNode();
  initial.ocr = { ...initial.ocr!, dpi: 300, max_pages: 20 };
  initial.quality_policy = {
    ...defaultQualityPolicy,
    thresholds: { ...defaultQualityPolicy.thresholds, minimum_ocr_confidence: 80 },
  };
  render(<Harness initial={initial} />);
  expect(screen.getByText('· 3 changed')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Reset to recommended' }));
  expect(latest.ocr).toMatchObject({ dpi: 300, max_pages: recommendedNode().ocr!.max_pages });
  expect(latest.quality_policy).toEqual(fallbackQualityPolicy('default-v1'));
  expect(screen.getByText('· 1 changed')).toBeInTheDocument();
  expect(
    screen.getByText(
      'These settings use the recommended values. The older setting is listed above.',
    ),
  ).toBeInTheDocument();
});

test('a server error on a visible advanced field opens the section', () => {
  render(<Harness serverFieldErrors={{ 'extract:ocr.max_pages': 'At most 100 pages.' }} />);
  expect(advanced().open).toBe(true);
});

test('a server error on a hidden setting shows on the older-settings line', () => {
  render(<Harness serverFieldErrors={{ 'extract:ocr.dpi': 'DPI must be 150–300.' }} />);
  expect(screen.getByRole('alert')).toHaveTextContent('DPI must be 150–300.');
  expect(advanced().open).toBe(false);
});

test('page-based sources keep only the quality choice outside Advanced', () => {
  const initial = recommendedNode();
  initial.ocr = { ...initial.ocr!, dpi: 300 };
  render(<Harness kinds={['website']} initial={initial} />);
  expect(screen.getByText('Quality and language only')).toBeInTheDocument();
  expect(screen.queryByText('Languages in scanned pages')).not.toBeInTheDocument();
  expect(screen.queryByText(/older custom setting/)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/Maximum OCR pages/)).not.toBeInTheDocument();
  expect(screen.getByLabelText("If a file can't be read well")).toHaveValue('stop');
});

test('without OCR the panel explains why and OCR off is not an older setting', () => {
  const initial: ExtractNode = {
    id: 'extract',
    type: 'extract',
    ...recommendedExtractSettings({
      ...capabilities,
      ocr: { ...capabilities.ocr, available: false },
    }),
    config_version: 'layout-ocr-v5',
  };
  expect(initial.ocr?.mode).toBe('off');
  render(<Harness initial={initial} available={false} />);
  expect(screen.getByText('No OCR.')).toBeInTheDocument();
  expect(screen.queryByText(/older custom setting/)).not.toBeInTheDocument();
});

test('the model helpers agree with each other', () => {
  const node = recommendedNode();
  expect(extractDifferences(node, capabilities, true)).toEqual([]);
  expect(extractLegacySettings(node, capabilities, true)).toEqual([]);
  expect(extractLegacySettings({ ...node, strategy: 'native' }, capabilities, false)).toEqual([]);
  // Spec 0008 D2: 100 scanned pages unless the server allows fewer.
  expect(recommendedExtractSettings(capabilities).ocr.max_pages).toBe(100);
  expect(
    recommendedExtractSettings({ ...capabilities, ocr: { ...capabilities.ocr, max_pages: 40 } }).ocr
      .max_pages,
  ).toBe(40);
  expect(recommendedExtractSettings().ocr.max_pages).toBe(100);
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
