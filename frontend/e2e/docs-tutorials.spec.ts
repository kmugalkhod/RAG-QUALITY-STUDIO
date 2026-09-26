import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';

const sample = readFileSync('../docs/site/static/examples/harbor-desk.txt');
const screenshots = '../docs/site/static/img/screenshots';

test.beforeEach(() => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Docs journeys require the isolated deterministic-provider stack.',
  );
});

test('documentation T1: synthetic upload through cited answer', async ({ page }) => {
  test.setTimeout(120000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/');
  await page.getByRole('button', { name: 'New project', exact: true }).click();
  await page.getByLabel('Project name').fill('Harbor docs');
  await page.locator('.create-project-panel').screenshot({ path: `${screenshots}/00-project.png` });
  await page.getByRole('button', { name: 'Create project', exact: true }).click();
  await page.getByRole('link', { name: 'Harbor docs', exact: true }).first().click();
  await page.getByRole('link', { name: 'Knowledge Base', exact: true }).click();
  await page.getByRole('button', { name: 'Add document', exact: true }).click();
  await page
    .getByLabel('Document file')
    .setInputFiles({ name: 'harbor-desk.txt', mimeType: 'text/plain', buffer: sample });
  await expect(page.getByRole('link', { name: 'Supported files and upload help' })).toHaveAttribute(
    'href',
    'http://127.0.0.1:3000/docs/knowledge-base/documents/',
  );
  await expect(page.getByText('Loading upload limit...')).toHaveCount(0);
  await expect(page.getByText('Loading documents...')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Upload document', exact: true })).toBeEnabled();
  await page.screenshot({ path: `${screenshots}/01-upload.png` });
  await page.getByRole('button', { name: 'Upload document', exact: true }).click();
  await page.getByRole('button', { name: 'Start processing', exact: true }).click();
  await expect(page.getByRole('button', { name: /Inspect \d+ chunks/ })).toBeVisible({
    timeout: 30000,
  });
  await page.screenshot({ path: `${screenshots}/02-prepared.png` });
  await page.getByRole('tab', { name: 'Collections', exact: true }).click();
  await page.getByRole('button', { name: 'Publish prepared documents' }).click();
  await expect(
    page.getByRole('button', { name: 'Open Uploaded documents collection' }),
  ).toBeVisible({ timeout: 60000 });
  await expect(page.getByText('Ready', { exact: true }).first()).toBeVisible({ timeout: 60000 });
  await page.reload();
  await page.getByRole('button', { name: 'Open Uploaded documents collection' }).click();
  await expect(page.getByRole('heading', { name: 'Uploaded documents' })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${screenshots}/03-collection.png` });
  await page.getByRole('link', { name: /Use version \d+ in a pipeline/ }).click();
  await page.getByLabel('Pipeline name').fill('Harbor answer');
  await page.getByRole('button', { name: 'Save version' }).click();
  await page.getByRole('button', { name: 'Open Playground' }).click();
  await page.getByLabel('Question', { exact: true }).fill('When is Harbor Desk open?');
  await page.getByRole('button', { name: 'Run pipeline test', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Query result' })).toContainText('Monday', {
    timeout: 60000,
  });
  await page.getByRole('button', { name: 'Sources & details' }).click();
  await expect(page.getByText('09:00–17:00').first()).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${screenshots}/04-evidence.png` });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `${screenshots}/05-evidence-mobile.png`, fullPage: true });
});

test('documentation T2: Existing Files preview and ingestion run', async ({ page, request }) => {
  test.setTimeout(120000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const project = (await (
    await request.post('/api/projects', { data: { name: 'Harbor ingestion' } })
  ).json()) as { id: string };
  await page.goto(`/#/projects/${project.id}/knowledge-base`);
  await page.getByRole('button', { name: 'Add document', exact: true }).click();
  await page
    .getByLabel('Document file')
    .setInputFiles({ name: 'harbor-desk.txt', mimeType: 'text/plain', buffer: sample });
  await page.getByRole('button', { name: 'Upload document', exact: true }).click();
  await page.getByRole('button', { name: 'Start processing', exact: true }).click();
  await expect(page.getByRole('button', { name: /Inspect \d+ chunks/ })).toBeVisible({
    timeout: 30000,
  });
  await page.getByRole('link', { name: 'Pipelines', exact: true }).click();
  await page.getByRole('tab', { name: 'Ingestion pipelines' }).click();
  await page.getByRole('link', { name: 'New ingestion pipeline' }).click();
  await page.getByLabel('Pipeline name').fill('Harbor files ingestion');
  await page.getByText('harbor-desk.txt', { exact: true }).click();
  await page.getByRole('button', { name: 'Preview processing' }).click();
  await expect(page.getByRole('heading', { name: '1 included · 0 excluded' })).toBeVisible({
    timeout: 30000,
  });
  await page.getByRole('button', { name: 'Inspect stages' }).click();
  await expect(page.getByRole('tablist', { name: 'Preview stage' })).toBeVisible();
  await page
    .locator('#ingestion-preview .content-derivation-inspector')
    .screenshot({ path: `${screenshots}/06-ingestion-preview.png` });
  await page.getByRole('button', { name: 'Save version' }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Run ingestion' }).click();
  await expect(page.locator('.ingestion-run-state[data-status="succeeded"]')).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByRole('link', { name: 'Inspect published index' })).toBeVisible();
  await page.screenshot({ path: `${screenshots}/07-ingestion-run.png` });
  await page
    .locator('.ingestion-published-index')
    .screenshot({ path: `${screenshots}/08-published-index.png` });
});
