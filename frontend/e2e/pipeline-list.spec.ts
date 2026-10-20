import { readFileSync } from 'node:fs';
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

// Spec 0015 U1, U2 and U5: the pipeline list shows each pipeline's last run and index with
// search and a last-run filter, the phone editor leaves room for the canvas, and counts of
// one read in the singular. Isolated stack with deterministic providers only.
const fixture = (name: string) => readFileSync(new URL(`./fixtures/${name}`, import.meta.url));

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

async function seriousIssues(page: Page) {
  const result = await new AxeBuilder({ page }).analyze();
  return result.violations
    .filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')
    .map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target).join(' ')}`);
}

async function pipeline(
  request: APIRequestContext,
  root: string,
  name: string,
  file: { name: string; mimeType: string; buffer: Buffer },
  run: boolean,
) {
  const document = await (await request.post(`${root}/documents`, { multipart: { file } })).json();
  const execution = JSON.parse(fixture('existing-files-v5-execution.json').toString());
  execution.nodes[0].config.document_ids = [document.id];
  execution.nodes.at(-1).knowledge_set_name = name;
  const saved = await request.post(`${root}/pipelines`, {
    data: {
      kind: 'ingestion',
      name,
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
  if (run) {
    const started = await (
      await request.post(
        `${root}/pipelines/${version.pipeline_id}/versions/${version.id}/ingestion-runs`,
      )
    ).json();
    await expect
      .poll(
        async () =>
          (await (await request.get(`${root}/ingestion-runs/${started.id}`)).json()).status,
        { timeout: 60000 },
      )
      .toBe('succeeded');
  }
  return version.pipeline_id as string;
}

test('pipeline list, phone editor and singular counts', async ({ page, request }) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires isolated deterministic providers.',
  );
  test.setTimeout(240000);
  page.setDefaultTimeout(15000);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const project = await (
    await request.post('/api/projects', { data: { name: `Pipeline list ${Date.now()}` } })
  ).json();
  const root = `/api/projects/${project.id}`;
  const xlsx = {
    name: 'rows.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: fixture('rows.xlsx'),
  };
  const ran = await pipeline(request, root, 'Spreadsheet rows', xlsx, true);
  const single = await pipeline(
    request,
    root,
    'One passage',
    { name: 'note.txt', mimeType: 'text/plain', buffer: Buffer.from('The harbor opens at nine.') },
    true,
  );
  await pipeline(request, root, 'Never started', xlsx, false);

  // U1: one row per pipeline with its last run and published index.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/projects/${project.id}/pipelines?kind=ingestion`);
  const list = page.getByRole('list', { name: 'Ingestion pipelines' });
  const row = (name: string) => list.getByRole('listitem').filter({ hasText: name });
  await expect(row('Spreadsheet rows')).toContainText('Complete');
  await expect(row('Spreadsheet rows')).toContainText(
    'Index Spreadsheet rows · version 1 · current',
  );
  await expect(row('Never started')).toContainText('Never run');
  await expect(row('Never started')).toContainText('No published index');
  await expect(page.getByText('3 pipelines · newest first')).toBeVisible();
  expect(await seriousIssues(page)).toEqual([]);

  await page.getByLabel('Search pipelines').fill('spread');
  await expect(list.getByRole('listitem')).toHaveCount(1);
  await expect(page.getByText('1 pipeline match · newest first')).toBeVisible();
  await page.getByLabel('Search pipelines').fill('');
  await page.getByLabel('Last run').selectOption('never_run');
  await expect(list.getByRole('listitem')).toHaveCount(1);
  await expect(row('Never started')).toBeVisible();
  await page.getByLabel('Last run').selectOption('failed');
  await expect(page.getByRole('heading', { name: 'No pipelines match' })).toBeVisible();
  await page.getByRole('button', { name: 'Clear search and filter' }).click();
  await expect(list.getByRole('listitem')).toHaveCount(3);
  await page.screenshot({ path: 'test-results/pipeline-list-desktop.png', fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(row('Spreadsheet rows')).toContainText('Complete');
  await noOverflow(page);
  expect(await seriousIssues(page)).toEqual([]);
  await page.screenshot({ path: 'test-results/pipeline-list-phone.png', fullPage: true });

  // U2: on a phone the name, version and Run share one line and the canvas starts within
  // the first 40% of the screen.
  await page.goto(`/#/projects/${project.id}/pipelines/${ran}?kind=ingestion`);
  await expect(page.getByLabel('Selected stage')).toBeVisible();
  const centre = async (locator: ReturnType<Page['getByLabel']>) => {
    const box = (await locator.boundingBox())!;
    return box.y + box.height / 2;
  };
  const nameY = await centre(page.getByLabel('Pipeline name'));
  const versionY = await centre(page.getByLabel('Saved ingestion version'));
  const runY = await centre(page.getByRole('button', { name: 'Run', exact: true }));
  expect(Math.abs(nameY - versionY)).toBeLessThan(4);
  expect(Math.abs(nameY - runY)).toBeLessThan(4);
  const canvas = (await page.locator('.react-flow').first().boundingBox())!;
  expect(canvas.y).toBeLessThanOrEqual(844 * 0.4);
  const strip = (await page.locator('#ingestion-run').boundingBox())!;
  expect(strip.height).toBeLessThan(52);
  const ready = page.locator('#ingestion-run').getByText('· index v1 ready');
  await expect(ready).toBeVisible();
  // The whole outcome fits beside Run details, not cut short.
  expect(await ready.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
  await expect(page.getByRole('button', { name: 'Preview processing' })).toBeHidden();
  await page.getByRole('button', { name: 'More actions' }).click();
  await expect(page.getByRole('button', { name: 'Preview processing' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save version' })).toBeVisible();
  await page.keyboard.press('Escape');
  await noOverflow(page);
  expect(await seriousIssues(page)).toEqual([]);
  await page.screenshot({ path: 'test-results/ingestion-editor-phone.png' });
  await page.getByRole('button', { name: 'Run details' }).click();
  await expect(
    page.getByRole('link', { name: 'Use index version 1 in answer pipeline' }),
  ).toBeVisible();

  // Desktop is unchanged: the actions stay in the toolbar.
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByRole('button', { name: 'Preview processing' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run ingestion' })).toBeVisible();
  await expect(page.getByTestId('published-index')).toBeVisible();
  expect(await seriousIssues(page)).toEqual([]);

  // U5: one passage reads in the singular.
  await page.goto(`/#/projects/${project.id}/pipelines/${single}?kind=ingestion`);
  await expect(page.getByText('1 chunk ready')).toBeVisible();
  expect(errors).toEqual([]);
});
