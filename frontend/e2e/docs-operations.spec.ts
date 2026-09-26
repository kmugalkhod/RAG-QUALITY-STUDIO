import { expect, test } from '@playwright/test';

const screenshots = '../docs/site/static/img/screenshots';

test.beforeEach(() => {
  test.skip(
    process.env.E2E_OPERATIONS_FIXTURE !== '1',
    'Operator screenshots require the isolated backend without provider credentials.',
  );
});

test('operator help links and unavailable-provider Settings at desktop and mobile widths', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const created = (await (
    await request.post('/api/projects', { data: { name: 'Docs operator fixture' } })
  ).json()) as { id: string };
  await page.goto(`/#/projects/${created.id}/settings`);
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
  await expect(page.getByText(/Set OPENROUTER_API_KEY in the server environment/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Security and permissions' })).toHaveAttribute(
    'href',
    'http://127.0.0.1:3000/docs/operate/security/',
  );
  await expect(page.getByRole('link', { name: 'Limits and FAQ' })).toHaveAttribute(
    'href',
    'http://127.0.0.1:3000/docs/reference/limits-faq/',
  );
  await expect(page.getByRole('link', { name: 'Troubleshoot unavailable settings' })).toHaveAttribute(
    'href',
    'http://127.0.0.1:3000/docs/operate/troubleshooting/',
  );
  const models = page.locator('section.settings-section').filter({
    has: page.getByRole('heading', { name: 'Models', exact: true }),
  });
  await models.screenshot({ path: `${screenshots}/17-provider-unavailable.png` });
  await page.setViewportSize({ width: 720, height: 1000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('link', { name: 'Security and permissions' }).focus();
  await expect(page.getByRole('link', { name: 'Security and permissions' })).toBeFocused();
  await models.screenshot({ path: `${screenshots}/18-provider-unavailable-mobile.png` });
});
