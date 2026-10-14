import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

import * as api from '../../../src/features/ingestion-pipelines/api';
import {
  createIngestionPipeline,
  createIngestionPipelineVersion,
} from '../../../src/features/ingestion-pipelines/api';
import {
  WebsiteSettings,
  type WebsiteRecommendationContext,
} from '../../../src/features/ingestion-pipelines/components/SourceSettings';
import { defaultWebsite } from '../../../src/features/ingestion-pipelines/editorModel';
import {
  canonicalIngestion,
  type IngestionPipelineDraft,
  type SettingRecommendation,
  type WebsiteConfig,
} from '../../../src/features/ingestion-pipelines/model';
import {
  applyRecommendation,
  recommendationDifferences,
} from '../../../src/features/ingestion-pipelines/recommendationsModel';

vi.mock('../../../src/features/ingestion-pipelines/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../src/features/ingestion-pipelines/api')>()),
  startSettingRecommendation: vi.fn(),
  getSettingRecommendation: vi.fn(),
}));

const URL_ENTERED = 'https://docs.example/docs';

function recommendation(overrides: Partial<SettingRecommendation> = {}): SettingRecommendation {
  return {
    id: 'rec-1',
    source_node_id: 'source',
    target: 'website',
    status: 'succeeded',
    progress: 100,
    progress_step: 'validating',
    error: null,
    inputs: {
      selection: { mode: 'crawl', start_url: URL_ENTERED },
      entered_url: URL_ENTERED,
      other_sources_max_pages: 0,
      page_ceiling: 200,
    },
    probe_version: 'website-probe-v1',
    rules_version: 'website-rules-v1',
    recommended: {
      kind: 'website',
      selection: { mode: 'crawl', start_url: URL_ENTERED },
      allowed_origins: ['https://docs.example/'],
      include_path_prefixes: ['/docs/'],
      exclude_path_prefixes: [],
      max_pages: 50,
      max_depth: 3,
      requests_per_second: 0.5,
    },
    fields: [
      {
        path: 'allowed_origins',
        label: 'Allowed sites',
        value: ['https://docs.example'],
        basis: 'computed',
        risk: 'high',
        rationale_code: 'origins_start',
        rationale: 'Pages are fetched only from https://docs.example, the address you entered.',
        check: false,
      },
      {
        path: 'include_path_prefixes',
        label: 'Pages under',
        value: ['/docs/'],
        basis: 'computed',
        risk: 'high',
        rationale_code: 'include_redirect_folder',
        rationale: '/docs redirects to the folder /docs/, so only pages under /docs/ are crawled.',
        check: false,
      },
      {
        path: 'requests_per_second',
        label: 'Crawl speed',
        value: 0.5,
        basis: 'computed',
        risk: 'high',
        rationale_code: 'rps_crawl_delay',
        rationale: 'robots.txt asks for 2 seconds between requests, so the speed is 0.5.',
        check: false,
      },
    ],
    warnings: [],
    evidence: {
      requests: [
        {
          purpose: 'robots',
          url: 'https://docs.example/robots.txt',
          status: 200,
          outcome: 'response',
          elapsed_ms: 10,
        },
        {
          purpose: 'start_page',
          url: URL_ENTERED,
          status: 301,
          outcome: 'response',
          elapsed_ms: 10,
        },
      ],
    },
    created_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86_400_000).toISOString(),
    ...overrides,
  };
}

const initialConfig = (overrides: Partial<WebsiteConfig> = {}): WebsiteConfig => ({
  ...defaultWebsite(),
  selection: { mode: 'crawl', start_url: URL_ENTERED },
  allowed_origins: ['https://docs.example'],
  ...overrides,
});

let latest: WebsiteConfig;
let applied: SettingRecommendation | undefined;

function Harness({ initial, enabled = true }: { initial: WebsiteConfig; enabled?: boolean }) {
  const [config, setConfig] = useState(initial);
  const [appliedRecommendation, setApplied] = useState<SettingRecommendation>();
  latest = config;
  const context: WebsiteRecommendationContext = {
    projectId: 'project',
    nodeId: 'source',
    otherSourcesMaxPages: 30,
    applied: appliedRecommendation,
    onApplied: (value) => {
      applied = value;
      setApplied(value);
    },
  };
  const dirty = canonicalIngestion(config) !== canonicalIngestion(initial);
  return (
    <>
      <p>{dirty ? 'Unsaved changes' : 'Saved'}</p>
      <WebsiteSettings
        config={config}
        update={setConfig}
        recommendations={enabled ? context : undefined}
      />
    </>
  );
}

const startUrlInput = () => screen.getByLabelText('Start URL');

beforeEach(() => {
  applied = undefined;
  vi.mocked(api.startSettingRecommendation).mockReset();
  vi.mocked(api.getSettingRecommendation).mockReset();
});

afterEach(() => vi.useRealTimers());

test('a committed address starts one analysis and pre-fills the draft', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(recommendation());
  render(<Harness initial={initialConfig()} />);
  expect(screen.getByText('Saved')).toBeInTheDocument();

  fireEvent.blur(startUrlInput());
  fireEvent.keyDown(startUrlInput(), { key: 'Enter' });

  await screen.findByRole('heading', { name: 'Recommended settings' });
  expect(api.startSettingRecommendation).toHaveBeenCalledTimes(1);
  expect(api.startSettingRecommendation).toHaveBeenCalledWith('project', {
    target: 'website',
    source_node_id: 'source',
    selection: { mode: 'crawl', start_url: URL_ENTERED },
    other_sources_max_pages: 30,
    refresh: false,
  });
  expect(latest.include_path_prefixes).toEqual(['/docs/']);
  expect(latest.allowed_origins).toEqual(['https://docs.example']);
  expect(latest.requests_per_second).toBe(0.5);
  expect(latest.selection).toEqual({ mode: 'crawl', start_url: URL_ENTERED });
  expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  expect(applied?.id).toBe('rec-1');

  // Rows with their values and one Why line each.
  expect(screen.getByText('Pages under')).toBeInTheDocument();
  expect(
    screen.getByText(
      'Why: /docs redirects to the folder /docs/, so only pages under /docs/ are crawled.',
    ),
  ).toBeInTheDocument();
  expect(screen.getByText('0.5 per second')).toBeInTheDocument();
  expect(screen.getByText(/2 requests/)).toBeInTheDocument();
  expect(screen.queryByText(/Changed from recommended/)).not.toBeInTheDocument();
});

test('Edit opens the existing form, which stays mounted while read-only', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(recommendation());
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  const edit = await screen.findByRole('button', { name: 'Edit' });
  const form = document.getElementById(edit.getAttribute('aria-controls') ?? '');
  expect(form).not.toBeNull();
  expect(form).not.toBeVisible();
  expect(edit).toHaveAttribute('aria-expanded', 'false');

  fireEvent.click(edit);
  expect(form).toBeVisible();
  expect(screen.getByRole('button', { name: 'Hide settings' })).toHaveAttribute(
    'aria-expanded',
    'true',
  );
  fireEvent.change(screen.getByLabelText('Crawl speed (requests per second)'), {
    target: { value: '1' },
  });
  expect(latest.requests_per_second).toBe(1);
  expect(screen.getByText('Changed from recommended (was 0.5 per second)')).toBeInTheDocument();
});

test('an edited setting survives a new recommendation', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(recommendation());
  render(
    <Harness
      initial={initialConfig({ max_pages: 120, include_path_prefixes: ['/docs/guide/'] })}
    />,
  );
  fireEvent.blur(startUrlInput());
  await screen.findByRole('heading', { name: 'Recommended settings' });
  expect(latest.max_pages).toBe(120);
  expect(latest.include_path_prefixes).toEqual(['/docs/guide/']);
  expect(latest.requests_per_second).toBe(0.5);
});

test('polls a queued analysis once per second until it ends', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(
    recommendation({
      status: 'running',
      progress: 10,
      progress_step: 'robots',
      recommended: null,
      fields: [],
    }),
  );
  vi.mocked(api.getSettingRecommendation).mockResolvedValue(recommendation());
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  expect(
    await screen.findByText('Checking the site to recommend settings: reading robots.txt.'),
  ).toHaveAttribute('role', 'status');
  expect(api.getSettingRecommendation).not.toHaveBeenCalled();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  await waitFor(() => expect(latest.include_path_prefixes).toEqual(['/docs/']));
  expect(api.getSettingRecommendation).toHaveBeenCalledTimes(1);
  expect(api.getSettingRecommendation).toHaveBeenCalledWith('project', 'rec-1');
});

test('a failed analysis keeps the form open with the safe reason', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(
    recommendation({
      status: 'failed',
      recommended: null,
      fields: [],
      error: 'robots.txt disallows the start URL, so the site was not analysed.',
    }),
  );
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  expect(await screen.findByRole('alert')).toHaveTextContent('robots.txt disallows the start URL');
  expect(screen.getByLabelText('Maximum pages')).toBeVisible();
  expect(latest).toEqual(initialConfig());
});

test('with recommendations off the form is unchanged and nothing is analysed', () => {
  render(<Harness initial={initialConfig()} enabled={false} />);
  fireEvent.blur(startUrlInput());
  fireEvent.keyDown(startUrlInput(), { key: 'Enter' });
  expect(api.startSettingRecommendation).not.toHaveBeenCalled();
  expect(screen.queryByText('Recommended settings')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Maximum pages')).toBeVisible();
  expect(document.querySelector('[aria-controls]')).toBeNull();
});

test('pre-fill replaces only default, derived or previously recommended values', () => {
  const recommended = recommendation();
  const derived = initialConfig({ include_path_prefixes: [] });
  expect(applyRecommendation(derived, recommended).include_path_prefixes).toEqual(['/docs/']);
  const previous = recommendation({
    id: 'rec-0',
    recommended: { ...recommended.recommended!, requests_per_second: 1 },
  });
  const fromPrevious = applyRecommendation(
    initialConfig({ requests_per_second: 1 }),
    recommended,
    previous,
  );
  expect(fromPrevious.requests_per_second).toBe(0.5);
  const edited = applyRecommendation(initialConfig({ requests_per_second: 3 }), recommended);
  expect(edited.requests_per_second).toBe(3);
  expect(recommendationDifferences(edited, recommended)).toEqual(new Set(['requests_per_second']));
});

test('the save payload carries recommendation IDs beside the draft only when present', async () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response('{}'));
  const draft = {
    kind: 'ingestion',
    name: 'Sources',
    execution: { schema_version: 1, nodes: [], edges: [] },
    layout: { positions: {} },
  } satisfies IngestionPipelineDraft;
  await createIngestionPipeline('project', draft, ['rec-1']);
  await createIngestionPipelineVersion('project', 'pipeline', draft, ['rec-1']);
  await createIngestionPipeline('project', draft);
  expect(fetchSpy).toHaveBeenNthCalledWith(
    1,
    '/api/projects/project/pipelines',
    expect.objectContaining({
      body: JSON.stringify({ ...draft, recommendation_ids: ['rec-1'] }),
    }),
  );
  expect(fetchSpy).toHaveBeenNthCalledWith(
    2,
    '/api/projects/project/pipelines/pipeline/versions',
    expect.objectContaining({
      body: JSON.stringify({ ...draft, recommendation_ids: ['rec-1'] }),
    }),
  );
  expect(fetchSpy).toHaveBeenNthCalledWith(
    3,
    '/api/projects/project/pipelines',
    expect.objectContaining({ body: JSON.stringify(draft) }),
  );
  fetchSpy.mockRestore();
});
