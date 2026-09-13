import { expect, test } from '@playwright/test';

test('Confluence preview publishes and incrementally refreshes an exact index', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires isolated deterministic providers.',
  );
  test.setTimeout(120000);
  const project = (await (
    await request.post('/api/projects', { data: { name: `Confluence ingestion ${Date.now()}` } })
  ).json()) as { id: string };
  const connection = (await (
    await request.post(`/api/projects/${project.id}/source-connections`, {
      data: {
        name: 'Controlled Confluence site',
        credentials: {
          kind: 'confluence',
          site_url: 'https://controlled.atlassian.net',
          email: 'reader@example.com',
          api_token: 'fixture-confluence-token',
        },
      },
    })
  ).json()) as { id: string };
  await request.post('/api/test/confluence-state/first');

  await page.goto(`/#/projects/${project.id}/pipelines/new?kind=ingestion`);
  await page.getByLabel('Pipeline name').fill('Controlled Confluence ingestion');
  await page.getByLabel('Source type').selectOption('confluence');
  await page.getByLabel('Confluence connection').selectOption(connection.id);
  await expect(
    page.locator('.react-flow__node').first().getByText('Confluence', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Preview source' }).click();
  await expect(page.getByRole('heading', { name: '2 included · 0 excluded' })).toBeVisible({
    timeout: 30000,
  });
  await expect(page.getByText('confluence://controlled.atlassian.net/page/101')).toBeVisible();

  await page.getByRole('button', { name: 'Save version' }).click();
  await page.getByRole('button', { name: 'Run saved version' }).click();
  await expect(page.getByRole('heading', { name: 'Ingested knowledge · succeeded' })).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByText('2 new · 0 changed · 0 unchanged · 0 removed')).toBeVisible();

  await request.post('/api/test/confluence-state/second');
  await page.getByRole('button', { name: 'Run saved version' }).click();
  await expect(page.getByText('1 new · 0 changed · 1 unchanged · 1 removed')).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByRole('heading', { name: 'Ingested knowledge · succeeded' })).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByRole('link', { name: 'Inspect published index v2' })).toBeVisible();

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: 'test-results/confluence-ingestion-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect
    .poll(() =>
      page
        .locator('.react-flow__node')
        .first()
        .evaluate((node) => {
          const bounds = node.getBoundingClientRect();
          return bounds.left >= 0 && bounds.right <= window.innerWidth;
        }),
    )
    .toBe(true);
  await page.screenshot({ path: 'test-results/confluence-ingestion-mobile.png', fullPage: true });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('link', { name: 'Pipelines', exact: true }).click();
  await page.getByRole('tab', { name: 'Answer pipelines' }).click();
  await page.getByRole('link', { name: 'New answer pipeline' }).click();
  const indexSelect = page.getByLabel('Documents to search', { exact: true });
  const indexValue = await indexSelect
    .locator('option')
    .filter({ hasText: 'Ingested knowledge · Version 2' })
    .getAttribute('value');
  expect(indexValue).toBeTruthy();
  await indexSelect.selectOption(indexValue!);
  await page.getByRole('button', { name: 'Save version' }).click();
  await page.getByRole('button', { name: 'Open Playground' }).click();
  await page.getByLabel('Question', { exact: true }).fill('What does the orchard grow?');
  await page.getByRole('button', { name: 'Run pipeline test', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Query result' })).toContainText(
    'The orchard grows apples. [S1]',
    { timeout: 30000 },
  );
});
