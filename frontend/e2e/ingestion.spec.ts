import { expect, test } from '@playwright/test';

test('website discovery is bounded, inspectable, and preview-only', async ({ page, request }) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires isolated deterministic providers.',
  );
  test.setTimeout(90000);
  const project = (await (
    await request.post('/api/projects', {
      data: { name: `Website preview ${Date.now()}` },
    })
  ).json()) as { id: string };

  await page.goto(`/#/projects/${project.id}/pipelines/new?kind=ingestion`);
  await page.getByLabel('Pipeline name').fill('Controlled website preview');
  await page.getByLabel('Source type').selectOption('website');
  await page.getByLabel('Starting URL').fill('https://controlled.example/');
  await page.getByLabel('Allowed origins (one per line)').fill('https://controlled.example');
  await page.getByRole('button', { name: 'Preview source' }).click();

  await expect(page.getByRole('heading', { name: '2 included · 2 excluded' })).toBeVisible({
    timeout: 30000,
  });
  await expect(page.getByText(/1 duplicate · 0 failed/)).toBeVisible();
  await expect(
    page
      .getByRole('listitem')
      .filter({ hasText: 'https://controlled.example/guide' })
      .filter({ hasText: 'included · HTML page is within scope' }),
  ).toContainText('https://controlled.example/guide');
  await expect(page.getByText(/robots.txt disallows this URL/)).toBeVisible();

  await page.getByRole('button', { name: 'Save version' }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run saved version' })).toBeDisabled();
  await expect(page.getByText(/preview-only in this phase/)).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: 'test-results/website-preview-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/website-preview-mobile.png', fullPage: true });
});

test('existing files publish an exact index that grounds an answer pipeline', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires isolated deterministic providers.',
  );
  test.setTimeout(120000);
  page.setDefaultTimeout(20000);
  const project = (await (
    await request.post('/api/projects', {
      data: { name: `Existing files ingestion ${Date.now()}` },
    })
  ).json()) as { id: string };

  await page.goto(`/#/projects/${project.id}/knowledge-base`);
  for (const [name, content] of [
    ['orchard.txt', 'The orchard grows apples. The harvest begins in September.'],
    ['packing.txt', 'Apples are packed in recycled paper boxes.'],
  ]) {
    await page.getByRole('button', { name: 'Add document', exact: true }).click();
    await page.getByLabel('PDF or UTF-8 TXT').setInputFiles({
      name,
      mimeType: 'text/plain',
      buffer: Buffer.from(content),
    });
    await page.getByRole('button', { name: 'Upload document', exact: true }).click();
    await page.getByRole('button', { name: 'Start processing', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Inspect 1 chunks' })).toBeVisible({
      timeout: 30000,
    });
  }

  await page.getByRole('link', { name: 'Pipelines', exact: true }).click();
  await page.getByRole('tab', { name: 'Ingestion pipelines' }).click();
  await page.getByRole('link', { name: 'New ingestion pipeline' }).click();
  await expect(page.getByRole('heading', { name: 'Ingestion editor' })).toBeVisible();
  await page.getByLabel('Pipeline name').fill('Project files ingestion');
  await page.getByText('orchard.txt', { exact: true }).click();
  await page.getByText('packing.txt', { exact: true }).click();
  await page.getByRole('button', { name: 'Preview source' }).click();
  await expect(page.getByRole('heading', { name: '2 included · 0 excluded' })).toBeVisible({
    timeout: 30000,
  });
  await page.getByRole('button', { name: 'Save version' }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Run saved version' }).click();
  await expect(page.getByRole('heading', { name: 'Ingested knowledge · succeeded' })).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByText(/processing v2 · 1 chunks/)).toHaveCount(2);
  await expect(page.getByRole('link', { name: /Inspect published index v1/ })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: 'test-results/ingestion-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/ingestion-mobile.png', fullPage: true });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('link', { name: 'Pipelines', exact: true }).click();
  await page.getByRole('tab', { name: 'Answer pipelines' }).click();
  await page.getByRole('link', { name: 'New answer pipeline' }).click();
  await page
    .getByLabel('Documents to search', { exact: true })
    .selectOption({ label: 'Ingested knowledge · Version 1 · 2 passages' });
  await page.getByRole('button', { name: 'Save version' }).click();
  await page.getByRole('button', { name: 'Open Playground' }).click();
  await page.getByLabel('Question', { exact: true }).fill('What does the orchard grow?');
  await page.getByRole('button', { name: 'Run pipeline test', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Query result' })).toContainText(
    'The orchard grows apples. [S1]',
    { timeout: 30000 },
  );
});
