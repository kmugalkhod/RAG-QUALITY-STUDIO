import { expect, test } from '@playwright/test';

test('local vault redacts, tests, rotates and re-encrypts a source connection', async ({
  page,
  request,
}) => {
  const project = (await (
    await request.post('/api/projects', {
      data: { name: `Encrypted connections ${Date.now()}` },
    })
  ).json()) as { id: string };
  const firstAccess = 'AKIA-BROWSER-1234';
  const firstSecret = 'browser-private-secret-one';
  const rotatedAccess = 'AKIA-BROWSER-5678';
  const rotatedSecret = 'browser-private-secret-two';
  const responseBodies: string[] = [];
  page.on('response', async (response) => {
    if (response.url().includes('/source-connections')) {
      responseBodies.push(await response.text().catch(() => ''));
    }
  });

  await page.goto(`/#/projects/${project.id}/settings`);
  await expect(page.getByRole('heading', { name: 'Source connections' })).toBeVisible();
  await page.getByRole('button', { name: 'Add connection' }).click();
  await page.getByLabel('Connection name').fill('Research archive');
  await page.getByLabel('Access key ID').fill(firstAccess);
  await page.getByLabel('Secret access key').fill(firstSecret);
  await page.getByRole('button', { name: 'Save encrypted connection' }).click();

  await expect(page.getByRole('button', { name: /Research archive/ })).toContainText(
    'Access key ••••1234',
  );
  await expect(page.getByLabel('Secret access key')).toHaveCount(0);
  expect(await page.locator('body').textContent()).not.toContain(firstSecret);
  expect(page.url()).not.toContain(firstSecret);
  expect(
    await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage })),
  ).not.toContain(firstSecret);

  await page.getByRole('button', { name: 'Test connection' }).click();
  await expect(
    page.getByText(/testing is unavailable until this connector is installed/),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Rotate credentials' }).click();
  await page.getByLabel('Access key ID').fill(rotatedAccess);
  await page.getByLabel('Secret access key').fill(rotatedSecret);
  await page.getByRole('button', { name: 'Rotate credentials', exact: true }).click();
  await expect(page.getByRole('button', { name: /Research archive/ })).toContainText(
    'Access key ••••5678',
  );
  await expect(page.getByLabel('Secret access key')).toHaveCount(0);
  await page.getByRole('button', { name: 'Re-encrypt with active key' }).click();
  await expect(page.getByRole('button', { name: /Research archive/ })).toContainText('untested');

  expect(responseBodies.join(' ')).not.toContain(firstAccess);
  expect(responseBodies.join(' ')).not.toContain(firstSecret);
  expect(responseBodies.join(' ')).not.toContain(rotatedAccess);
  expect(responseBodies.join(' ')).not.toContain(rotatedSecret);
  expect(await page.locator('body').textContent()).not.toContain(rotatedSecret);

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: 'test-results/connections-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/connections-mobile.png', fullPage: true });
});
