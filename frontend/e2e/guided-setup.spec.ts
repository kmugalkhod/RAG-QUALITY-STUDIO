import { devices, expect, test, type Page } from '@playwright/test';

const { defaultBrowserType: _browser, ...iPhone13 } = devices['iPhone 13'];
void _browser;

// Spec 0003: the guided setup creates the same Website pipeline versions as the editor.

async function noHorizontalScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test('guided setup saves a two-site pipeline that the editor opens unchanged', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires isolated deterministic providers.',
  );
  test.setTimeout(240000);
  const project = (await (
    await request.post('/api/projects', { data: { name: `Two-site wizard ${Date.now()}` } })
  ).json()) as { id: string };

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/#/projects/${project.id}/pipelines?kind=ingestion`);
  await page.getByRole('link', { name: 'Guided setup', exact: true }).click();
  await expect(page).toHaveURL(/pipelines\/setup\?kind=ingestion/);
  await expect(
    page.getByRole('heading', { name: 'Which websites should this pipeline read?' }),
  ).toBeVisible({ timeout: 15000 });
  const next = page.getByRole('button', { name: 'Next: Output' });
  await expect(next).toHaveAttribute('aria-disabled', 'true');

  const address = page.getByLabel('Add a website');
  await address.fill('not a url at all');
  await page.getByRole('button', { name: 'Add website' }).click();
  await expect(page.getByRole('alert')).toContainText('Enter a website address');
  await address.fill('https://controlled.example/');
  await address.press('Enter');
  await address.fill('second.example');
  await page.getByRole('button', { name: 'Add website' }).click();
  await expect(page.getByRole('list', { name: 'Websites' }).getByRole('listitem')).toHaveCount(2);
  await expect(page.getByText(/You have added 2 of 5 websites, up to 100 pages/)).toBeVisible();

  await page.getByRole('button', { name: 'Preview controlled.example' }).click();
  await expect(page.getByText(/Preview OK · 2 pages/)).toBeVisible({ timeout: 30000 });

  // Keyboard on the page-limit slider: one step is 10 pages.
  const slider = page.getByRole('slider', { name: 'Maximum pages for second.example' });
  await slider.focus();
  await slider.press('ArrowRight');
  await expect(page.getByText('60 pages', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/guided-sources-desktop.png', fullPage: true });

  await next.click();
  await expect(
    page.getByRole('heading', { name: 'How should these sites be indexed?' }),
  ).toBeVisible();
  await page.getByLabel('Name', { exact: true }).fill('Guided docs');
  await page.getByRole('radio', { name: /One index per source/ }).check();
  await expect(page.getByText('Guided docs · controlled.example')).toBeVisible();
  await expect(page.getByText('Guided docs · second.example')).toBeVisible();

  await page.getByRole('button', { name: 'Next: Processing' }).click();
  await expect(page.getByRole('heading', { name: 'How should pages be processed?' })).toBeVisible();
  const chunk = page.getByRole('slider', { name: 'Chunk size in tokens', exact: true });
  await chunk.focus();
  await chunk.press('ArrowRight');
  await page.getByRole('button', { name: 'Add override for second.example' }).click();
  const own = page.getByRole('slider', { name: 'Chunk size in tokens for second.example' });
  await own.focus();
  await own.press('ArrowLeft');
  await own.press('ArrowLeft');
  await expect(page.getByText('Custom', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/guided-processing-desktop.png', fullPage: true });

  await page.getByRole('button', { name: 'Next: Review' }).click();
  await expect(page.getByRole('heading', { name: 'Review and publish.' })).toBeVisible();
  // The draft survives a reload.
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Review and publish.' })).toBeVisible();
  await expect(page.getByText('Draft saved')).toBeVisible();
  await expect(page.getByText('controlled.example, second.example')).toBeVisible();

  await page.getByRole('button', { name: 'Save and publish 2 indexes' }).click();
  await expect(page.getByRole('heading', { name: 'Collecting your sources.' })).toBeVisible();
  const runs = page.getByRole('list', { name: 'Run progress' });
  await expect(runs.getByText('Published')).toHaveCount(2, { timeout: 90000 });
  await page.screenshot({ path: 'test-results/guided-run-desktop.png', fullPage: true });

  const pipelines = await (
    await request.get(`/api/projects/${project.id}/pipelines?kind=ingestion`)
  ).json();
  expect(pipelines.items).toHaveLength(1);
  const versions = await (
    await request.get(`/api/projects/${project.id}/pipelines/${pipelines.items[0].id}/versions`)
  ).json();
  expect(versions.items).toHaveLength(1);
  const saved = versions.items[0];
  expect(saved.name).toBe('Guided docs');
  expect(saved.execution.index_layout).toBe('per_source');
  const chunks = saved.execution.nodes.filter((node: { type: string }) => node.type === 'chunk');
  expect(chunks.map((node: { target_tokens: number }) => node.target_tokens).sort()).toEqual([
    500, 700,
  ]);
  const sources = saved.execution.nodes.filter((node: { type: string }) => node.type === 'source');
  expect(sources.map((node: { config: { max_pages: number } }) => node.config.max_pages)).toEqual([
    50, 60,
  ]);

  await page.getByRole('link', { name: 'Open in editor' }).click();
  await expect(page.getByText('Unsaved changes', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save version' })).toHaveAttribute(
    'aria-disabled',
    'true',
  );
  await expect(page.getByRole('button', { name: 'Website 1 settings' })).toContainText(
    'Shared settings',
  );
  await expect(page.getByRole('button', { name: 'Website 2 settings' })).toContainText(
    'Custom chunking',
  );
});

test.describe('on a phone', () => {
  test.use(iPhone13);

  test('guided setup works at 390px in both themes and discards its draft', async ({
    context,
    request,
  }) => {
    const project = (await (
      await request.post('/api/projects', { data: { name: `Guided phone ${Date.now()}` } })
    ).json()) as { id: string };
    let page: Page | undefined;
    for (const theme of ['dark', 'light']) {
      // A fresh tab per theme: Chromium drops touch emulation after an in-page hash change.
      await page?.close();
      page = await context.newPage();
      await page.addInitScript((value) => localStorage.setItem('rqs.theme', value), theme);
      await page.goto(`/#/projects/${project.id}/pipelines/setup?kind=ingestion`);
      await expect(
        page.getByRole('heading', { name: 'Which websites should this pipeline read?' }),
      ).toBeVisible();
      await page.getByLabel('Add a website').fill('https://controlled.example/');
      await page.getByRole('button', { name: 'Add website' }).click();
      await expect(page.getByRole('list', { name: 'Websites' }).getByRole('listitem')).toHaveCount(
        1,
      );
      await noHorizontalScroll(page);
      const footer = page.getByRole('button', { name: 'Next: Output' });
      const box = await footer.boundingBox();
      expect(box?.height).toBeGreaterThanOrEqual(44);
      await page.screenshot({
        path: `test-results/guided-sources-phone-${theme}.png`,
        fullPage: true,
      });
      await footer.click();
      await page.getByRole('button', { name: 'Next: Processing' }).click();
      await noHorizontalScroll(page);
      await page.screenshot({
        path: `test-results/guided-processing-phone-${theme}.png`,
        fullPage: true,
      });
      page.once('dialog', (dialog) => dialog.accept());
      await page.getByRole('button', { name: 'Discard draft' }).click();
      await expect(
        page.getByRole('heading', { name: 'Which websites should this pipeline read?' }),
      ).toBeVisible();
      await expect(page.getByRole('list', { name: 'Websites' }).getByRole('listitem')).toHaveCount(
        0,
      );
    }
    await page!.getByRole('link', { name: 'Close' }).click();
    await expect(page!.getByRole('tab', { name: 'Ingestion pipelines' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });
});
