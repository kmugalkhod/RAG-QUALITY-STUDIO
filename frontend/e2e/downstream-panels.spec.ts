import { expect, test } from '@playwright/test';

// Spec 0012 Slice 4: the simplified Clean, Chunk, Embed and Publish panels against the
// isolated stack with deterministic providers (compose.e2e.yaml + compose.index-e2e.yaml).
test('edits Clean, Chunk and Publish, then saves, previews and publishes', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires isolated deterministic providers.',
  );
  test.setTimeout(240000);
  const errors: string[] = [];
  page.on('console', (message) => message.type() === 'error' && errors.push(message.text()));
  page.on('pageerror', (error) => errors.push(error.message));
  const project = (await (
    await request.post('/api/projects', { data: { name: `Downstream panels ${Date.now()}` } })
  ).json()) as { id: string };

  await page.goto(`/#/projects/${project.id}/pipelines/new?kind=ingestion`);
  await page.getByLabel('Pipeline name').fill('Controlled docs');
  await page.getByLabel('Source type').selectOption('website');
  await page.getByLabel('Start URL').fill('https://controlled.example/');

  // Clean: text to remove keeps its spaces; Advanced says recommended.
  await page.getByLabel('Selected stage').selectOption({ label: 'Clean' });
  await expect(
    page.getByText(/Removes website menus, cookie banners and repeated page headers/),
  ).toBeVisible();
  await page.getByLabel('Text to remove').fill('Skip to content \nFooter');
  await expect(page.getByLabel('Text to remove')).toHaveValue('Skip to content \nFooter');
  await expect(page.getByLabel(/Redact emails, phone numbers and IDs/)).toBeChecked();
  await expect(page.getByText('· recommended')).toBeVisible();
  await page.locator('#node-settings').screenshot({ path: 'test-results/downstream-clean.png' });

  // Chunk: a smaller passage size; Advanced shows the exact bytes.
  await page.getByLabel('Selected stage').selectOption({ label: 'Chunk' });
  await page.getByRole('radio', { name: /Small/ }).click();
  await page.getByText('Advanced chunking settings').click();
  await expect(page.getByLabel('Target size (bytes)')).toHaveValue('300');
  await page.getByLabel('Overlap (bytes)').fill('');
  await expect(page.getByLabel('Overlap (bytes)')).toHaveAccessibleDescription(
    'Enter a whole number.',
  );
  await expect(page.getByRole('button', { name: 'Save version', exact: true })).toBeDisabled();
  await page.getByLabel('Overlap (bytes)').fill('40');
  await page.locator('#node-settings').screenshot({ path: 'test-results/downstream-chunk.png' });

  // Publish: the index follows the pipeline name and says what the run publishes.
  await page.getByLabel('Selected stage').selectOption({ label: 'Publish index' });
  await expect(page.getByLabel('Index name')).toHaveValue('Controlled docs');
  await expect(
    page.getByText('This run publishes version 1 of the new index Controlled docs.'),
  ).toBeVisible();
  await page.locator('#node-settings').screenshot({ path: 'test-results/downstream-publish.png' });

  await page.getByRole('button', { name: 'Save version', exact: true }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();

  // Preview from the Chunk panel; Embed estimates the run.
  await page.getByLabel('Selected stage').selectOption({ label: 'Chunk' });
  await page.getByRole('button', { name: 'Preview chunks' }).click();
  await expect(page.getByText(/passages? · median \d+ bytes/).first()).toBeVisible({
    timeout: 30000,
  });
  await page.getByLabel('Selected stage').selectOption({ label: 'Embed' });
  await expect(page.getByText(/set by the server\./)).toBeVisible();
  await expect(
    page.getByText(/estimated (under )?\$[\d.]+ \(list price, estimate\)/),
  ).toBeVisible();

  await page.getByRole('button', { name: 'Collect source & publish index' }).click();
  await expect(
    page.locator('[data-testid="ingestion-run-state"][data-status="succeeded"]'),
  ).toBeVisible({ timeout: 60000 });
  await expect(page.getByText(/^Last run: \d+ new, 0 reused, cost /)).toBeVisible();

  for (const scheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({
      path: `test-results/downstream-${scheme}-desktop.png`,
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `test-results/downstream-${scheme}-phone.png`, fullPage: true });
  }
  expect(errors).toEqual([]);
});
