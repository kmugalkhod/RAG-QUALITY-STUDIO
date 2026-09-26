import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';

const orchard = readFileSync('../docs/site/static/examples/orchard.txt');
const reviewed = readFileSync('../docs/site/static/examples/orchard-reviewed.csv');
const screenshots = '../docs/site/static/img/screenshots';

test('documentation T4: compare two saved versions on reviewed fictional questions', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_EMBEDDING_FIXTURE !== '1',
    'Requires the isolated deterministic answer/evaluator provider stack.',
  );
  test.setTimeout(210000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const project = (await (
    await request.post('/api/projects', { data: { name: `Docs comparison ${Date.now()}` } })
  ).json()) as { id: string };
  await page.goto(`/#/projects/${project.id}/knowledge-base`);
  await page.getByRole('button', { name: 'Add document', exact: true }).click();
  await page
    .getByLabel('Document file')
    .setInputFiles({ name: 'orchard.txt', mimeType: 'text/plain', buffer: orchard });
  await page.getByRole('button', { name: 'Upload document', exact: true }).click();
  await page.getByRole('button', { name: 'Start processing', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Inspect 1 chunks' })).toBeVisible({
    timeout: 30000,
  });
  await page.getByRole('tab', { name: 'Collections', exact: true }).click();
  await page.getByRole('button', { name: 'Publish prepared documents' }).click();
  await expect(
    page.getByRole('button', { name: 'Open Uploaded documents collection' }),
  ).toBeVisible({
    timeout: 60000,
  });
  await page.getByRole('button', { name: 'Open Uploaded documents collection' }).click();
  await page.getByRole('link', { name: /Use version \d+ in a pipeline/ }).click();
  await page.getByLabel('Pipeline name').fill('Orchard comparison');
  await page.getByLabel('Selected node').selectOption('retriever');
  await page.getByLabel('Top k', { exact: true }).fill('1');
  await page.getByRole('button', { name: 'Save version', exact: true }).click();
  await expect(page.getByText('Saved version 1', { exact: true })).toBeVisible();
  await page.getByLabel('Selected node').selectOption('retriever');
  await page.getByLabel('Top k', { exact: true }).fill('2');
  await page.getByRole('button', { name: 'Save version', exact: true }).click();
  await expect(page.getByText('Saved version 2', { exact: true })).toBeVisible();

  await page.getByRole('link', { name: 'Experiments', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Dataset import guide' })).toHaveAttribute(
    'href',
    'http://127.0.0.1:3000/docs/experiments/datasets/',
  );
  await page.getByLabel('Dataset name', { exact: true }).fill('Reviewed orchard');
  await page
    .getByLabel('CSV file')
    .setInputFiles({ name: 'orchard-reviewed.csv', mimeType: 'text/csv', buffer: reviewed });
  await page.getByRole('button', { name: 'Preview CSV', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Preview · 2 questions' })).toBeVisible();
  await expect(page.getByLabel('Dataset questions')).toContainText('What is the launch code?');
  await page
    .locator('.dataset-preview')
    .screenshot({ path: `${screenshots}/13-reviewed-dataset.png` });
  await page.getByRole('button', { name: 'Import reviewed dataset' }).click();
  await expect(
    page.getByText('Imported Reviewed orchard version 1.', { exact: true }),
  ).toBeVisible();
  await page.getByLabel('Experiment name', { exact: true }).fill('Orchard paired run');
  await page
    .getByRole('combobox', { name: 'Candidate A', exact: true })
    .selectOption({ label: 'Orchard comparison · v1' });
  await page
    .getByRole('combobox', { name: 'Candidate B (optional)', exact: true })
    .selectOption({ label: 'Orchard comparison · v2' });
  await expect(page.getByRole('link', { name: 'Experiment run guide' })).toHaveAttribute(
    'href',
    'http://127.0.0.1:3000/docs/experiments/runs/',
  );
  const options = page.getByRole('group', { name: 'Evaluation metrics' });
  for (const name of ['Faithfulness', 'Response relevancy', 'Context recall']) {
    await expect(options.getByRole('checkbox', { name: new RegExp(name) })).toBeChecked();
  }
  await page.getByRole('button', { name: 'Run experiment', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Orchard paired run' })).toBeVisible();
  await expect(page.getByRole('status')).toContainText('succeeded 4 / 4 results completed', {
    timeout: 150000,
  });
  await expect(page.getByRole('heading', { name: 'Paired comparison' })).toBeVisible();
  const summaries = page.locator('.experiment-section').filter({
    has: page.getByRole('heading', { name: 'Candidate summaries' }),
  });
  await expect(summaries).toContainText('unavailable');
  await expect(page.getByRole('link', { name: 'Interpret metrics and costs' })).toHaveAttribute(
    'href',
    'http://127.0.0.1:3000/docs/experiments/metrics/',
  );
  await summaries.screenshot({ path: `${screenshots}/14-candidate-summary.png` });
  const paired = page.locator('.experiment-section').filter({
    has: page.getByRole('heading', { name: 'Paired comparison' }),
  });
  await expect(paired).toContainText('Shared sample');
  await paired.screenshot({ path: `${screenshots}/15-paired-comparison.png` });
  const questions = page.locator('.experiment-section').filter({
    has: page.getByRole('heading', { name: 'Per-question comparison' }),
  });
  await expect(questions).toContainText('Insufficient evidence');
  await questions.screenshot({ path: `${screenshots}/16-question-comparison.png` });
  await page.getByRole('button', { name: 'What does the orchard grow?', exact: true }).click();
  const evidence = page.getByRole('region', { name: 'Question evidence' });
  await expect(evidence.getByText('The orchard grows apples. [S1]', { exact: true })).toHaveCount(
    2,
  );
  await expect(evidence).toContainText('The fictional orchard grows apples.');
  await expect(page.getByRole('link', { name: 'Interpret and improve results' })).toHaveAttribute(
    'href',
    'http://127.0.0.1:3000/docs/experiments/interpret/',
  );
  const experiment = (await (
    await request.get(`/api/projects/${project.id}/experiments/${page.url().split('/').at(-1)}`)
  ).json()) as {
    snapshot: { candidates: { index_id: string }[] };
    summary: { paired: Record<string, { count: number; b_minus_a: number | null }> };
  };
  expect(experiment.snapshot.candidates[0].index_id).toBe(
    experiment.snapshot.candidates[1].index_id,
  );
  expect(experiment.summary.paired.context_recall.count).toBe(1);
  expect(experiment.summary.paired.context_recall.b_minus_a).toBe(0);
  const download = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Export CSV' }).click();
  expect((await download).suggestedFilename()).toContain('.csv');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Orchard paired run' })).toBeVisible();
});
