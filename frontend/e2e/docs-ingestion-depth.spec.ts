import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';

const screenshots = '../docs/site/static/img/screenshots';
const corrupt = readFileSync('../docs/site/static/examples/harbor-quality-corrupt.txt');
const repaired = readFileSync('../docs/site/static/examples/harbor-quality-repaired.txt');

test.beforeEach(() => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires isolated deterministic providers and source transport.',
  );
});

test('documentation T3: reuse one Website snapshot through the UI for a second index', async ({
  page,
  request,
}) => {
  test.setTimeout(180000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const project = (await (
    await request.post('/api/projects', { data: { name: `Docs snapshot ${Date.now()}` } })
  ).json()) as { id: string };
  await page.goto(`/#/projects/${project.id}/pipelines/new?kind=ingestion`);
  await page.getByLabel('Pipeline name').fill('Controlled website lineage');
  await page.getByLabel('Source type').selectOption('website');
  await page.getByLabel('Starting URL').fill('https://controlled.example/');
  await page.getByLabel('Allowed origins (one per line)').fill('https://controlled.example');
  await page.getByRole('button', { name: 'Preview processing' }).click();
  await expect(page.getByRole('heading', { name: '2 included · 2 excluded' })).toBeVisible({
    timeout: 30000,
  });
  await page.getByRole('button', { name: 'Save version' }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Collect source & publish index' }).click();
  await expect(page.locator('.ingestion-run-state[data-status="succeeded"]')).toBeVisible({
    timeout: 60000,
  });
  const snapshots = (await (
    await request.get(`/api/projects/${project.id}/source-snapshots`)
  ).json()) as { items: { id: string }[] };
  expect(snapshots.items).toHaveLength(1);
  const snapshotId = snapshots.items[0].id;

  await page
    .getByRole('navigation', { name: 'Ingestion stages' })
    .getByRole('button', { name: /Chunk/ })
    .click();
  await page.getByLabel('Chunking algorithm').selectOption('character_window');
  await page.getByLabel('Chunk size (characters)').fill('600');
  await page.getByRole('button', { name: 'Save version' }).click();
  await expect(page.getByText('Saved version 2', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Knowledge Base', exact: true }).click();
  await page.getByRole('tab', { name: 'Collections', exact: true }).click();
  await page.getByRole('tab', { name: 'Source history' }).click();
  await page.getByRole('button', { name: /Snapshot 1/ }).click();
  await expect(page.getByRole('heading', { name: 'Snapshot 1' })).toBeVisible();
  await expect(page.getByRole('link', { name: /Ingested knowledge · v1/ })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Snapshot reuse guide' })).toHaveAttribute(
    'href',
    'http://127.0.0.1:3000/docs/ingestion/source-history/',
  );
  await page
    .locator('.snapshot-detail')
    .screenshot({ path: `${screenshots}/11-source-snapshot.png` });
  await page
    .getByLabel('Ingestion pipeline version')
    .selectOption({ label: 'Controlled website lineage · v2' });
  await page.getByLabel('Index name').fill('Controlled website variant');
  const runRequest = page.waitForRequest(
    (value) => value.method() === 'POST' && value.url().includes('/ingestion-runs'),
  );
  await page.getByRole('button', { name: 'Create index variant' }).click();
  expect((await runRequest).postDataJSON().source_input).toEqual({
    kind: 'snapshot',
    source_snapshot_id: snapshotId,
  });
  await expect(page.getByRole('status').filter({ hasText: 'Run succeeded:' })).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByRole('link', { name: /Controlled website variant · v1/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /Ingested knowledge · v1/ })).toBeVisible();
  await page
    .locator('.snapshot-detail')
    .screenshot({ path: `${screenshots}/12-snapshot-variant.png` });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('documentation T5: strict finding, repaired source and redacted publication', async ({
  page,
  request,
}) => {
  test.setTimeout(180000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const project = (await (
    await request.post('/api/projects', { data: { name: `Docs quality ${Date.now()}` } })
  ).json()) as { id: string };
  await page.goto(`/#/projects/${project.id}/knowledge-base`);
  for (const [name, content] of [
    ['harbor-quality-corrupt.txt', corrupt],
    ['harbor-quality-repaired.txt', repaired],
  ] as const) {
    await page.getByRole('button', { name: 'Add document', exact: true }).click();
    await page
      .getByLabel('Document file')
      .setInputFiles({ name, mimeType: 'text/plain', buffer: content });
    await page.getByRole('button', { name: 'Upload document', exact: true }).click();
    await expect(page.getByRole('heading', { name: `Process: ${name}` })).toBeVisible();
  }
  await page.getByRole('link', { name: 'Pipelines', exact: true }).click();
  await page.getByRole('tab', { name: 'Ingestion pipelines' }).click();
  await page.getByRole('link', { name: 'New ingestion pipeline' }).click();
  await page.getByLabel('Pipeline name').fill('Harbor quality repair');
  await page.getByText('harbor-quality-corrupt.txt', { exact: true }).click();
  await page
    .getByRole('navigation', { name: 'Ingestion stages' })
    .getByRole('button', { name: /Extract/ })
    .click();
  await page.getByLabel('Quality policy').selectOption('strict-v1');
  await page.getByText('Quality thresholds', { exact: true }).click();
  await page.getByLabel('Maximum replacement-character ratio').fill('0');
  await page
    .getByRole('navigation', { name: 'Ingestion stages' })
    .getByRole('button', { name: /Clean/ })
    .click();
  await expect(
    page.getByLabel('Redact sensitive values before chunking and embedding'),
  ).toBeChecked();
  await page.getByRole('button', { name: 'Preview processing' }).click();
  await expect(page.getByText(/Quality: 0 pass · 0 warn · 0 exclude · 1 fail/)).toBeVisible({
    timeout: 30000,
  });
  await expect(page.getByText(/Replacement-character frequency exceeded/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Interpret quality findings' })).toHaveAttribute(
    'href',
    'http://127.0.0.1:3000/docs/ingestion/quality/',
  );
  await page
    .locator('#ingestion-preview > .section-heading')
    .screenshot({ path: `${screenshots}/09-quality-failure.png` });
  await page.getByRole('button', { name: 'Inspect stages' }).click();
  await page.getByRole('tab', { name: 'Cleaned' }).click();
  await expect(page.locator('#ingestion-preview .content-derivation-inspector')).toContainText(
    '[EMAIL]',
  );

  await page
    .getByRole('navigation', { name: 'Ingestion stages' })
    .getByRole('button', { name: /Source/ })
    .click();
  await page
    .getByRole('region', { name: 'Stage settings' })
    .getByText('harbor-quality-corrupt.txt', { exact: true })
    .click();
  await page
    .getByRole('region', { name: 'Stage settings' })
    .getByText('harbor-quality-repaired.txt', { exact: true })
    .click();
  await page.getByRole('button', { name: 'Preview processing' }).click();
  await expect(page.getByText(/Quality: 1 pass · 0 warn · 0 exclude · 0 fail/)).toBeVisible({
    timeout: 30000,
  });
  await page.getByRole('button', { name: 'Inspect stages' }).click();
  await page.getByRole('tab', { name: 'Cleaned' }).click();
  await expect(page.locator('#ingestion-preview .content-derivation-inspector')).toContainText(
    '[EMAIL]',
  );
  await page
    .locator('#ingestion-preview .content-derivation-inspector')
    .screenshot({ path: `${screenshots}/10-quality-repaired.png` });
  await page
    .getByRole('navigation', { name: 'Ingestion stages' })
    .getByRole('button', { name: /Publish/ })
    .click();
  await page.getByLabel('New knowledge set name').fill('Harbor repaired quality');
  await page.getByRole('button', { name: 'Save version' }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Run ingestion' }).click();
  await expect(page.locator('.ingestion-run-state[data-status="succeeded"]')).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByRole('link', { name: 'Inspect published index' })).toBeVisible();
  await expect(page.locator('.ingestion-run-details')).toContainText('harbor-quality-repaired.txt');
  await expect(page.locator('.ingestion-run-details')).not.toContainText(
    'harbor-quality-corrupt.txt',
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
