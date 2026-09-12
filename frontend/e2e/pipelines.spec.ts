import { test, expect } from '@playwright/test';

test('pipeline kind tabs survive refresh and stay scoped to each project', async ({
  page,
  request,
}) => {
  const first = (await (
    await request.post('/api/projects', { data: { name: `Kinds A ${Date.now()}` } })
  ).json()) as { id: string };
  const second = (await (
    await request.post('/api/projects', { data: { name: `Kinds B ${Date.now()}` } })
  ).json()) as { id: string };

  await page.goto(`/#/projects/${first.id}/pipelines`);
  await expect(page.getByRole('tab', { name: 'Answer pipelines' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await page.getByRole('tab', { name: 'Ingestion pipelines' }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${first.id}/pipelines\\?kind=ingestion$`));
  await expect(page.getByRole('button', { name: 'New ingestion pipeline' })).toBeDisabled();
  await expect(page.getByText('Available when ingestion execution is implemented.')).toBeVisible();
  await expect(page.getByRole('button', { name: /run|preview|connector/i })).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole('tab', { name: 'Ingestion pipelines' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await page.getByLabel('Switch project').selectOption(second.id);
  await expect(page).toHaveURL(new RegExp(`/projects/${second.id}/pipelines$`));
  await expect(page.getByRole('tab', { name: 'Answer pipelines' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await page.getByLabel('Switch project').selectOption(first.id);
  await expect(page).toHaveURL(new RegExp(`/projects/${first.id}/pipelines\\?kind=ingestion$`));
});

test('pipeline create configure save reopen run evidence and immutable versions', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires isolated deterministic providers.',
  );
  test.setTimeout(120000);
  page.setDefaultTimeout(15000);
  const project = (await (
    await request.post('/api/projects', { data: { name: `Pipeline ${Date.now()}` } })
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
  await page.getByRole('link', { name: 'Pipelines', exact: true }).click();
  await page.getByRole('link', { name: 'New answer pipeline', exact: true }).click();
  await page.getByLabel('Pipeline name', { exact: true }).fill('Orchard answers');
  const questionBox = (await page.locator('.react-flow__node[data-id="question"]').boundingBox())!;
  const retrieverBox = (await page
    .locator('.react-flow__node[data-id="retriever"]')
    .boundingBox())!;
  expect(retrieverBox.y).toBeGreaterThan(questionBox.y);
  expect(Math.abs(retrieverBox.x - questionBox.x)).toBeLessThan(2);
  const retriever = page.locator('.react-flow__node[data-id="retriever"]');
  const box = (await retriever.boundingBox())!;
  await page.mouse.move(box.x + 15, box.y + 15);
  await page.mouse.down();
  await page.mouse.move(box.x + 35, box.y + 45, { steps: 8 });
  await page.mouse.up();
  await page
    .getByLabel('Documents to search', { exact: true })
    .selectOption({ label: 'Document set · Version 1 · 1 passages' });
  await page.getByLabel('Top k', { exact: true }).fill('3');
  await page.getByLabel('Selected node').selectOption('prompt');
  await page
    .getByLabel('Answer instructions')
    .fill('Answer concisely. Question: {question} Context: {context}');
  await page.getByRole('button', { name: 'Save version', exact: true }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Pipeline name', { exact: true })).toHaveValue('Orchard answers');
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Arrange vertically', exact: true }).click();
  await expect(page.getByText('Unsaved changes', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Discard changes', exact: true }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await page.getByLabel('Selected node').selectOption('prompt');
  await expect(page.getByLabel('Answer instructions')).toHaveValue(
    'Answer concisely. Question: {question} Context: {context}',
  );
  await page.getByRole('button', { name: 'Open Playground', exact: true }).click();
  const savedPlaygroundUrl = page.url();
  await page.getByRole('link', { name: 'Pipelines', exact: true }).click();
  await page.getByRole('link', { name: 'Playground', exact: true }).click();
  await expect(page).toHaveURL(savedPlaygroundUrl);
  await page.reload();
  await expect(page.locator('.playground-context')).toHaveText('Orchard answers · Version 1');
  await page.getByLabel('Question', { exact: true }).fill('What does the orchard grow?');
  await page.getByRole('button', { name: 'Run pipeline test', exact: true }).click();
  const result = page.getByRole('region', { name: 'Query result' });
  await expect(result.locator('.formatted-answer')).toHaveText('The orchard grows apples. [S1]', {
    timeout: 30000,
  });
  await result.getByRole('button', { name: '[S1]', exact: true }).click();
  await expect(page.locator('#evidence-S1')).toBeFocused();
  const composer = await page.locator('.playground-chat-composer').boundingBox();
  expect(composer!.y + composer!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  expect(composer!.y + composer!.height).toBeGreaterThan(page.viewportSize()!.height - 32);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await expect(result.getByText('Saved index', { exact: false })).toHaveCount(0);
  await page.getByRole('button', { name: 'Answer details', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Answer details' })).toContainText(
    'Pipeline version 1',
  );
  await page.getByRole('link', { name: 'Pipelines', exact: true }).click();
  await page.getByRole('link', { name: 'Open Orchard answers', exact: true }).click();
  await page.getByLabel('Selected node').selectOption('retriever');
  await page.getByLabel('Top k', { exact: true }).fill('1');
  await expect(page.getByRole('button', { name: 'Open Playground', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Save version', exact: true }).click();
  await expect(page.getByText('Saved version 2', { exact: true })).toBeVisible();
  await page.getByLabel('Saved version', { exact: true }).selectOption({ label: 'Version 1' });
  await page.getByLabel('Selected node').selectOption('retriever');
  await expect(page.getByLabel('Top k', { exact: true })).toHaveValue('3');
  await page.setViewportSize({ width: 1600, height: 1100 });
  await page.getByLabel('Selected node').selectOption('question');
  await page.getByLabel('Selected node').selectOption('retriever');
  await expect(
    page.locator('.react-flow__node[data-id="retriever"] .workflow-selected'),
  ).toBeVisible();
  const canvas = page.locator('.pipeline-canvas');
  const canvasBefore = (await canvas.boundingBox())!;
  expect(canvasBefore.height).toBeGreaterThan(660);
  await page.getByRole('button', { name: 'Hide settings', exact: true }).click();
  await expect(page.getByLabel('Selected node')).toBeHidden();
  expect((await canvas.boundingBox())!.width).toBeGreaterThan(canvasBefore.width + 250);
  await page.getByRole('button', { name: 'Node settings', exact: true }).click();
  await expect(page.getByLabel('Selected node')).toBeVisible();
  await page.screenshot({ path: 'test-results/pipeline-desktop.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel('Selected node').selectOption('question');
  await page.getByLabel('Selected node').selectOption('retriever');
  await page.locator('.pipeline-editor').screenshot({ path: 'test-results/pipeline-mobile.png' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Duplicate pipeline', exact: true }).click();
  await expect(page.getByLabel('Pipeline name', { exact: true })).toHaveValue(
    'Orchard answers (copy)',
  );
  await page.getByLabel('Selected node').selectOption('answer');
  await page.getByRole('button', { name: 'Delete selected node', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save version', exact: true })).toBeDisabled();
  await expect(page.getByRole('region', { name: 'Graph validation' })).toContainText(
    'Require exactly one',
  );
  await page.getByRole('button', { name: 'Nodes', exact: true }).click();
  await page.getByRole('button', { name: 'Add Answer', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Graph validation' })).toContainText(
    'Connect Question',
  );
  await page.getByRole('button', { name: 'Discard changes', exact: true }).click();
});
