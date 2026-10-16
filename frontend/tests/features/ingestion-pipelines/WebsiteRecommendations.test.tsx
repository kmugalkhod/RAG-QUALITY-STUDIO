import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
  PREFILLED_PATHS,
  addressSelection,
  applyRecommendation,
  isStale,
  recommendationDifferences,
  resetToRecommended,
  wideningEdits,
} from '../../../src/features/ingestion-pipelines/recommendationsModel';

vi.mock('../../../src/features/ingestion-pipelines/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../src/features/ingestion-pipelines/api')>()),
  startSettingRecommendation: vi.fn(),
  getSettingRecommendation: vi.fn(),
  cancelSettingRecommendation: vi.fn(),
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
      other_sources_max_pages: 30,
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

function Harness({
  initial,
  enabled = true,
  otherSourcesMaxPages = 30,
  extra = {},
  fieldErrors,
}: {
  initial: WebsiteConfig;
  enabled?: boolean;
  otherSourcesMaxPages?: number;
  extra?: Partial<WebsiteRecommendationContext>;
  fieldErrors?: Record<string, string>;
}) {
  const [config, setConfig] = useState(initial);
  const [appliedRecommendation, setApplied] = useState<SettingRecommendation>();
  latest = config;
  const context: WebsiteRecommendationContext = {
    projectId: 'project',
    nodeId: 'source',
    otherSourcesMaxPages,
    ...extra,
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
        fieldErrors={fieldErrors}
        recommendations={enabled ? context : undefined}
      />
    </>
  );
}

const startUrlInput = () => screen.getByLabelText('Website address');

beforeEach(() => {
  applied = undefined;
  vi.mocked(api.startSettingRecommendation).mockReset();
  vi.mocked(api.getSettingRecommendation).mockReset();
  vi.mocked(api.cancelSettingRecommendation).mockReset();
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
  expect(screen.queryByLabelText('Website address')).not.toBeInTheDocument();
  const startUrl = screen.getByLabelText('Start URL');
  fireEvent.blur(startUrl);
  fireEvent.keyDown(startUrl, { key: 'Enter' });
  // Today's form: discovery first, then the mode's URL field and the slash advisory.
  expect(screen.getByLabelText('Discovery mode')).toBeVisible();
  expect(screen.getByText(/This URL has no trailing slash/)).toBeInTheDocument();
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

const SITEMAP_URL = 'https://docs.example/sitemap.xml';

function fullRecommendation(): SettingRecommendation {
  const base = recommendation();
  const field = (
    path: SettingRecommendation['fields'][number]['path'],
    label: string,
    value: unknown,
    rationale_code: string,
    rationale: string,
  ) => ({
    path,
    label,
    value,
    basis: 'computed' as const,
    risk: 'medium' as const,
    rationale_code,
    rationale,
    check: false,
  });
  return {
    ...base,
    recommended: {
      ...base.recommended!,
      selection: { mode: 'sitemap', sitemap_url: SITEMAP_URL },
      exclude_path_prefixes: ['/docs/search/'],
      max_pages: 60,
      requests_per_second: 0.5,
    },
    fields: [
      field(
        'selection',
        'Discovery',
        { mode: 'sitemap', sitemap_url: SITEMAP_URL },
        'mode_sitemap',
        "The site's sitemap lists 51 pages in scope, and the sample found 51 of the 51 linked pages in it, so the sitemap is read.",
      ),
      ...base.fields,
      field(
        'exclude_path_prefixes',
        'Excluded',
        ['/docs/search/'],
        'exclude_utility_pattern',
        '/docs/search/ hold search, feed or other utility pages, so they are skipped.',
      ),
      field(
        'max_pages',
        'Maximum pages',
        60,
        'pages_sitemap',
        'The sitemap lists 51 pages in scope, so up to 60 are fetched.',
      ),
      field(
        'max_depth',
        'Crawl depth',
        3,
        'depth_not_used',
        'Crawl depth applies only when links are followed.',
      ),
    ],
    warnings: [
      {
        code: 'all_links_off_origin',
        message: 'Every link on the start page leads to another site.',
      },
    ],
    evidence: {
      ...base.evidence,
      robots: { found: true, crawl_delay: 2, start_allowed: true },
    },
  };
}

test('Slice 2 rows: discovery, exclusions, page time, an unused depth and warnings', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(fullRecommendation());
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  await screen.findByRole('heading', { name: 'Recommended settings' });

  // The crawl input becomes the recommended sitemap, and the card stays for it.
  expect(latest.selection).toEqual({ mode: 'sitemap', sitemap_url: SITEMAP_URL });
  expect(latest.exclude_path_prefixes).toEqual(['/docs/search/']);
  expect(latest.max_pages).toBe(60);
  const card = within(screen.getByRole('region', { name: 'Recommended settings' }));
  expect(card.getByText('Discovery')).toBeInTheDocument();
  expect(card.getByText('Sitemap')).toBeInTheDocument();
  expect(card.getByText('/docs/search/')).toBeInTheDocument();
  // 60 pages, one every 2 seconds.
  expect(card.getByText('60 · about 2 min at 0.5/s')).toBeInTheDocument();
  expect(card.getByText('Not used')).toBeInTheDocument();
  expect(screen.getByRole('note')).toHaveTextContent(
    'Every link on the start page leads to another site.',
  );
  expect(screen.queryByText(/Changed from recommended/)).not.toBeInTheDocument();
});

test('the page time follows a crawl delay longer than the speed allows', async () => {
  const value = fullRecommendation();
  vi.mocked(api.startSettingRecommendation).mockResolvedValue({
    ...value,
    recommended: { ...value.recommended!, requests_per_second: 0.1 },
    evidence: { ...value.evidence, robots: { found: true, crawl_delay: 11, start_allowed: true } },
  });
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  // 60 pages at one per 11 seconds is 11 minutes, not the 10 that 0.1/s suggests.
  expect(await screen.findByText('60 · about 11 min at 0.1/s')).toBeInTheDocument();
});

test('a discovery the user changed is kept and reported', () => {
  const value = fullRecommendation();
  const listed = initialConfig({
    selection: { mode: 'url_list', urls: ['https://docs.example/a'] },
  });
  expect(applyRecommendation(listed, value).selection).toEqual(listed.selection);
  const crawl = initialConfig();
  expect(recommendationDifferences(crawl, value).has('selection')).toBe(true);
  expect(recommendationDifferences(applyRecommendation(crawl, value), value).has('selection')).toBe(
    false,
  );
});

// Slice 3: every card state, Reset, Re-analyze, Cancel, stale, widening, saved versions.

const running = (overrides: Partial<SettingRecommendation> = {}) =>
  recommendation({
    status: 'running',
    progress: 30,
    progress_step: 'start_page',
    recommended: null,
    fields: [],
    finished_at: null,
    ...overrides,
  });

const card = () => within(screen.getByRole('region', { name: 'Recommended settings' }));

test('no address shows only the hint, and the field is labelled Website address', () => {
  render(<Harness initial={initialConfig({ selection: { mode: 'crawl', start_url: '' } })} />);
  const field = screen.getByLabelText('Website address');
  expect(field).toHaveAccessibleDescription(
    'Enter a page, a section or a sitemap. Settings are recommended from the site.',
  );
  fireEvent.blur(field);
  expect(api.startSettingRecommendation).not.toHaveBeenCalled();
  expect(screen.queryByRole('region', { name: 'Recommended settings' })).not.toBeInTheDocument();
  expect(screen.getByLabelText('Maximum pages')).toBeVisible();
});

test('analysing names the step, and Cancel calls the cancel endpoint', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(running());
  vi.mocked(api.cancelSettingRecommendation).mockResolvedValue(
    recommendation({ status: 'cancelled', recommended: null, fields: [] }),
  );
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  expect(
    await screen.findByText('Checking the site to recommend settings: reading the start page.'),
  ).toHaveAttribute('aria-live', 'polite');
  fireEvent.click(card().getByRole('button', { name: 'Cancel' }));
  await screen.findByText('The analysis was cancelled. The settings below are unchanged.');
  expect(api.cancelSettingRecommendation).toHaveBeenCalledWith('project', 'rec-1');
  expect(latest).toEqual(initialConfig());
  expect(card().getByRole('button', { name: 'Re-analyze' })).toBeInTheDocument();
});

test('a failed analysis offers Retry, which analyses the address again', async () => {
  vi.mocked(api.startSettingRecommendation)
    .mockResolvedValueOnce(
      recommendation({
        status: 'failed',
        recommended: null,
        fields: [],
        error: 'The start page returned HTTP 503.',
      }),
    )
    .mockResolvedValueOnce(recommendation({ id: 'rec-2' }));
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  expect(await screen.findByRole('alert')).toHaveTextContent('The start page returned HTTP 503.');
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  await waitFor(() => expect(latest.include_path_prefixes).toEqual(['/docs/']));
  expect(api.startSettingRecommendation).toHaveBeenCalledTimes(2);
  expect(vi.mocked(api.startSettingRecommendation).mock.calls[1][1].refresh).toBe(false);
});

test('a request error (rate limit) shows as a failure with Retry', async () => {
  vi.mocked(api.startSettingRecommendation).mockRejectedValue(
    new Error('Analysis limit reached for this project. Try again later.'),
  );
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  expect(await screen.findByRole('alert')).toHaveTextContent('Analysis limit reached');
  expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  expect(screen.getByLabelText('Maximum pages')).toBeVisible();
});

test('a changed address makes the card stale, keeps the values and hides Edit', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(recommendation());
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  await screen.findByRole('button', { name: 'Edit' });
  fireEvent.change(startUrlInput(), { target: { value: 'https://docs.example/other/' } });
  expect(card().getByText(/These recommendations are for/)).toHaveTextContent(URL_ENTERED);
  expect(latest.requests_per_second).toBe(0.5);
  expect(latest.include_path_prefixes).toEqual(['/docs/']);
  expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
  expect(screen.getByLabelText('Maximum pages')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Reset to recommended' })).not.toBeInTheDocument();
});

test("other sources' page total changing makes the card stale; Re-analyze refreshes", async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(recommendation());
  const { rerender } = render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  await screen.findByRole('button', { name: 'Edit' });
  expect(screen.queryByText(/These recommendations are for/)).not.toBeInTheDocument();
  rerender(<Harness initial={initialConfig()} otherSourcesMaxPages={80} />);
  expect(card().getByText(/These recommendations are for/)).toBeInTheDocument();
  // A blur of the same address does not re-analyse on its own; Re-analyze does.
  expect(isStale(latest, recommendation(), 80)).toBe(true);
  expect(isStale(latest, recommendation(), 30)).toBe(false);
  fireEvent.click(card().getByRole('button', { name: 'Re-analyze' }));
  await waitFor(() => expect(api.startSettingRecommendation).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.startSettingRecommendation).mock.calls[1][1]).toMatchObject({
    other_sources_max_pages: 80,
    refresh: true,
  });
});

test('an expired recommendation keeps its values and says when it was analysed', async () => {
  const dayAgo = new Date(Date.now() - 25 * 3_600_000).toISOString();
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(
    recommendation({ status: 'expired', finished_at: dayAgo, expires_at: dayAgo }),
  );
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  expect(await screen.findByText(/Analysed yesterday/)).toBeInTheDocument();
  expect(card().getByText(/more than a day old/)).toBeInTheDocument();
  expect(card().getByRole('button', { name: 'Re-analyze' })).toBeInTheDocument();
});

test('a viewer sees the saved card without actions and starts nothing', () => {
  render(
    <Harness
      initial={initialConfig({ include_path_prefixes: ['/docs/'], requests_per_second: 1 })}
      extra={{
        readOnly: true,
        savedVersion: 2,
        provenance: {
          status: 'applied',
          target: 'website',
          recommendation_id: 'rec-1',
          entered_url: URL_ENTERED,
          analysed_at: '2026-10-20T10:00:00Z',
          probe_version: 'website-probe-v1',
          rules_version: 'website-rules-v1',
          fields: {
            include_path_prefixes: {
              basis: 'computed',
              recommended: ['/docs/'],
              saved: null,
              rationale_code: 'include_redirect_folder',
              rationale: '/docs redirects to the folder /docs/.',
            },
            requests_per_second: {
              basis: 'user',
              recommended: 0.5,
              saved: 1,
              rationale_code: 'rps_crawl_delay',
              rationale: 'robots.txt asks for 2 seconds between requests.',
            },
          },
        },
      }}
    />,
  );
  fireEvent.blur(startUrlInput());
  fireEvent.change(startUrlInput(), { target: { value: 'https://docs.example/new/' } });
  fireEvent.blur(startUrlInput());
  expect(api.startSettingRecommendation).not.toHaveBeenCalled();
  expect(card().getByText('Version 2 · Recommended on 20 Oct · 1 changed by you')).toBeVisible();
  expect(card().getByText('Changed by you (recommended 0.5 per second)')).toBeInTheDocument();
  expect(card().queryByRole('button')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Maximum pages')).toBeVisible();
});

test('a saved version shows the recorded settings, and Re-analyze is offered', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(recommendation({ id: 'rec-9' }));
  render(
    <Harness
      initial={initialConfig({ include_path_prefixes: ['/docs/'] })}
      extra={{
        savedVersion: 1,
        provenance: {
          status: 'applied',
          target: 'website',
          recommendation_id: 'rec-1',
          entered_url: URL_ENTERED,
          analysed_at: '2026-10-20T10:00:00Z',
          probe_version: 'website-probe-v1',
          rules_version: 'website-rules-v1',
          fields: {
            include_path_prefixes: {
              basis: 'computed',
              recommended: ['/docs/'],
              saved: null,
              rationale_code: 'include_redirect_folder',
              rationale: '/docs redirects to the folder /docs/.',
            },
          },
        },
      }}
    />,
  );
  expect(card().getByText('Version 1 · Recommended on 20 Oct · 0 changed by you')).toBeVisible();
  // The recorded address is not analysed again on blur (D6).
  fireEvent.blur(startUrlInput());
  expect(api.startSettingRecommendation).not.toHaveBeenCalled();
  fireEvent.click(card().getByRole('button', { name: 'Re-analyze' }));
  await waitFor(() => expect(api.startSettingRecommendation).toHaveBeenCalledTimes(1));
  expect(vi.mocked(api.startSettingRecommendation).mock.calls[0][1].refresh).toBe(true);
});

test('Reset restores every managed setting and lists what changed first', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(fullRecommendation());
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
  fireEvent.change(screen.getByLabelText('Maximum pages'), { target: { value: '400' } });
  fireEvent.change(screen.getByLabelText('Crawl speed (requests per second)'), {
    target: { value: '3' },
  });
  fireEvent.change(screen.getByLabelText('Include path prefixes (one per line)'), {
    target: { value: '/' },
  });
  fireEvent.change(screen.getByLabelText('Exclude path prefixes (one per line)'), {
    target: { value: '' },
  });
  fireEvent.change(screen.getByLabelText('Allowed origins (one per line)'), {
    target: { value: 'https://docs.example\nhttps://cdn.example' },
  });
  expect(
    card().getByText(
      '5 settings changed from recommended: Allowed sites, Pages under, Excluded, Maximum pages, Crawl speed.',
    ),
  ).toBeInTheDocument();
  fireEvent.click(card().getByRole('button', { name: 'Reset to recommended' }));
  const recommended = fullRecommendation().recommended!;
  expect(latest.selection).toEqual(recommended.selection);
  expect(latest.allowed_origins).toEqual(['https://docs.example']);
  expect(latest.include_path_prefixes).toEqual(recommended.include_path_prefixes);
  expect(latest.exclude_path_prefixes).toEqual(recommended.exclude_path_prefixes);
  expect(latest.max_pages).toBe(recommended.max_pages);
  expect(latest.max_depth).toBe(recommended.max_depth);
  expect(latest.requests_per_second).toBe(recommended.requests_per_second);
  expect(screen.queryByText(/changed from recommended:/)).not.toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByRole('heading', { name: 'Recommended settings' })).toHaveFocus(),
  );
});

test('resetToRecommended sets all seven managed paths', () => {
  const value = fullRecommendation();
  const edited = initialConfig({
    selection: { mode: 'single_url', url: 'https://docs.example/x' },
    allowed_origins: ['https://other.example'],
    include_path_prefixes: [],
    exclude_path_prefixes: ['/a/'],
    max_pages: 999,
    max_depth: 9,
    requests_per_second: 5,
  });
  const reset = resetToRecommended(edited, value);
  expect(PREFILLED_PATHS).toHaveLength(7);
  expect(recommendationDifferences(reset, value).size).toBe(0);
});

test('the widening list names origins, include, pages and speed with consequences', async () => {
  const value = fullRecommendation();
  const wider = {
    ...applyRecommendation(initialConfig(), value),
    allowed_origins: ['https://docs.example', 'https://cdn.example'],
    include_path_prefixes: ['/'],
    max_pages: 500,
    requests_per_second: 2,
  };
  const edits = wideningEdits(wider, value);
  expect(edits.map((edit) => edit.path)).toEqual([
    'allowed_origins',
    'include_path_prefixes',
    'max_pages',
    'requests_per_second',
  ]);
  expect(edits[0].consequence).toContain('https://cdn.example');
  expect(edits[1].consequence).toContain('Pages under /');
  expect(edits[2].consequence).toContain('Up to 500 pages instead of 60');
  expect(edits[3].consequence).toContain('faster than the 0.5 recommended');
  // Narrower edits are not widening.
  const narrower = {
    ...applyRecommendation(initialConfig(), value),
    include_path_prefixes: ['/docs/guide/'],
    max_pages: 10,
    requests_per_second: 0.2,
  };
  expect(wideningEdits(narrower, value)).toEqual([]);
  expect(
    wideningEdits({ ...narrower, include_path_prefixes: [] }, value).map((edit) => edit.path),
  ).toEqual(['include_path_prefixes']);

  vi.mocked(api.startSettingRecommendation).mockResolvedValue(value);
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
  fireEvent.change(screen.getByLabelText('Maximum pages'), { target: { value: '500' } });
  const note = within(card().getByText('Wider than recommended').closest('[role="note"]')!);
  expect(note.getByText(/Up to 500 pages instead of 60/)).toBeInTheDocument();
});

test('the trailing-slash advisory is hidden while a current recommendation is applied', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(recommendation());
  render(<Harness initial={initialConfig()} />);
  expect(screen.getByText(/This URL has no trailing slash/)).toBeInTheDocument();
  fireEvent.blur(startUrlInput());
  await screen.findByRole('button', { name: 'Edit' });
  expect(screen.queryByText(/This URL has no trailing slash/)).not.toBeInTheDocument();
});

test('a multi-line paste is analysed as a URL list, and a .xml address as a sitemap', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(running());
  render(<Harness initial={initialConfig({ selection: { mode: 'crawl', start_url: '' } })} />);
  fireEvent.paste(startUrlInput(), {
    clipboardData: { getData: () => 'https://docs.example/a\nhttps://docs.example/b' },
  });
  await waitFor(() => expect(api.startSettingRecommendation).toHaveBeenCalledTimes(1));
  expect(vi.mocked(api.startSettingRecommendation).mock.calls[0][1].selection).toEqual({
    mode: 'url_list',
    urls: ['https://docs.example/a', 'https://docs.example/b'],
  });
  expect(latest.selection).toEqual({
    mode: 'url_list',
    urls: ['https://docs.example/a', 'https://docs.example/b'],
  });
  expect(addressSelection('https://docs.example/sitemap.xml.gz')).toEqual({
    mode: 'sitemap',
    sitemap_url: 'https://docs.example/sitemap.xml.gz',
  });
  expect(addressSelection('https://docs.example/page', 'single_url')).toEqual({
    mode: 'single_url',
    url: 'https://docs.example/page',
  });
});

test('a sitemap address starts a sitemap analysis', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(running());
  render(<Harness initial={initialConfig({ selection: { mode: 'crawl', start_url: '' } })} />);
  fireEvent.change(startUrlInput(), { target: { value: SITEMAP_URL } });
  fireEvent.keyDown(startUrlInput(), { key: 'Enter' });
  await waitFor(() => expect(api.startSettingRecommendation).toHaveBeenCalledTimes(1));
  expect(vi.mocked(api.startSettingRecommendation).mock.calls[0][1].selection).toEqual({
    mode: 'sitemap',
    sitemap_url: SITEMAP_URL,
  });
});

test('a URL list recommendation pre-fills the list draft', () => {
  const urls = ['https://docs.example/a', 'https://docs.example/b'];
  const listed = initialConfig({ selection: { mode: 'url_list', urls } });
  const value = recommendation({
    inputs: { ...recommendation().inputs, selection: { mode: 'url_list', urls } },
    recommended: {
      ...recommendation().recommended!,
      selection: { mode: 'url_list', urls },
      include_path_prefixes: [],
      max_pages: 2,
    },
  });
  const next = applyRecommendation(listed, value);
  expect(next.max_pages).toBe(2);
  expect(next.requests_per_second).toBe(0.5);
  expect(next.selection).toEqual({ mode: 'url_list', urls });
});

test('Edit moves focus to the first field of the form', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(recommendation());
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
  await waitFor(() => expect(screen.getByLabelText('Discovery mode')).toHaveFocus());
});

test('a server error on a Website field keeps the form open', async () => {
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(recommendation());
  render(
    <Harness
      initial={initialConfig()}
      fieldErrors={{ 'website.max_pages': 'Input should be less than or equal to 1000' }}
    />,
  );
  fireEvent.blur(startUrlInput());
  await screen.findByRole('heading', { name: 'Recommended settings' });
  expect(screen.getByLabelText('Maximum pages')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
});

test('polling stops on unmount', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.startSettingRecommendation).mockResolvedValue(running());
  vi.mocked(api.getSettingRecommendation).mockResolvedValue(running());
  const { unmount } = render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  await screen.findByText(/Checking the site/);
  unmount();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  expect(api.getSettingRecommendation).not.toHaveBeenCalled();
});

test('a response for a replaced analysis is ignored', async () => {
  let resolveFirst: (value: SettingRecommendation) => void = () => undefined;
  vi.mocked(api.startSettingRecommendation)
    .mockImplementationOnce(
      () => new Promise<SettingRecommendation>((resolve) => (resolveFirst = resolve)),
    )
    .mockResolvedValueOnce(
      recommendation({
        id: 'rec-2',
        inputs: {
          ...recommendation().inputs,
          selection: { mode: 'crawl', start_url: 'https://docs.example/second/' },
          entered_url: 'https://docs.example/second/',
        },
        recommended: {
          ...recommendation().recommended!,
          selection: { mode: 'crawl', start_url: 'https://docs.example/second/' },
          include_path_prefixes: ['/second/'],
        },
      }),
    );
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  fireEvent.change(startUrlInput(), { target: { value: 'https://docs.example/second/' } });
  fireEvent.blur(startUrlInput());
  await waitFor(() => expect(latest.include_path_prefixes).toEqual(['/second/']));
  await act(async () => {
    resolveFirst(recommendation());
  });
  expect(latest.include_path_prefixes).toEqual(['/second/']);
  expect(applied?.id).toBe('rec-2');
});

test('What was checked lists the requests, the sitemap and the sample pages', async () => {
  const value = fullRecommendation();
  vi.mocked(api.startSettingRecommendation).mockResolvedValue({
    ...value,
    evidence: {
      ...value.evidence,
      sitemap: { found: true, url: SITEMAP_URL, in_scope: 51, lower_bound: false },
      sample_pages: [{ url: 'https://docs.example/docs/a', status: 200, text_length: 1200 }],
    },
  });
  render(<Harness initial={initialConfig()} />);
  fireEvent.blur(startUrlInput());
  await screen.findByRole('heading', { name: 'Recommended settings' });
  const details = card().getByText('What was checked').closest('details')!;
  expect(within(details).getByText('robots.txt · HTTP 200')).toBeInTheDocument();
  expect(within(details).getByText(/listing\s+51 pages in scope/)).toBeInTheDocument();
  expect(within(details).getByText('1,200 characters of text')).toBeInTheDocument();
});
