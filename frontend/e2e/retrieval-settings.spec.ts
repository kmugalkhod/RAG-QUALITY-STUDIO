import { test, expect } from '@playwright/test';

test('legacy pipeline upgrades to hybrid, persists all six settings and tests keyword retrieval', async ({ page, request }) => {
  test.skip(process.env.E2E_EMBEDDING_FIXTURE !== '1', 'Requires isolated deterministic providers.');
  test.setTimeout(120000);
  page.setDefaultTimeout(15000);
  const project = await (await request.post('/api/projects', { data: { name: `Retrieval settings ${Date.now()}` } })).json();
  const root = `/api/projects/${project.id}`;
  const doc = await (await request.post(`${root}/documents`, { multipart: { file: { name: 'orchard.txt', mimeType: 'text/plain', buffer: Buffer.from('The orchard grows apples. The harvest begins in September.') } } })).json();
  const processing = await (await request.post(`${root}/documents/${doc.id}/runs`, { data: { chunk_size: 500, overlap: 0 } })).json();
  await expect.poll(async () => (await (await request.get(`${root}/documents/${doc.id}/runs/${processing.id}`)).json()).status, { timeout: 40000 }).toBe('succeeded');
  const index = await (await request.post(`${root}/indexes`)).json();
  await expect.poll(async () => (await (await request.get(`${root}/indexes/${index.id}`)).json()).status, { timeout: 40000 }).toBe('succeeded');
  const kinds = ['question', 'retriever', 'prompt', 'llm', 'answer'];
  const original = await (await request.post(`${root}/pipelines`, { data: {
    name: 'Retrieval behavior', execution: { schema_version: 1,
      nodes: [{ id: 'question', type: 'question' }, { id: 'retriever', type: 'retriever', index_id: index.id, top_k: 5 }, { id: 'prompt', type: 'prompt', template: 'Answer {question} using {context}' }, { id: 'llm', type: 'llm', model: 'test/chat', max_tokens: 512, temperature: 0 }, { id: 'answer', type: 'answer' }],
      edges: kinds.slice(1).map((kind, i) => ({ source: kinds[i], target: kind })) },
    layout: { positions: Object.fromEntries(kinds.map((kind, i) => [kind, { x: 80, y: 40 + i * 116 }])) },
  } })).json();
  await page.goto(`/#/projects/${project.id}/pipelines/${original.pipeline_id}?version=${original.id}`);
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await expect(page.getByText('Unsaved changes', { exact: true })).toHaveCount(0);
  await page.getByLabel('Selected node').selectOption('retriever');
  await page.getByLabel('Search method').selectOption('hybrid');
  await page.getByLabel('Top k', { exact: true }).fill('3');
  await page.getByText('Advanced search settings', { exact: true }).click();
  await page.getByLabel('Maximum vector distance (optional)').fill('0.8');
  await page.getByLabel('Vector candidate count').fill('30');
  await page.getByLabel('Keyword candidate count').fill('40');
  await page.getByLabel('Vector weight', { exact: true }).fill('0.7');
  await page.getByRole('button', { name: 'Save version', exact: true }).click();
  await expect(page.getByText('Saved version 2', { exact: true })).toBeVisible();
  await page.reload();
  await page.getByLabel('Selected node').selectOption('retriever');
  await expect(page.getByLabel('Search method')).toHaveValue('hybrid');
  await page.getByText('Advanced search settings', { exact: true }).click();
  await expect(page.getByLabel('Vector candidate count')).toHaveValue('30');
  await expect(page.getByLabel('Keyword candidate count')).toHaveValue('40');
  await expect(page.getByLabel('Vector weight', { exact: true })).toHaveValue('0.7');
  await expect(page.getByLabel('Maximum vector distance (optional)')).toHaveValue('0.8');
  await page.screenshot({ path: 'test-results/retrieval-settings-desktop.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('.pipeline-config').screenshot({ path: 'test-results/retrieval-settings-mobile.png' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: 'Open Playground', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Playground', exact: true })).toBeVisible();
  await expect(page.getByLabel('Search method')).toHaveValue('hybrid');
  // Preview a keyword draft, then verify the persisted run used keyword settings.
  await page.getByLabel('Search method').selectOption('keyword');
  await expect(page.getByText('Test draft · changes are not saved', { exact: true })).toBeVisible();
  await page.getByLabel('Question', { exact: true }).fill('apples');
  const previewResponse = page.waitForResponse(r => r.url().endsWith('/preview-runs') && r.request().method() === 'POST', { timeout: 15000 });
  await page.getByRole('button', { name: 'Run pipeline test', exact: true }).click();
  const preview = await (await previewResponse).json();
  await expect.poll(async () => (await (await request.get(`${root}/query-runs/${preview.id}`)).json()).status).toBe('succeeded');
  const run = await (await request.get(`${root}/query-runs/${preview.id}`)).json();
  expect(run.snapshot.retrieval).toEqual({ mode: 'keyword', top_k: 3 });
  expect(run.snapshot.evidence[0].cosine_distance).toBeNull();
  expect(run.snapshot.evidence[0].lexical_score).toBeGreaterThan(0);
  expect((await (await request.get(`${root}/pipelines/${original.pipeline_id}/versions/${original.id}`)).json()).execution).toEqual(original.execution);
  await page.getByRole('button', { name: 'Retrieval test', exact: true }).click();
  await page.getByRole('combobox', { name: 'Documents to search', exact: true }).selectOption(index.id);
  await page.getByLabel('Search method').selectOption('keyword');
  await page.getByLabel('Search query', { exact: true }).fill('apples');
  await page.getByRole('button', { name: 'Run retrieval test', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Retrieval test results' })).toContainText('Keyword score');
});
