import { expect, test } from '@playwright/test';

const docs = process.env.DOCS_BASE_URL || 'http://127.0.0.1:3000';

test('docs navigation, local search, semantic content and mobile width', async ({ page }) => {
  await page.goto(docs);
  await expect(
    page.getByRole('heading', { name: /From source material to an answer/ }),
  ).toBeVisible();
  await page.getByRole('link', { name: /Start with one cited answer/ }).click();
  await expect(page).toHaveURL(`${docs}/docs/start/first-workflow/`);
  await expect(page.getByRole('heading', { name: 'First RAG workflow' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'harbor-desk.txt' })).toHaveAttribute(
    'href',
    '/examples/harbor-desk.txt',
  );
  expect((await page.request.get(`${docs}/examples/harbor-desk.txt`)).status()).toBe(200);
  expect((await page.request.get(`${docs}/img/screenshots/01-upload.png`)).status()).toBe(200);
  await expect(page.getByRole('link', { name: 'mobile evidence view' })).toHaveAttribute(
    'href',
    '/img/screenshots/05-evidence-mobile.png',
  );
  expect((await page.request.get(`${docs}/img/screenshots/05-evidence-mobile.png`)).status()).toBe(
    200,
  );
  expect(await page.locator('img:not([alt])').count()).toBe(0);
  await page.getByRole('textbox', { name: 'Search' }).focus();
  await expect(page.getByRole('textbox', { name: 'Search' })).toBeFocused();
  await page.getByRole('textbox', { name: 'Search' }).fill('Collections and index versions');
  await expect(
    page.getByRole('option', { name: /Collections and index versions/ }).first(),
  ).toBeVisible();
  await page
    .getByRole('option', { name: /Collections and index versions/ })
    .first()
    .click();
  await expect(page).toHaveURL(new RegExp(`${docs}/docs/knowledge-base/collections/\\?`));
  await page.goto(`${docs}/docs/start/first-workflow/`);
  await page.screenshot({ path: 'test-results/docs-desktop.png' });
  await page.setViewportSize({ width: 720, height: 1000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByRole('heading', { name: 'First RAG workflow' })).toBeVisible();
  await page.getByRole('textbox', { name: 'Search' }).click();
  await expect(page.getByRole('combobox', { name: 'Search' })).toBeFocused();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Toggle navigation bar' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Toggle navigation bar' })).toHaveAttribute(
    'aria-expanded',
    'true',
  );
  await expect(page.getByRole('button', { name: 'Start', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Choose your path' })).toBeVisible();
  await page.screenshot({ path: 'test-results/docs-mobile.png' });
});

test('ingestion depth pages, diagrams and synthetic downloads remain usable at narrow widths', async ({
  page,
}) => {
  await page.goto(`${docs}/docs/ingestion/source-history/`);
  await expect(
    page.getByRole('heading', { name: 'Source history and snapshot reuse' }),
  ).toBeVisible();
  await expect(
    page.getByRole('img', {
      name: /One source snapshot, two independent index versions|Remote collection fixes source revisions/,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Open the lineage diagram at full size' }),
  ).toHaveAttribute('href', '/img/source-lineage.svg');
  expect((await page.request.get(`${docs}/img/source-lineage.svg`)).status()).toBe(200);
  await page.getByRole('textbox', { name: 'Search' }).fill('Diagnose quality findings');
  await expect(
    page.getByRole('option', { name: /Diagnose quality findings/ }).first(),
  ).toBeVisible();
  await page
    .getByRole('option', { name: /Diagnose quality findings/ })
    .first()
    .click();
  await expect(page.getByRole('heading', { name: 'Diagnose quality findings' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'the deliberately corrupt file' })).toHaveAttribute(
    'href',
    '/examples/harbor-quality-corrupt.txt',
  );
  expect((await page.request.get(`${docs}/examples/harbor-quality-corrupt.txt`)).status()).toBe(
    200,
  );
  expect((await page.request.get(`${docs}/examples/harbor-quality-repaired.txt`)).status()).toBe(
    200,
  );
  expect((await page.request.get(`${docs}/examples/README.md`)).status()).toBe(200);
  expect(await page.locator('img:not([alt])').count()).toBe(0);
  await page.screenshot({ path: 'test-results/docs-ingestion-desktop.png' });
  await page.setViewportSize({ width: 720, height: 1000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Toggle navigation bar' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Sources and ingestion' })).toBeVisible();
  await page.screenshot({ path: 'test-results/docs-ingestion-mobile.png' });
});

test('evaluation and generated API reference are searchable and usable on mobile', async ({
  page,
}) => {
  await page.goto(`${docs}/docs/api/reference/`);
  await expect(page.getByRole('heading', { name: 'Endpoint reference' })).toBeVisible();
  await page.getByRole('link', { name: 'Datasets and experiments', exact: true }).first().click();
  await expect(page.getByRole('heading', { name: 'Datasets and experiments' })).toBeVisible();
  await expect(page.getByRole('heading', { name: /POST.*datasets\/preview/ })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Schema models', exact: true })).toBeVisible();
  expect((await page.request.get(`${docs}/openapi.json`)).status()).toBe(200);
  await page.goto(`${docs}/docs/api/recipes/`);
  await expect(page.getByRole('heading', { name: 'API workflow recipes' })).toBeVisible();
  await expect(page.getByRole('img', { name: /API returns a project ID/ })).toBeVisible();
  expect((await page.request.get(`${docs}/img/api-workflow.svg`)).status()).toBe(200);
  await page.goto(`${docs}/docs/experiments/compare/`);
  await expect(page.getByRole('heading', { name: 'Compare two answer pipelines' })).toBeVisible();
  await expect(
    page.getByRole('img', { name: /same ready index feeds two saved answer versions/ }),
  ).toBeVisible();
  expect((await page.request.get(`${docs}/img/paired-comparison.svg`)).status()).toBe(200);
  expect((await page.request.get(`${docs}/examples/orchard-reviewed.csv`)).status()).toBe(200);
  await page.getByRole('textbox', { name: 'Search' }).fill('paired comparison');
  await expect(
    page.getByRole('option', { name: /Compare two answer pipelines/ }).first(),
  ).toBeVisible();
  await page.goto(`${docs}/docs/experiments/compare/`);
  await page.setViewportSize({ width: 720, height: 1000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByRole('main')).toBeVisible();
  await page.goto(`${docs}/docs/api/schema-models/`);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Toggle navigation bar' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'API' })).toBeVisible();
});

test('operator procedures, diagrams, screenshot alternatives and limits work on narrow screens', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`${docs}/docs/operate/deploy/`);
  await expect(page.getByRole('heading', { name: 'Deploy the local workspace' })).toBeVisible();
  await expect(page.getByRole('img', { name: /local API and worker share PostgreSQL/ })).toBeVisible();
  expect((await page.request.get(`${docs}/img/deploy-boundary.svg`)).status()).toBe(200);
  await page.goto(`${docs}/docs/operate/security/`);
  await expect(page.getByRole('heading', { name: 'Security and permissions' })).toBeVisible();
  await expect(page.getByRole('img', { name: /Local loopback requests and configured OIDC/ })).toBeVisible();
  await page.goto(`${docs}/docs/operate/backup-restore/`);
  await expect(page.getByRole('heading', { name: 'Back up and restore a workspace' })).toBeVisible();
  await expect(page.getByRole('img', { name: /Pause writers, capture PostgreSQL/ })).toBeVisible();
  await page.goto(`${docs}/docs/operate/operations/`);
  await expect(page.getByRole('heading', { name: 'Operate jobs and storage' })).toBeVisible();
  await expect(page.getByRole('img', { name: /Jobs move from queued to running/ })).toBeVisible();
  await page.goto(`${docs}/docs/operate/troubleshooting/`);
  await expect(page.getByRole('heading', { name: 'Troubleshoot a blocked workflow' })).toBeVisible();
  for (const image of ['17-provider-unavailable.png', '18-provider-unavailable-mobile.png']) {
    expect((await page.request.get(`${docs}/img/screenshots/${image}`)).status()).toBe(200);
  }
  expect(await page.locator('img:not([alt])').count()).toBe(0);
  await page.getByRole('textbox', { name: 'Search' }).fill('Back up and restore a workspace');
  await expect(page.getByRole('option', { name: /Back up and restore a workspace/ }).first()).toBeVisible();
  await page.goto(`${docs}/docs/reference/limits-faq/`);
  await expect(page.getByRole('heading', { name: 'Limits and FAQ' })).toBeVisible();
  await page.screenshot({ path: 'test-results/docs-operator-desktop.png' });
  await page.setViewportSize({ width: 720, height: 1000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Toggle navigation bar' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Operate' })).toBeVisible();
  await page.screenshot({ path: 'test-results/docs-operator-mobile.png' });
});
