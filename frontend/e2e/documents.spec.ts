import { test, expect } from '@playwright/test';

test('uploads, processes, inspects and revisits a versioned document', async ({ page }) => {
  const name = `Knowledge verification ${Date.now()}`;
  await page.goto('/');
  await page.getByRole('button', { name: 'New project', exact: true }).click();
  await page.getByLabel('Project name').fill(name);
  await page.getByRole('button', { name: 'Create project', exact: true }).click();
  await page.getByRole('link', { name, exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Knowledge Base' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'No documents yet' })).toBeVisible();
  await page.getByLabel('PDF or UTF-8 TXT').setInputFiles({ name: 'knowledge.txt', mimeType: 'text/plain', buffer: Buffer.from('A source document with evidence. '.repeat(50)) });
  await page.getByRole('button', { name: 'Upload document', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Process: knowledge.txt' })).toBeVisible();
  await page.getByLabel('Chunk size (characters)').fill('40');
  await page.getByLabel('Overlap (characters)').fill('40');
  await page.getByRole('button', { name: 'Start processing', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('smaller than chunk size');
  await page.getByLabel('Overlap (characters)').fill('8');
  await page.getByRole('button', { name: 'Start processing', exact: true }).click();
  const inspect = page.getByRole('button', { name: /Inspect \d+ chunks/ }).first();
  await expect(inspect).toBeVisible({ timeout: 30000 });
  await inspect.click();
  await expect(page.getByRole('heading', { name: 'Chunks · Version 1' })).toBeVisible();
  await expect(page.getByText('Chunk 1 · TXT source · characters 0–40 (end exclusive)', { exact: true })).toBeVisible();
  await page.getByRole('navigation', { name: 'Chunk pages' }).getByRole('button', { name: 'Next' }).click();
  await expect(page.getByText(/Chunk 21 · TXT source/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Chunks · Version 1' })).toBeFocused();
  await page.reload();
  await page.getByRole('button', { name: 'Manage knowledge.txt' }).click();
  await page.getByRole('button', { name: /Inspect \d+ chunks/ }).click();
  await expect(page.getByText('Chunk 1 · TXT source · characters 0–40 (end exclusive)', { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: 'test-results/knowledge-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'test-results/knowledge-mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('shows parsing failure and allows a new processing version', async ({ page, request }) => {
  const project = await (await request.post('/api/projects', { data: { name: `Failure verification ${Date.now()}` } })).json() as { id: string };
  await page.goto(`/#/projects/${project.id}`);
  await page.getByLabel('PDF or UTF-8 TXT').setInputFiles({ name: 'broken.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.7\ninvalid PDF') });
  await page.getByRole('button', { name: 'Upload document', exact: true }).click();
  await page.getByRole('button', { name: 'Start processing', exact: true }).click();
  await expect(page.getByText('PDF could not be parsed. Upload a valid, unencrypted text-based PDF.').last()).toBeVisible({ timeout: 30000 });
  await page.getByRole('button', { name: 'Start processing', exact: true }).click();
  await expect(page.getByRole('heading', { name: /Version 2/ })).toBeVisible();
});

test('processes a text PDF and displays its page provenance', async ({ page, request }) => {
  const project = await (await request.post('/api/projects', { data: { name: `PDF verification ${Date.now()}` } })).json() as { id: string };
  await page.goto(`/#/projects/${project.id}`);
  await page.getByLabel('PDF or UTF-8 TXT').setInputFiles('e2e/fixtures/text.pdf');
  await page.getByRole('button', { name: 'Upload document', exact: true }).click();
  await page.getByRole('button', { name: 'Start processing', exact: true }).click();
  const inspect = page.getByRole('button', { name: 'Inspect 2 chunks' });
  await expect(inspect).toBeVisible({ timeout: 30000 });
  await inspect.click();
  await expect(page.getByText('First page evidence', { exact: true })).toBeVisible();
  await expect(page.getByText(/Chunk 2 · PDF page 2/)).toBeVisible();
});
