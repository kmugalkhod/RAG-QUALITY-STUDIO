import { devices, expect, test } from '@playwright/test';

const { defaultBrowserType: _browser, ...iPhone13 } = devices['iPhone 13'];
void _browser;

// Spec 0003 shell: grouped sidebar, collapse, active marker, top bar and quick jump.

test('sidebar groups, collapse, active marker and top bar work with the keyboard', async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  const project = (await (
    await request.post('/api/projects', { data: { name: `Shell ${Date.now()}` } })
  ).json()) as { id: string; name: string };
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/projects/${project.id}/pipelines?kind=ingestion`);
  await page.evaluate(() => localStorage.removeItem('rqs.sidebar'));
  await page.reload();

  const sidebar = page.getByRole('complementary', { name: 'Studio navigation' });
  const ingestion = sidebar.getByRole('link', { name: 'Ingestion pipelines' });
  await expect(ingestion).toHaveAttribute('aria-current', 'page');
  await expect(sidebar.getByText('Owner · local')).toBeVisible();

  const top = page.getByRole('banner');
  await expect(top.getByText('API ready')).toBeVisible();
  await expect(top.getByText(/ingestion runs? in progress/)).toBeAttached();
  const crumbs = page.getByRole('navigation', { name: 'Breadcrumb' });
  await expect(crumbs).toContainText(project.name);
  await expect(crumbs.locator('[aria-current="page"]')).toHaveText('Pipelines');

  // Group headers collapse and expand from the keyboard.
  const run = sidebar.getByRole('button', { name: 'Run' });
  await run.focus();
  await page.keyboard.press('Enter');
  await expect(run).toHaveAttribute('aria-expanded', 'false');
  await expect(sidebar.getByRole('link', { name: 'Playground' })).toHaveCount(0);
  await page.keyboard.press('Space');
  await expect(run).toHaveAttribute('aria-expanded', 'true');
  await expect(sidebar.getByRole('link', { name: 'Playground' })).toBeVisible();

  const kinds = sidebar.getByRole('button', { name: 'Pipeline kinds' });
  await kinds.click();
  await expect(kinds).toHaveAttribute('aria-expanded', 'false');
  await expect(sidebar.getByRole('link', { name: 'Pipelines', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await kinds.click();

  // Collapse to icons; the choice survives a reload and links keep their names.
  await sidebar.getByRole('button', { name: 'Collapse sidebar' }).click();
  const width = (await sidebar.boundingBox())?.width ?? 0;
  expect(width).toBeLessThanOrEqual(64);
  await page.reload();
  await expect(sidebar.getByRole('button', { name: 'Expand sidebar' })).toBeVisible();
  await expect(sidebar.getByRole('link', { name: 'Pipelines', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await page.screenshot({ path: 'test-results/shell-collapsed-desktop.png' });
  await sidebar.getByRole('button', { name: 'Expand sidebar' }).click();
  await expect(sidebar.getByText('RAG Quality Studio')).toBeVisible();

  // Quick jump opens with Ctrl+K, filters and navigates with the arrow keys.
  await page.keyboard.press('Control+k');
  const filter = page.getByLabel('Filter pages, projects and pipelines');
  await expect(filter).toBeFocused();
  await filter.fill('experi');
  await page.keyboard.press('ArrowDown');
  const jump = page.locator('[data-slot="popover-content"]');
  await expect(jump.getByRole('link', { name: 'Experiments', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Experiments', exact: true })).toBeVisible();
  await expect(sidebar.getByRole('link', { name: 'Experiments', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );

  // Both themes keep the shell cards without horizontal scroll at tablet width.
  for (const width of [1440, 900]) {
    await page.setViewportSize({ width, height: 900 });
    for (let pass = 0; pass < 2; pass += 1) {
      await top.getByRole('button', { name: /^Switch to (light|dark) theme$/ }).click();
      const theme = await page.evaluate(() => document.documentElement.dataset.theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await page.screenshot({ path: `test-results/shell-${width}-${theme}.png` });
    }
  }
});

test.describe('on a phone', () => {
  test.use(iPhone13);

  test('phones keep the tab bar and hide the sidebar', async ({ page, request }) => {
    const project = (await (
      await request.post('/api/projects', { data: { name: `Shell phone ${Date.now()}` } })
    ).json()) as { id: string };
    await page.goto(`/#/projects/${project.id}/overview`);
    await expect(page.getByRole('navigation', { name: 'Project sections' })).toBeVisible();
    await expect(page.getByRole('complementary', { name: 'Studio navigation' })).toBeHidden();
    const search = page.getByRole('button', { name: 'Jump to a page, project or pipeline' });
    expect((await search.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: 'test-results/shell-phone.png', fullPage: true });
  });
});
