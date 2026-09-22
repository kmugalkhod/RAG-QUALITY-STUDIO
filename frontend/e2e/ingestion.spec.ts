import { expect, test } from '@playwright/test';

test('website discovery publishes and incrementally refreshes an exact index', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires isolated deterministic providers.',
  );
  test.setTimeout(240000);
  const project = (await (
    await request.post('/api/projects', {
      data: { name: `Website preview ${Date.now()}` },
    })
  ).json()) as { id: string };

  await page.goto(`/#/projects/${project.id}/pipelines/new?kind=ingestion`);
  await page.getByLabel('Pipeline name').fill('Controlled website preview');
  await page.getByLabel('Source type').selectOption('website');
  await page.getByLabel('Starting URL').fill('https://controlled.example/');
  await page.getByLabel('Allowed origins (one per line)').fill('https://controlled.example');
  await page.getByRole('button', { name: 'Preview source' }).click();

  await expect(page.getByRole('heading', { name: '2 included · 2 excluded' })).toBeVisible({
    timeout: 30000,
  });
  await expect(page.getByText(/1 duplicate · 0 failed/)).toBeVisible();
  await expect(
    page
      .getByRole('listitem')
      .filter({ hasText: 'https://controlled.example/guide' })
      .filter({ hasText: 'included · HTML page is within scope' }),
  ).toContainText('https://controlled.example/guide');
  await expect(page.getByText(/robots.txt disallows this URL/)).toBeVisible();

  await page.getByRole('button', { name: 'Save version' }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Collect latest source & build index' }).click();
  await expect(page.getByRole('heading', { name: 'Ingested knowledge · succeeded' })).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByText('2 new · 0 changed · 0 unchanged · 0 removed')).toBeVisible();
  await expect(page.getByText(/new · succeeded/)).toHaveCount(2);
  await expect(page.getByRole('link', { name: 'Inspect published index v1' })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: 'test-results/website-preview-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/website-preview-mobile.png', fullPage: true });

  const snapshots = await (
    await request.get(`/api/projects/${project.id}/source-snapshots`)
  ).json();
  expect(snapshots.items).toHaveLength(1);
  const pipeline = await (
    await request.get(`/api/projects/${project.id}/pipelines?kind=ingestion`)
  ).json();
  const versions = await (
    await request.get(`/api/projects/${project.id}/pipelines/${pipeline.items[0].id}/versions`)
  ).json();
  const preciseDraft = structuredClone(versions.items[0]);
  delete preciseDraft.id;
  delete preciseDraft.pipeline_id;
  delete preciseDraft.project_id;
  delete preciseDraft.version;
  delete preciseDraft.created_at;
  preciseDraft.kind = 'ingestion';
  preciseDraft.name = 'Controlled website precise';
  const chunk = preciseDraft.execution.nodes.find(
    (node: { type: string }) => node.type === 'chunk',
  );
  chunk.size = 600;
  chunk.overlap = 80;
  const precise = await (
    await request.post(`/api/projects/${project.id}/pipelines/${pipeline.items[0].id}/versions`, {
      data: preciseDraft,
    })
  ).json();
  const variant = await (
    await request.post(
      `/api/projects/${project.id}/pipelines/${pipeline.items[0].id}/versions/${precise.id}/ingestion-runs`,
      {
        data: {
          source_input: { kind: 'snapshot', source_snapshot_id: snapshots.items[0].id },
          destination: { kind: 'new', name: 'Precise website' },
        },
      },
    )
  ).json();
  let variantStatus = variant;
  for (
    let attempt = 0;
    attempt < 60 && !['succeeded', 'failed'].includes(variantStatus.status);
    attempt += 1
  ) {
    await page.waitForTimeout(500);
    variantStatus = await (
      await request.get(`/api/projects/${project.id}/ingestion-runs/${variant.id}`)
    ).json();
  }
  expect(variantStatus.status).toBe('succeeded');

  await page.goto(
    `/#/projects/${project.id}/knowledge-base?view=indexes&mode=snapshots&snapshot=${snapshots.items[0].id}`,
  );
  await expect(page.getByRole('heading', { name: 'Snapshot 1' })).toBeVisible();
  await expect(page.getByText('Ingested knowledge · v1')).toBeVisible();
  await expect(page.getByText('Precise website · v1')).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByRole('button', { name: 'Back to snapshots' })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });

  const indexes = (await (await request.get(`/api/projects/${project.id}/indexes`)).json()).items;
  const answerVersions: string[] = [];
  for (const [position, index] of indexes.entries()) {
    const nodes = [
      { id: 'q', type: 'question' },
      { id: 'r', type: 'retriever', index_id: index.id, top_k: position + 1 },
      { id: 'p', type: 'prompt', template: '{question} {context}' },
      { id: 'l', type: 'llm', model: 'test/chat', temperature: 0, max_tokens: 512 },
      { id: 'a', type: 'answer' },
    ];
    const saved = await (
      await request.post(`/api/projects/${project.id}/pipelines`, {
        data: {
          name: `Website candidate ${position + 1}`,
          execution: {
            schema_version: 1,
            nodes,
            edges: nodes.slice(1).map((node, i) => ({ source: nodes[i].id, target: node.id })),
          },
          layout: {
            positions: Object.fromEntries(nodes.map((node, i) => [node.id, { x: 0, y: i * 120 }])),
          },
        },
      })
    ).json();
    answerVersions.push(saved.id);
  }
  await page.goto(`/#/projects/${project.id}/experiments`);
  await page.getByLabel('Dataset name', { exact: true }).fill('Website snapshot questions');
  await page.getByLabel('CSV file').setInputFiles({
    name: 'website.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(
      'question,reference_answer\nWhat does the controlled guide document?,The controlled guide documents solar orchards.\n',
    ),
  });
  await page.getByRole('button', { name: 'Preview CSV' }).click();
  await page.getByRole('button', { name: 'Import reviewed dataset' }).click();
  await page.getByLabel('Experiment name').fill('Same snapshot variants');
  await page.getByLabel('Candidate A').selectOption(answerVersions[0]);
  await page.getByLabel('Candidate B (optional)').selectOption(answerVersions[1]);
  await expect(page.getByText(/Same source snapshot/)).toBeVisible();
  await page.getByRole('button', { name: 'Run experiment' }).click();
  await expect(page.getByRole('status')).toContainText('succeeded 2 / 2 results completed', {
    timeout: 120000,
  });
  await expect(page.getByText(/Same source snapshot/)).toBeVisible();
});

test('existing files publish an exact index that grounds an answer pipeline', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires isolated deterministic providers.',
  );
  test.setTimeout(120000);
  page.setDefaultTimeout(20000);
  const project = (await (
    await request.post('/api/projects', {
      data: { name: `Existing files ingestion ${Date.now()}` },
    })
  ).json()) as { id: string };

  await page.goto(`/#/projects/${project.id}/knowledge-base`);
  for (const [name, content] of [
    ['orchard.txt', 'The orchard grows apples. The harvest begins in September.'],
    ['packing.txt', 'Apples are packed in recycled paper boxes.'],
  ]) {
    await page.getByRole('button', { name: 'Add document', exact: true }).click();
    await page.getByLabel('PDF or UTF-8 TXT').setInputFiles({
      name,
      mimeType: 'text/plain',
      buffer: Buffer.from(content),
    });
    await page.getByRole('button', { name: 'Upload document', exact: true }).click();
    await page.getByRole('button', { name: 'Start processing', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Inspect 1 chunks' })).toBeVisible({
      timeout: 30000,
    });
  }

  await page.getByRole('link', { name: 'Pipelines', exact: true }).click();
  await page.getByRole('tab', { name: 'Ingestion pipelines' }).click();
  await page.getByRole('link', { name: 'New ingestion pipeline' }).click();
  await expect(page.getByRole('heading', { name: 'Ingestion editor' })).toBeVisible();
  await page.getByLabel('Pipeline name').fill('Project files ingestion');
  await page.getByText('orchard.txt', { exact: true }).click();
  await page.getByText('packing.txt', { exact: true }).click();
  await page.getByRole('button', { name: 'Preview source' }).click();
  await expect(page.getByRole('heading', { name: '2 included · 0 excluded' })).toBeVisible({
    timeout: 30000,
  });
  await page.getByRole('button', { name: 'Save version' }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Run saved version' }).click();
  await expect(page.getByRole('heading', { name: 'Ingested knowledge · succeeded' })).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByText(/processing v2 · 1 chunks/)).toHaveCount(2);
  await expect(page.getByRole('link', { name: /Inspect published index v1/ })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: 'test-results/ingestion-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/ingestion-mobile.png', fullPage: true });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('link', { name: 'Pipelines', exact: true }).click();
  await page.getByRole('tab', { name: 'Answer pipelines' }).click();
  await page.getByRole('link', { name: 'New answer pipeline' }).click();
  await page
    .getByLabel('Documents to search', { exact: true })
    .selectOption({ label: 'Ingested knowledge · Version 1 · 2 passages' });
  await page.getByRole('button', { name: 'Save version' }).click();
  await page.getByRole('button', { name: 'Open Playground' }).click();
  await page.getByLabel('Question', { exact: true }).fill('What does the orchard grow?');
  await page.getByRole('button', { name: 'Run pipeline test', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Query result' })).toContainText(
    'The orchard grows apples. [S1]',
    { timeout: 30000 },
  );
});
