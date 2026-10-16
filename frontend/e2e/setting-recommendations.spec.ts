import { expect, test } from '@playwright/test';

// Spec 0011, Slice 3. Needs the isolated stack with deterministic providers and the
// controlled website transport, with recommendations turned on for that stack only:
// compose.e2e.yaml + compose.index-e2e.yaml + compose.recommendations-e2e.yaml.
test('a website address gets recommended settings that survive Edit, Reset and save', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1' || process.env.E2E_RECOMMENDATIONS !== '1',
    'Requires the isolated stack with recommended settings turned on.',
  );
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') {
      errors.push(message.text());
    }
  });
  const project = (await (
    await request.post('/api/projects', { data: { name: `Recommended settings ${Date.now()}` } })
  ).json()) as { id: string };

  await page.goto(`/#/projects/${project.id}/pipelines/new?kind=ingestion`);
  await page.getByLabel('Pipeline name').fill('Recommended website');
  await page.getByLabel('Source type').selectOption('website');
  const address = page.getByLabel('Website address');
  await address.fill('https://controlled.example/docs');
  await address.press('Tab');

  // The probe follows the 301 to /docs/, so only that folder is crawled.
  const card = page.getByRole('region', { name: 'Recommended settings' });
  await expect(card.getByText('Pages under', { exact: true })).toBeVisible({ timeout: 60000 });
  await expect(card.getByText('/docs/', { exact: true })).toBeVisible();
  await expect(card.getByText(/redirects to the folder \/docs\//)).toBeVisible();
  await expect(page.getByText('Unsaved changes')).toBeVisible();
  // The trailing-slash advisory gives way to the recommendation.
  await expect(page.getByText(/This URL has no trailing slash/)).toHaveCount(0);

  await card.getByRole('button', { name: 'Edit' }).click();
  await expect(page.getByLabel('Discovery mode')).toBeFocused();
  const maxPages = page.getByLabel('Maximum pages');
  const recommendedPages = await maxPages.inputValue();
  await maxPages.fill('900');
  await expect(card.getByText(/1 setting changed from recommended: Maximum pages/)).toBeVisible();
  await expect(card.getByText('Wider than recommended')).toBeVisible();
  await card.getByRole('button', { name: 'Reset to recommended' }).click();
  await expect(maxPages).toHaveValue(recommendedPages);
  await expect(card.getByText(/changed from recommended:/)).toHaveCount(0);

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: 'test-results/recommendations-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/recommendations-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });

  await page.getByRole('button', { name: 'Save version' }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await expect(card.getByText(/Version 1 · Recommended on .+ · 0 changed by you/)).toBeVisible();

  const pipelines = await (
    await request.get(`/api/projects/${project.id}/pipelines?kind=ingestion`)
  ).json();
  const versions = await (
    await request.get(`/api/projects/${project.id}/pipelines/${pipelines.items[0].id}/versions`)
  ).json();
  const provenance = versions.items[0].settings_provenance;
  const node = Object.values(provenance.nodes)[0] as {
    fields: Record<string, { basis: string; recommended: unknown }>;
  };
  expect(node.fields.include_path_prefixes).toMatchObject({
    basis: 'computed',
    recommended: ['/docs/'],
  });
  expect(node.fields.max_pages.basis).toBe('computed');
  expect(errors).toEqual([]);
});
