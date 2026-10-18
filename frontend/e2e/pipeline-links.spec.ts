import { readFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';

// Spec 0015 U3 and U4: pipeline links open the saved kind, a wrong ID says so, and
// Run details show the versions a run used and what each passage is searched as.
const fixture = (name: string) => readFileSync(new URL(`./fixtures/${name}`, import.meta.url));

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test('links open the saved kind, wrong IDs say not found, runs show what ran', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires isolated deterministic providers.',
  );
  test.setTimeout(180000);
  page.setDefaultTimeout(15000);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const project = await (
    await request.post('/api/projects', { data: { name: `Pipeline links ${Date.now()}` } })
  ).json();
  const root = `/api/projects/${project.id}`;
  const document = await (
    await request.post(`${root}/documents`, {
      multipart: {
        file: {
          name: 'rows.xlsx',
          mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          buffer: fixture('rows.xlsx'),
        },
      },
    })
  ).json();
  const execution = JSON.parse(fixture('existing-files-v5-execution.json').toString());
  execution.nodes[0].config.document_ids = [document.id];
  const saved = await request.post(`${root}/pipelines`, {
    data: {
      kind: 'ingestion',
      name: 'Spreadsheet rows',
      execution,
      layout: {
        positions: Object.fromEntries(
          execution.nodes.map((node: { id: string }, i: number) => [
            node.id,
            { x: 80, y: 40 + i * 116 },
          ]),
        ),
      },
    },
  });
  expect(saved.status(), await saved.text()).toBe(201);
  const version = await saved.json();
  const run = await (
    await request.post(
      `${root}/pipelines/${version.pipeline_id}/versions/${version.id}/ingestion-runs`,
    )
  ).json();
  await expect
    .poll(
      async () => (await (await request.get(`${root}/ingestion-runs/${run.id}`)).json()).status,
      {
        timeout: 60000,
      },
    )
    .toBe('succeeded');

  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width > 400 ? 900 : 844 });
    // U3: a link without ?kind=ingestion opens the ingestion editor, not a blank page.
    await page.goto(`/#/projects/${project.id}/pipelines/${version.pipeline_id}`);
    await expect(page.getByLabel('Selected stage')).toBeVisible();
    await expect(page).toHaveURL(/\?kind=ingestion/);
    await noOverflow(page);
    // A wrong ID says so and links back to the list.
    await page.goto(`/#/projects/${project.id}/pipelines/00000000-0000-4000-8000-000000000000`);
    await expect(page.getByRole('heading', { name: 'Pipeline not found' })).toBeVisible();
    await page.getByRole('link', { name: 'Back to pipelines' }).click();
    await expect(page).toHaveURL(new RegExp(`/projects/${project.id}/pipelines$`));
    await noOverflow(page);
  }

  // U4: Run details name the versions, and the chunks say what they are searched as.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/projects/${project.id}/pipelines/${version.pipeline_id}?kind=ingestion`);
  await page.getByRole('button', { name: 'Run details' }).first().click();
  await expect(page.getByTestId('run-stage-versions')).toHaveText(
    'Extractor layout-ocr-v6 · cleaner structure-clean-v2 · chunker section-token-v5',
  );
  await page.getByRole('button', { name: 'Inspect content' }).first().click();
  await page.getByRole('tab', { name: 'Chunks' }).click();
  const row = page.getByRole('region', { name: 'Chunk 2 searched as' });
  await expect(row).toContainText(
    'Economic inactivity by sex, aged 16 to 64. Time period: Oct to Dec 2022; Males: 22.7',
  );
  await expect(page.getByRole('region', { name: 'Chunk 1 searched as' })).toHaveCount(0);
  await row.scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'test-results/searched-as-desktop.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(row).toBeVisible();
  await noOverflow(page);
  await page.screenshot({ path: 'test-results/searched-as-phone.png', fullPage: true });
  expect(errors).toEqual([]);
});
