import { expect, test } from '@playwright/test';

test('S3 preview publishes and incrementally refreshes an exact index', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires isolated deterministic providers.',
  );
  test.setTimeout(120000);
  const project = (await (
    await request.post('/api/projects', {
      data: { name: `S3 ingestion ${Date.now()}` },
    })
  ).json()) as { id: string };
  const connection = (await (
    await request.post(`/api/projects/${project.id}/source-connections`, {
      data: {
        name: 'Controlled research bucket',
        credentials: {
          kind: 's3',
          access_key_id: 'fixture-access',
          secret_access_key: 'fixture-secret',
        },
      },
    })
  ).json()) as { id: string };
  await request.post('/api/test/s3-state/first');

  await page.goto(`/#/projects/${project.id}/pipelines/new?kind=ingestion`);
  await page.getByLabel('Pipeline name').fill('Controlled S3 ingestion');
  await page.getByLabel('Source type').selectOption('s3');
  await page.getByLabel('S3 connection').selectOption(connection.id);
  await page.getByRole('textbox', { name: 'Bucket', exact: true }).fill('research-archive');
  await page.getByLabel('Prefix (optional)').fill('docs/');
  await page.getByLabel('Expected AWS account ID (optional)').fill('123456789012');
  await page.getByLabel('PDF').uncheck();
  await page.getByRole('button', { name: 'Preview source' }).click();
  await expect(page.getByRole('heading', { name: '2 included · 0 excluded' })).toBeVisible({
    timeout: 30000,
  });
  await expect(page.getByText('s3://research-archive/docs/orchard.txt')).toBeVisible();

  await page.getByRole('button', { name: 'Save version' }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Run saved version' }).click();
  await expect(page.locator('.ingestion-run-state[data-status="succeeded"]')).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByText('2 new · 0 changed · 0 unchanged · 0 removed')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Inspect published index v1' })).toBeVisible();

  await request.post('/api/test/s3-state/second');
  await page.getByRole('button', { name: 'Run saved version' }).click();
  await expect(page.getByText('1 new · 0 changed · 1 unchanged · 1 removed')).toBeVisible({
    timeout: 60000,
  });
  await expect(page.locator('.ingestion-run-state[data-status="succeeded"]')).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByText('s3://research-archive/docs/new.txt')).toBeVisible({
    timeout: 10000,
  });
  await expect(page.getByRole('link', { name: 'Inspect published index v2' })).toBeVisible();

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: 'test-results/s3-ingestion-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/s3-ingestion-mobile.png', fullPage: true });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('link', { name: 'Pipelines', exact: true }).click();
  await page.getByRole('tab', { name: 'Answer pipelines' }).click();
  await page.getByRole('link', { name: 'New answer pipeline' }).click();
  await page.reload();
  await page
    .getByLabel('Documents to search', { exact: true })
    .selectOption({ label: 'Ingested knowledge · Version 2 · 2 passages' });
  await page.getByRole('button', { name: 'Save version' }).click();
  await page.getByRole('button', { name: 'Open Playground' }).click();
  await page.getByLabel('Question', { exact: true }).fill('What does the orchard grow?');
  await page.getByRole('button', { name: 'Run pipeline test', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Query result' })).toContainText(
    'The orchard grows apples. [S1]',
    { timeout: 30000 },
  );
});
