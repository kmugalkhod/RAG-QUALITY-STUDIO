import { test, expect, type APIRequestContext } from '@playwright/test';

// Spec 0015 S1: add, configure, save, run and remove the optional Rerank step.
async function readyIndex(request: APIRequestContext, root: string) {
  for (const [name, text] of [
    ['orchard.txt', 'The orchard grows apples. The harvest begins in September.'],
    ['harbor.txt', 'Harbor Desk is open Monday through Friday from nine to five.'],
  ]) {
    const doc = await (
      await request.post(`${root}/documents`, {
        multipart: { file: { name, mimeType: 'text/plain', buffer: Buffer.from(text) } },
      })
    ).json();
    const run = await (
      await request.post(`${root}/documents/${doc.id}/runs`, {
        data: { chunk_size: 500, overlap: 0 },
      })
    ).json();
    await expect
      .poll(
        async () =>
          (await (await request.get(`${root}/documents/${doc.id}/runs/${run.id}`)).json()).status,
        { timeout: 40000 },
      )
      .toBe('succeeded');
  }
  const index = await (await request.post(`${root}/indexes`)).json();
  await expect
    .poll(async () => (await (await request.get(`${root}/indexes/${index.id}`)).json()).status, {
      timeout: 40000,
    })
    .toBe('succeeded');
  return index as { id: string };
}

test('rerank step is added, configured, saved, run with both ranks and removed', async ({
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
    await request.post('/api/projects', { data: { name: `Rerank ${Date.now()}` } })
  ).json();
  const root = `/api/projects/${project.id}`;
  const index = await readyIndex(request, root);
  const kinds = ['question', 'retriever', 'prompt', 'llm', 'answer'];
  const original = await (
    await request.post(`${root}/pipelines`, {
      data: {
        name: 'Reranked answers',
        execution: {
          schema_version: 2,
          nodes: [
            { id: 'question', type: 'question' },
            {
              id: 'retriever',
              type: 'retriever',
              index_id: index.id,
              retrieval: { mode: 'vector', top_k: 5 },
            },
            { id: 'prompt', type: 'prompt', template: 'Answer {question} using {context}' },
            { id: 'llm', type: 'llm', model: 'test/chat', max_tokens: 512, temperature: 0 },
            { id: 'answer', type: 'answer' },
          ],
          edges: kinds.slice(1).map((kind, i) => ({ source: kinds[i], target: kind })),
        },
        layout: {
          positions: Object.fromEntries(kinds.map((kind, i) => [kind, { x: 80, y: 40 + i * 116 }])),
        },
      },
    })
  ).json();
  const versions = `${root}/pipelines/${original.pipeline_id}/versions`;

  await page.goto(
    `/#/projects/${project.id}/pipelines/${original.pipeline_id}?version=${original.id}`,
  );
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await page.getByLabel('Selected node').selectOption('retriever');
  // Keyboard: the button is reachable and activates with Enter.
  const add = page.getByRole('button', { name: 'Add a rerank step', exact: true });
  await add.focus();
  await page.keyboard.press('Enter');
  const rerankCard = page.locator('.react-flow__node[data-id="rerank"]');
  await expect(rerankCard).toBeVisible();
  await expect(rerankCard).toContainText('Rerank');
  await expect(rerankCard).toContainText('Keeps 5 · test/chat');
  await expect(page.getByRole('heading', { name: 'Rerank', exact: true })).toBeVisible();
  await expect(page.getByLabel('Rerank model', { exact: true })).toHaveValue('test/chat');
  await page.getByLabel('Passages kept', { exact: true }).fill('2');
  await expect(rerankCard).toContainText('Keeps 2');
  // The step sits between Retriever and Prompt on the canvas.
  const retrieverBox = (await page
    .locator('.react-flow__node[data-id="retriever"]')
    .boundingBox())!;
  const rerankBox = (await rerankCard.boundingBox())!;
  const promptBox = (await page.locator('.react-flow__node[data-id="prompt"]').boundingBox())!;
  expect(rerankBox.y).toBeGreaterThan(retrieverBox.y);
  expect(promptBox.y).toBeGreaterThan(rerankBox.y);
  await page.getByLabel('Selected node').selectOption('retriever');
  await expect(page.getByLabel('Top k', { exact: true })).toHaveValue('30');
  await expect(page.getByText(/keeps the 2 most useful/)).toBeVisible();
  await expect(page.getByText('Unsaved changes', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Save version', exact: true }).click();
  await expect(page.getByText('Saved version 2', { exact: true })).toBeVisible();

  const saved = (await (await request.get(versions)).json()).items.find(
    (version: { version: number }) => version.version === 2,
  );
  expect(saved.execution.schema_version).toBe(3);
  expect(saved.execution.nodes[2]).toEqual({
    id: 'rerank',
    type: 'rerank',
    model: 'test/chat',
    top_n: 2,
  });

  await page.reload();
  await expect(page.getByText('Saved version 2', { exact: true })).toBeVisible();
  await page.getByLabel('Selected node').selectOption('rerank');
  await expect(page.getByLabel('Passages kept', { exact: true })).toHaveValue('2');

  await page.getByRole('button', { name: 'Open Playground', exact: true }).click();
  await expect(page.getByTestId('playground-context')).toHaveText('Reranked answers · Version 2');
  await page.getByLabel('Question', { exact: true }).fill('What does the orchard grow?');
  await page.getByRole('button', { name: 'Run pipeline test', exact: true }).click();
  const result = page.getByRole('region', { name: 'Query result' });
  await expect(result.locator('[data-slot="answer-text"]')).toHaveText(
    'The orchard grows apples. [S1]',
    { timeout: 30000 },
  );
  await result.getByRole('button', { name: '[S1]', exact: true }).click();
  // The test double reverses the retriever order: S1 was the retriever's second passage.
  await expect(page.locator('#evidence-S1')).toContainText('Rank 1 · Retriever rank 2');
  await expect(page.locator('#evidence-S2')).toContainText('Rank 2 · Retriever rank 1');
  await page.getByRole('button', { name: 'Answer details', exact: true }).click();
  const details = page.getByRole('region', { name: 'Answer details' });
  await expect(details).toContainText(
    'Rerank step · test/chat · ordered 2 of 2 candidates, kept 2',
  );
  await expect(details).toContainText('Reranking');
  await expect(details).toContainText('Rerank cost');

  await page.goto(
    `/#/projects/${project.id}/pipelines/${original.pipeline_id}?version=${saved.id}`,
  );
  await expect(page.getByText('Saved version 2', { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel('Selected node').selectOption('rerank');
  await expect(page.getByLabel('Rerank model', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/rerank-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole('button', { name: 'Remove rerank step', exact: true }).click();
  await expect(rerankCard).toHaveCount(0);
  await page.getByLabel('Selected node').selectOption('retriever');
  await expect(page.getByLabel('Top k', { exact: true })).toHaveValue('2');
  await expect(page.getByRole('button', { name: 'Add a rerank step', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Save version', exact: true }).click();
  await expect(page.getByText('Saved version 3', { exact: true })).toBeVisible();
  const removed = (await (await request.get(versions)).json()).items.find(
    (version: { version: number }) => version.version === 3,
  );
  expect(removed.execution.schema_version).toBe(2);
  expect(removed.execution.nodes.map((node: { type: string }) => node.type)).toEqual(kinds);
  await page.screenshot({ path: 'test-results/rerank-desktop.png' });
  expect(errors).toEqual([]);
});
