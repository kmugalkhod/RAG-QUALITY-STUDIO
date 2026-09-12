import { test, expect } from '@playwright/test';

test('reports missing embedding credentials without breaking document management', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE === '1',
    'This case uses the default credential-free stack.',
  );
  const project = (await (
    await request.post('/api/projects', { data: { name: `Index settings ${Date.now()}` } })
  ).json()) as { id: string };
  await page.goto(`/#/projects/${project.id}`);
  await page.getByRole('tab', { name: 'Document sets', exact: true }).click();
  await expect(page.getByText(/Set OPENROUTER_API_KEY/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Prepare document set' })).toBeDisabled();
  await page.getByRole('button', { name: 'Add document', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Upload document', exact: true })).toBeEnabled();
});

test('indexes and retrieves persisted source evidence using the isolated provider fixture', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires compose.index-e2e.yaml, never live provider calls.',
  );
  const project = (await (
    await request.post('/api/projects', { data: { name: `Index fixture ${Date.now()}` } })
  ).json()) as { id: string };
  await page.goto(`/#/projects/${project.id}`);
  await page.getByRole('button', { name: 'Add document', exact: true }).click();
  await page.getByLabel('PDF or UTF-8 TXT').setInputFiles({
    name: 'orchard.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('The orchard grows apples. The harvest begins in September.'),
  });
  await page.getByRole('button', { name: 'Upload document', exact: true }).click();
  await page.getByRole('button', { name: 'Start processing', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Inspect 1 chunks' })).toBeVisible({
    timeout: 30000,
  });
  await page.getByRole('tab', { name: 'Document sets', exact: true }).click();
  await page.getByRole('button', { name: 'Prepare document set' }).click();
  await expect(page.getByRole('button', { name: 'Use document set 1' })).toBeVisible({
    timeout: 30000,
  });
  await expect(page.getByRole('heading', { name: 'Uploaded documents' })).toBeVisible();
  await expect(page.getByText('Current', { exact: true })).toBeVisible();
  await expect(page.getByText(/prepared from 1 processing run/)).toBeVisible();
  await page.reload();
  await expect(page.getByRole('tab', { name: 'Document sets', exact: true })).toHaveAttribute(
    'data-state',
    'active',
  );
  await page.getByRole('button', { name: 'Use document set 1' }).click();
  await page.getByLabel('Search query').fill('What does the orchard grow?');
  await page.getByRole('button', { name: 'Search documents only', exact: true }).click();
  const results = page.getByRole('region', { name: 'Retrieval results' });
  await expect(
    results.getByText('The orchard grows apples. The harvest begins in September.', {
      exact: true,
    }),
  ).toBeVisible();
  await expect(results.getByText(/Cosine distance 0.0000/)).toBeVisible();
  await expect(results.getByText(/1 passages from document set version 1/)).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .getByRole('heading', { name: 'Prepare documents for questions' })
    .scrollIntoViewIfNeeded();
  await page
    .getByRole('region', { name: 'Prepare documents for questions' })
    .screenshot({ path: 'test-results/index-desktop.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole('heading', { name: 'Prepare documents for questions' })
    .scrollIntoViewIfNeeded();
  await page
    .getByRole('region', { name: 'Prepare documents for questions' })
    .screenshot({ path: 'test-results/index-mobile.png' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});
