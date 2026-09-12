import { test, expect } from '@playwright/test';
test('creates a real project and preserves it across reload', async ({ page }) => {
  const name = `Browser verification ${Date.now()}`;
  await page.goto('/');
  await page.getByRole('button', { name: 'New project', exact: true }).click();
  await page.getByLabel('Project name').fill(name);
  await page.getByLabel('Description').fill('Created by the opt-in browser integration test.');
  await page.getByRole('button', { name: 'Create project', exact: true }).click();
  await expect(
    page.getByRole('status').filter({ hasText: `Project “${name}” created.` }),
  ).toContainText('created');
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
});
