import { expect, test, type Page } from '@playwright/test';

async function settledViewport(page: Page) {
  let previous: string | null = null;
  let stableSamples = 0;
  await expect
    .poll(
      async () => {
        const current = await page.locator('.react-flow__viewport').getAttribute('style');
        stableSamples = current === previous ? stableSamples + 1 : 0;
        previous = current;
        return stableSamples;
      },
      { intervals: [100], timeout: 5000 },
    )
    .toBeGreaterThanOrEqual(2);
  return previous!;
}

// UI-only fixtures: no requests reach a developer database or a paid provider.
test.beforeEach(async ({ page }) => {
  const project = {
    id: '11111111-1111-4111-8111-111111111111',
    name: 'Pipeline layout verification',
    description: '',
    created_at: '2026-09-21T00:00:00Z',
  };
  const empty = { items: [], total: 0, limit: 20, offset: 0 };
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = empty;
    if (path === '/api/projects') body = { ...empty, items: [project], total: 1 };
    else if (path === `/api/projects/${project.id}`) body = project;
    else if (path.endsWith('/embedding-settings'))
      body = {
        configured: true,
        config: { provider: 'test', model: 'fixture-embedding', dimensions: 3, revision: '1' },
      };
    else if (path.endsWith('/source-connections/settings')) body = { enabled: false };
    else if (route.request().method() !== 'GET') {
      await route.abort();
      return;
    }
    await route.fulfill({ json: body });
  });
  await page.goto(`/#/projects/${project.id}/pipelines/new?kind=ingestion`);
  await page.getByLabel('Source type').selectOption('website');
});

test('credentialed source types stay discoverable while vault setup is required', async ({
  page,
}) => {
  const sourceType = page.getByLabel('Source type');
  await expect(sourceType.locator('option')).toHaveText([
    'Existing files',
    'Website',
    'Amazon S3 · setup required',
    'Notion · setup required',
    'Confluence · setup required',
  ]);
  await expect(page.getByRole('link', { name: 'Review setup in project settings' })).toBeVisible();

  await sourceType.selectOption('s3');
  await expect(page.getByRole('heading', { name: 'Amazon S3 settings' })).toBeVisible();
  await expect(
    page.getByText('Enable the local encrypted connection vault before using S3.'),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save version', exact: true })).toBeDisabled();
});

test('all desktop stages preserve canvas position and zoom while the inspector scrolls', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const canvas = page.locator('.pipeline-canvas');
  const settings = page.locator('#node-settings');
  const originalBox = await canvas.boundingBox();
  await page.getByText(/Scope & fetch limits/).click();
  await settings.hover({ position: { x: 30, y: 120 } });
  await page.mouse.wheel(0, 650);
  await expect.poll(() => settings.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  expect(await canvas.boundingBox()).toEqual(originalBox);
  expect(await page.evaluate(() => scrollY)).toBe(0);
  await page.getByLabel('User agent').scrollIntoViewIfNeeded();
  await expect(page.getByLabel('User agent')).toBeInViewport();
  await page.getByRole('button', { name: 'Fit View', exact: true }).click();
  await page.getByRole('button', { name: 'Zoom In', exact: true }).click();
  await expect
    .poll(() => page.locator('.react-flow__viewport').getAttribute('style'))
    .toContain('scale');
  // Wait for the explicit zoom animation to finish, then preserve that user's view.
  await page.waitForFunction(() =>
    document.getAnimations().every((animation) => animation.playState !== 'running'),
  );
  await settledViewport(page);
  const size = await canvas.evaluate((element) => ({
    width: element.clientWidth,
    height: element.clientHeight,
  }));
  for (const stage of [
    '2 Extract',
    '3 Clean',
    '4 Chunk',
    '5 Embed',
    '6 Publish index',
    '1 Source',
  ]) {
    const transform = await page.locator('.react-flow__viewport').getAttribute('style');
    await page
      .getByRole('navigation', { name: 'Ingestion stages' })
      .getByRole('button', { name: stage, exact: true })
      .click();
    await expect(page.getByRole('button', { name: stage, exact: true })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(
      await canvas.evaluate((element) => ({
        width: element.clientWidth,
        height: element.clientHeight,
      })),
    ).toEqual(size);
    expect(await canvas.boundingBox()).toEqual(originalBox);
    expect(
      await page.evaluate(() => ({ y: scrollY, height: document.documentElement.scrollHeight })),
    ).toEqual({ y: 0, height: 900 });
    await expect(page.locator('.react-flow__viewport')).toHaveAttribute('style', transform!);
    expect(await settings.evaluate((element) => element.scrollTop)).toBe(0);
    await expect(page.locator('#ingestion-settings-heading')).toBeInViewport();
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + 30, box.y + 100);
  const transform = await page.locator('.react-flow__viewport').getAttribute('style');
  await page.mouse.wheel(0, 500);
  expect(await page.evaluate(() => scrollY)).toBe(0);
  await expect(page.locator('.react-flow__viewport')).toHaveAttribute('style', transform!);
});

test('tablet stacks the inspector and preserves editable state across every stage', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.getByLabel('Starting URL').fill('https://example.org/guide');
  for (const stage of [
    '2 Extract',
    '3 Clean',
    '4 Chunk',
    '5 Embed',
    '6 Publish index',
    '1 Source',
  ]) {
    await page.getByRole('button', { name: stage, exact: true }).click();
    await expect(page.locator('#ingestion-settings-heading')).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    const canvas = (await page.locator('.pipeline-canvas').boundingBox())!;
    const settings = (await page.locator('#node-settings').boundingBox())!;
    expect(settings.y).toBeGreaterThanOrEqual(canvas.y + canvas.height);
    expect(canvas.width).toBeGreaterThan(700);
  }
  await expect(page.getByLabel('Starting URL')).toHaveValue('https://example.org/guide');
});

test('mobile stages and long source settings remain reachable without horizontal overflow', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const chunk = page.getByRole('button', { name: '4 Chunk', exact: true });
  await chunk.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Chunk settings' })).toBeVisible();
  await page.getByLabel('Chunk size (characters)').fill('1200');
  await page.getByRole('button', { name: '1 Source', exact: true }).click();
  await page.getByLabel('Starting URL').fill('https://example.org/');
  await page.getByText(/Scope & fetch limits/).click();
  await page.getByLabel('User agent').scrollIntoViewIfNeeded();
  await expect(page.getByLabel('User agent')).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.getByRole('button', { name: '4 Chunk', exact: true }).click();
  await expect(page.getByLabel('Chunk size (characters)')).toHaveValue('1200');
  expect(await page.locator('.pipeline-canvas').evaluate((element) => element.clientHeight)).toBe(
    440,
  );
  const canvas = (await page.locator('.pipeline-canvas').boundingBox())!;
  const settings = (await page.locator('#node-settings').boundingBox())!;
  expect(canvas.y + canvas.height).toBeLessThanOrEqual(settings.y);
});

test('saving records the draft and discard restores the saved stage settings', async ({ page }) => {
  await page.route('**/api/projects/*/pipelines', async (route) => {
    const draft = route.request().postDataJSON();
    expect(draft.execution.nodes[0].config.selection.start_url).toBe('https://example.org/');
    await route.fulfill({
      json: {
        ...draft,
        id: 'version-1',
        pipeline_id: 'pipeline-1',
        version: 1,
        created_at: '2026-09-21T00:00:00Z',
      },
    });
  });
  await page.getByLabel('Starting URL').fill('https://example.org/');
  await page.getByRole('button', { name: 'Save version', exact: true }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Collect source & build index' })).toBeEnabled();
  await page.getByRole('button', { name: '4 Chunk', exact: true }).click();
  await page.getByLabel('Chunk size (characters)').fill('1500');
  await expect(page.getByRole('button', { name: 'Collect source & build index' })).toBeDisabled();
  await page.getByRole('button', { name: 'Discard changes' }).click();
  await expect(page.getByLabel('Chunk size (characters)')).toHaveValue('1000');
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Automatic sync' })).not.toBeVisible();
  await page.getByRole('button', { name: 'Automatic sync' }).click();
  await expect(page.getByRole('heading', { name: 'Automatic sync' })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 900 });
  const canvas = (await page.locator('.pipeline-canvas').boundingBox())!;
  const syncPanel = (await page.locator('#automatic-sync-panel').boundingBox())!;
  const inspector = (await page.locator('#node-settings').boundingBox())!;
  expect(Math.abs(syncPanel.x - canvas.x)).toBeLessThanOrEqual(1);
  expect(syncPanel.width).toBeGreaterThanOrEqual(canvas.width + inspector.width - 1);
  await page.getByRole('button', { name: '5 Embed', exact: true }).click();
  await expect(page.locator('#automatic-sync-panel')).toHaveCount(1);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('heading', { name: 'Automatic sync' }).scrollIntoViewIfNeeded();
  await expect(page.getByRole('button', { name: 'Start automatic sync' })).toBeVisible();
  const heading = (await page.locator('#automatic-sync-heading').boundingBox())!;
  const name = (await page.getByLabel('Schedule name', { exact: true }).boundingBox())!;
  expect(heading.x).toBe(name.x);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);

  await page.route('**/api/projects/*/ingestion-schedules', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    const request = route.request().postDataJSON();
    expect(request.enabled).toBe(true);
    expect(request.cadence).toEqual({ kind: 'interval', minutes: 1440 });
    await route.fulfill({
      json: {
        id: 'schedule-1',
        project_id: '11111111-1111-4111-8111-111111111111',
        pipeline_id: 'pipeline-1',
        pipeline_version_id: 'version-1',
        pipeline_version: 1,
        name: request.name,
        status: 'enabled',
        cadence: request.cadence,
        next_run_at: '2026-09-22T00:00:00Z',
        last_run_id: null,
        last_triggered_at: null,
        last_outcome: null,
        last_error: null,
        created_at: '2026-09-21T00:00:00Z',
        updated_at: '2026-09-21T00:00:00Z',
      },
    });
  });
  await page.getByRole('button', { name: 'Start automatic sync' }).click();
  await expect(page.getByText('Active', { exact: true })).toBeVisible();
});

test('unavailable embedding configuration shows an actionable error instead of endless loading', async ({
  page,
}) => {
  await page.route('**/api/projects/*/embedding-settings', (route) =>
    route.fulfill({
      json: { configured: false, config: null, error: 'Configure an embedding provider.' },
    }),
  );
  page.on('dialog', (dialog) => dialog.accept());
  await page.reload();
  await expect(page.getByRole('alert')).toHaveText('Configure an embedding provider.');
  await expect(page.getByRole('button', { name: 'Retry loading pipeline' })).toBeVisible();
});

test('preview feedback is brought into view, cancellation works, and failures stay actionable', async ({
  page,
}) => {
  const preview = {
    id: 'preview-1',
    status: 'running',
    progress: 20,
    discovered_count: 0,
    included_count: 0,
    excluded_count: 0,
    duplicate_count: 0,
    failed_count: 0,
    error: null,
  };
  await page.route('**/api/projects/*/ingestion-previews', (route) =>
    route.fulfill({ json: preview }),
  );
  await page.route('**/api/projects/*/source-previews/preview-1', (route) =>
    route.fulfill({ json: preview }),
  );
  await page.route('**/api/projects/*/source-previews/preview-1/cancel', (route) =>
    route.fulfill({ json: { ...preview, status: 'cancelled' } }),
  );
  await page.getByLabel('Starting URL').fill('https://example.org/');
  await page.getByRole('button', { name: 'Preview source', exact: true }).click();
  await expect(page.locator('#ingestion-preview')).toBeInViewport();
  await page.getByRole('button', { name: 'Cancel preview' }).click();
  await expect(page.locator('#ingestion-preview')).toContainText('cancelled');
  await expect(page.locator('#ingestion-preview')).toContainText(
    'No preview items were discovered.',
  );
  await page.route('**/api/projects/*/ingestion-previews', (route) =>
    route.fulfill({ status: 503, json: { detail: 'Source service unavailable. Retry preview.' } }),
  );
  await page.getByRole('button', { name: 'Preview source', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('Source service unavailable. Retry preview.');
  await expect(page.getByRole('alert')).toBeFocused();
  await expect(page.getByRole('button', { name: 'Preview source', exact: true })).toBeEnabled();
});

test('invalid chunk settings expose field errors and block saving and preview', async ({
  page,
}) => {
  await page.getByLabel('Starting URL').fill('https://example.org/');
  await page.getByRole('button', { name: '4 Chunk', exact: true }).click();
  await page.getByLabel('Chunk size (characters)').fill('50');
  await expect(page.getByLabel('Chunk size (characters)')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByLabel('Overlap (characters)')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByRole('button', { name: 'Save version', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Preview source', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Balanced', exact: true }).click();
  await expect(page.getByLabel('Chunk size (characters)')).toHaveValue('1000');
  await expect(page.getByLabel('Overlap (characters)')).toHaveValue('120');
  await expect(page.getByRole('button', { name: 'Save version', exact: true })).toBeEnabled();
});

test('canvas node clicks and source form variants never resize or refit the graph', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.getByRole('button', { name: 'Fit View', exact: true }).click();
  const canvas = page.locator('.pipeline-canvas');
  const height = await canvas.evaluate((element) => element.clientHeight);
  const transform = await settledViewport(page);
  for (const id of ['extract', 'clean', 'chunk', 'embed', 'publish', 'source']) {
    await page.locator(`.react-flow__node[data-id="${id}"]`).click();
    expect(await canvas.evaluate((element) => element.clientHeight)).toBe(height);
    await expect(page.locator('.react-flow__viewport')).toHaveAttribute('style', transform!);
  }
  for (const mode of ['single_url', 'url_list', 'sitemap', 'crawl']) {
    await page.getByLabel('Discovery mode').selectOption(mode);
    await expect(
      page.getByLabel(mode === 'url_list' ? 'URLs (one per line)' : 'Starting URL'),
    ).toBeVisible();
    expect(await canvas.evaluate((element) => element.clientHeight)).toBe(height);
    await expect(page.locator('.react-flow__viewport')).toHaveAttribute('style', transform!);
  }
  await page.getByLabel('Source type').selectOption('existing_files');
  await expect(
    page.getByText('No uploaded documents. Add and process files in Knowledge Base first.'),
  ).toBeVisible();
  expect(await canvas.evaluate((element) => element.clientHeight)).toBe(height);
});
