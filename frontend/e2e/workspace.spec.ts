import { test, expect } from '@playwright/test';

test('project navigation, isolated state, direct links, history and mobile tab bar', async ({
  page,
  request,
}) => {
  const a = (await (
    await request.post('/api/projects', { data: { name: `Workspace A ${Date.now()}` } })
  ).json()) as { id: string; name: string };
  const b = (await (
    await request.post('/api/projects', { data: { name: `Workspace B ${Date.now()}` } })
  ).json()) as { id: string; name: string };
  await page.goto(`/#/projects/${a.id}/overview`);
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Overview', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await page.getByRole('link', { name: 'Knowledge Base', exact: true }).click();
  await page.getByRole('button', { name: 'Add document', exact: true }).click();
  await page.getByLabel('Document file').setInputFiles({
    name: 'only-project-a.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('Project A evidence.'),
  });
  await page.getByRole('button', { name: 'Upload document', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Process: only-project-a.txt' })).toBeVisible();
  await page.getByLabel('Switch project').selectOption(b.id);
  await expect(page.getByRole('heading', { name: 'No documents yet' })).toBeVisible();
  await expect(page.getByText('only-project-a.txt', { exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'No documents yet' })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole('button', { name: 'only-project-a.txt', exact: true })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole('heading', { name: 'No documents yet' })).toBeVisible();
  await page.getByRole('link', { name: 'Pipelines', exact: true }).click();
  await page.getByRole('link', { name: 'New answer pipeline', exact: true }).click();
  await expect(page.getByText('Unsaved changes', { exact: true })).toBeVisible();
  page.once('dialog', (d) => d.dismiss());
  await page.getByRole('link', { name: 'Overview', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Pipeline editor', exact: true })).toBeVisible();
  page.once('dialog', (d) => d.dismiss());
  await page.goBack();
  await expect(page.getByRole('heading', { name: 'Pipeline editor', exact: true })).toBeVisible();
  page.once('dialog', (d) => d.accept());
  await page.getByRole('link', { name: 'Overview', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: 'test-results/workspace-desktop.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  const tabs = page.getByRole('navigation', { name: 'Project sections' });
  await tabs.getByRole('button', { name: 'More' }).click();
  await page.screenshot({ path: 'test-results/workspace-mobile-navigation.png' });
  await page.getByRole('link', { name: 'Settings', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
  await expect(
    page.getByText('PDF, TXT, Markdown, HTML, DOCX, PPTX, CSV, TSV, and XLSX'),
  ).toBeVisible();
  await expect(
    page.getByText(/Document preparation uses versioned character chunks/),
  ).toBeVisible();
  await expect(tabs.getByRole('button', { name: 'More' })).toHaveAttribute('aria-current', 'page');
  await page.screenshot({ path: 'test-results/settings-mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await tabs.getByRole('link', { name: 'Knowledge', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Knowledge Base', exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
});
