import { test, expect } from '@playwright/test';

const customer = 'http://127.0.0.1:5275';
const copied = 'http://127.0.0.1:5276';
test.skip(
  !process.env.WIDGET_E2E,
  'Start the isolated widget browser fixture and set WIDGET_E2E=1.',
);
test.describe.configure({ mode: 'serial' });

test('backend-only fixture key is outside the widget web root', async ({ request }) => {
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const keyPath = join(tmpdir(), `rag-widget-browser-${process.getuid!()}.json`);
  expect((await request.get('http://127.0.0.1:5274/.local/browser.json')).status()).not.toBe(200);
  expect((await request.get(`http://127.0.0.1:5274/@fs${keyPath}`)).status()).not.toBe(200);
});

test('localhost demo alias redirects to the exact allowed site origin', async ({ page }) => {
  await page.goto('http://localhost:5275/');
  await expect(page).toHaveURL(`${customer}/`);
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  await expect(frame.getByRole('button', { name: /Open .* assistant/i })).toBeEnabled();
});

test('plain HTML authenticated embed submits, polls and inspects citations', async ({ page }) => {
  const widgetCookies: Array<string | undefined> = [];
  page.on('request', (request) => {
    if (request.url().includes('/widget/questions')) widgetCookies.push(request.headers().cookie);
  });
  await page.goto(customer);
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  await expect(frame.getByRole('button', { name: /Open .* assistant/i })).toBeEnabled();
  await frame.getByRole('button', { name: /Open .* assistant/i }).click();
  await expect(frame.getByRole('region', { name: /assistant/i })).toBeVisible();
  await expect(frame.getByRole('dialog')).toHaveCount(0);
  await expect(frame.getByRole('status')).toContainText('Sign in');
  await expect(frame.getByRole('status')).toBeVisible();
  await frame.getByRole('button', { name: 'Close assistant' }).click();
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(frame.getByRole('button', { name: /Open .* assistant/i })).toBeEnabled();
  await frame.getByRole('button', { name: /Open .* assistant/i }).click();
  await expect(frame.getByRole('status')).toContainText('Ready');
  await frame.getByRole('textbox', { name: 'Your question' }).fill('What is the fixture answer?');
  await frame.getByRole('button', { name: 'Ask question' }).click();
  await expect(frame.getByRole('status')).toContainText('Answer ready', { timeout: 15000 });
  await expect(frame.getByRole('textbox', { name: 'Your question' })).toBeFocused();
  await expect(frame.getByRole('heading', { name: 'Answer' })).toBeVisible();
  await frame.getByRole('button', { name: 'View source S1' }).click();
  await expect(frame.getByRole('button', { name: 'Evidence (1)' })).toHaveAttribute(
    'aria-expanded',
    'true',
  );
  await expect(frame.getByText('Fixture guide.txt')).toBeVisible();
  await expect(frame.getByText('The fixture answer is forty-two.', { exact: true })).toBeVisible();
  await expect(page.locator('iframe[title="Website question assistant"]')).toHaveCount(1);
  expect(widgetCookies.length).toBeGreaterThan(0);
  expect(widgetCookies.every((value) => !value)).toBe(true);
});

test('copied embed cannot reach a usable assistant', async ({ page }) => {
  const questions: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/widget/questions')) questions.push(request.url());
  });
  await page.goto(copied);
  await expect(page.getByRole('heading', { name: 'Copied embed' })).toBeVisible();
  await expect(page.locator('iframe[title="Website question assistant"]')).toHaveCount(1);
  await expect(page.getByText('Assistant unavailable. Check this site widget setup.')).toBeVisible({
    timeout: 15_000,
  });
  expect(questions).toHaveLength(0);
});

test('React shared root layout keeps one launcher through client navigation', async ({ page }) => {
  await page.goto(`${customer}/react`);
  await expect(page.getByRole('heading', { name: 'Overview route' })).toBeVisible();
  await expect(page.locator('iframe[title="Website question assistant"]')).toHaveCount(1);
  await page.getByRole('button', { name: 'Help' }).click();
  await expect(page.getByRole('heading', { name: 'Help route' })).toBeVisible();
  await expect(page.locator('iframe[title="Website question assistant"]')).toHaveCount(1);
});

test('Vue shared root layout keeps one launcher and authenticates after navigation', async ({
  page,
}) => {
  await page.goto(customer);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.goto(`${customer}/vue`);
  await expect(page.getByRole('heading', { name: 'Overview route' })).toBeVisible();
  await expect(page.locator('iframe[title="Website question assistant"]')).toHaveCount(1);
  await page.getByRole('button', { name: 'Help' }).click();
  await expect(page.getByRole('heading', { name: 'Help route' })).toBeVisible();
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  await expect(frame.getByRole('button', { name: /Open .* assistant/i })).toBeEnabled();
  await frame.getByRole('button', { name: /Open .* assistant/i }).click();
  await expect(frame.getByRole('status')).toContainText('Ready');
  await frame.getByRole('textbox', { name: 'Your question' }).fill('Question from Vue layout');
  await frame.getByRole('button', { name: 'Ask question' }).click();
  await expect(frame.getByRole('status')).toContainText('Answer ready', { timeout: 15000 });
  await expect(page.locator('iframe[title="Website question assistant"]')).toHaveCount(1);
});

test('server-rendered shared head layout loads once before and after DOM ready', async ({
  page,
}) => {
  const response = await page.goto(`${customer}/server`);
  expect(response?.headers()['content-security-policy']).toContain(
    'frame-src http://127.0.0.1:5274',
  );
  await expect(page.getByRole('heading', { name: 'Overview route' })).toBeVisible();
  await expect(page.locator('body > iframe[title="Website question assistant"]')).toHaveCount(1);
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  await expect(frame.getByRole('button', { name: /Open .* assistant/i })).toBeEnabled();
  await page.getByRole('link', { name: 'Help' }).click();
  await expect(page.getByRole('heading', { name: 'Help route' })).toBeVisible();
  await expect(page.locator('body > iframe[title="Website question assistant"]')).toHaveCount(1);
});

test('mobile dialog covers viewport and Escape returns to launcher', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(customer);
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  const launcher = frame.getByRole('button', { name: /Open .* assistant/i });
  await expect(launcher).toBeEnabled();
  await launcher.focus();
  await launcher.press('Enter');
  await expect(frame.getByRole('dialog')).toBeVisible();
  await expect(frame.getByRole('status')).toBeVisible();
  expect(
    await frame
      .locator('footer')
      .evaluate((element) => parseFloat(getComputedStyle(element).fontSize)),
  ).toBeGreaterThanOrEqual(12);
  const box = await page.locator('iframe[title="Website question assistant"]').boundingBox();
  expect(box?.width).toBe(390);
  expect(box?.height).toBe(844);
  await frame.getByRole('textbox', { name: 'Your question' }).press('Escape');
  await expect(launcher).toBeVisible();
  await expect(launcher).toBeFocused();
  await launcher.press('Space');
  await expect(frame.getByRole('dialog')).toBeVisible();
});

test('zoom-sized viewport and reduced motion keep the chat usable', async ({ page }) => {
  await page.setViewportSize({ width: 720, height: 740 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(customer);
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  await frame.getByRole('button', { name: /Open .* assistant/i }).click();
  await expect(frame.getByRole('region', { name: /assistant/i })).toBeVisible();
  expect(
    await frame.locator('.panel').evaluate((element) => element.scrollWidth <= element.clientWidth),
  ).toBe(true);
  await expect(frame.getByRole('textbox', { name: 'Your question' })).toBeVisible();
});

test('insufficient evidence and provider failure remain honest', async ({ page }) => {
  await page.goto(customer);
  await page.getByRole('button', { name: 'Sign in' }).click();
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  await frame.getByRole('button', { name: /Open .* assistant/i }).click();
  await expect(frame.getByRole('status')).toContainText('Ready');
  await frame.getByRole('textbox', { name: 'Your question' }).fill('This is unanswerable');
  await frame.getByRole('button', { name: 'Ask question' }).click();
  await expect(frame.getByRole('status')).toContainText('insufficient', { timeout: 15000 });
  await expect(frame.getByRole('heading', { name: 'Answer' })).toHaveCount(0);
  await expect(frame.getByRole('button', { name: /Evidence/ })).toHaveCount(0);
  await frame.getByRole('textbox', { name: 'Your question' }).fill('Fail provider please');
  await frame.getByRole('button', { name: 'Ask question' }).click();
  await expect(frame.getByRole('status')).toContainText('provider outcome is unknown', {
    timeout: 15000,
  });
  await expect(frame.getByRole('heading', { name: 'Answer' })).toHaveCount(0);
});

test('expired widget token renews through the customer session', async ({ page }) => {
  const { execFileSync } = await import('node:child_process');
  const env = { ...process.env, PYTHONPATH: '../backend' };
  await page.goto(customer);
  await page.getByRole('button', { name: 'Sign in' }).click();
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  await frame.getByRole('button', { name: /Open .* assistant/i }).click();
  await expect(frame.getByRole('status')).toContainText('Ready');
  execFileSync('../backend/.venv/bin/python', ['../widget/e2e/control.py', 'expire'], { env });
  await frame.getByRole('textbox', { name: 'Your question' }).fill('Question after token expiry');
  await frame.getByRole('button', { name: 'Ask question' }).click();
  await expect(frame.getByRole('status')).toContainText('Answer ready', { timeout: 15000 });
});

test('paused deployment denies the browser launcher', async ({ page }) => {
  const { execFileSync } = await import('node:child_process');
  const env = { ...process.env, PYTHONPATH: '../backend' };
  execFileSync('../backend/.venv/bin/python', ['../widget/e2e/control.py', 'pause'], { env });
  try {
    await page.goto(customer);
    const frame = page.frameLocator('iframe[title="Website question assistant"]');
    await expect(frame.getByRole('button', { name: /is paused/i })).toBeDisabled();
  } finally {
    execFileSync('../backend/.venv/bin/python', ['../widget/e2e/control.py', 'resume'], { env });
  }
});

test('ambiguous admission retries with the original idempotency key', async ({ page }) => {
  await page.goto(customer);
  await page.getByRole('button', { name: 'Sign in' }).click();
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  await frame.getByRole('button', { name: /Open .* assistant/i }).click();
  await expect(frame.getByRole('status')).toContainText('Ready');
  const keys: string[] = [];
  let first = true;
  await page.route('**/widget/questions', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    keys.push(route.request().headers()['idempotency-key']);
    const response = await route.fetch();
    if (first) {
      first = false;
      await route.abort('failed');
    } else await route.fulfill({ response });
  });
  await frame.getByRole('textbox', { name: 'Your question' }).fill('Retry this question');
  await frame.getByRole('button', { name: 'Ask question' }).click();
  await expect(frame.getByRole('status')).toContainText('temporarily unavailable');
  await frame.getByRole('button', { name: 'Ask question' }).click();
  await expect(frame.getByRole('status')).toContainText('Answer ready', { timeout: 15000 });
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
});

test('interrupted polling resumes the accepted run without another admission', async ({ page }) => {
  await page.goto(customer);
  await page.getByRole('button', { name: 'Sign in' }).click();
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  await frame.getByRole('button', { name: /Open .* assistant/i }).click();
  await expect(frame.getByRole('status')).toContainText('Ready');
  let admissions = 0;
  let interrupted = 0;
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/widget/questions')) admissions++;
  });
  await page.route('**/widget/questions/*/status', async (route) => {
    if (interrupted < 3) {
      interrupted++;
      await route.abort('failed');
    } else await route.continue();
  });
  await frame.getByRole('textbox', { name: 'Your question' }).fill('Polling should resume');
  await frame.getByRole('button', { name: 'Ask question' }).click();
  await expect(frame.getByRole('status')).toContainText('Connection interrupted', {
    timeout: 15000,
  });
  await frame.getByRole('button', { name: 'Check result again' }).click();
  await expect(frame.getByRole('status')).toContainText('Answer ready', { timeout: 15000 });
  expect(admissions).toBe(1);
});

test('rate response shows a retry countdown and disables submission', async ({ page }) => {
  await page.goto(customer);
  await page.getByRole('button', { name: 'Sign in' }).click();
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  await frame.getByRole('button', { name: /Open .* assistant/i }).click();
  await expect(frame.getByRole('status')).toContainText('Ready');
  await page.route('**/widget/questions', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 429,
      headers: {
        'content-type': 'application/json',
        'retry-after': '3',
        'access-control-allow-origin': 'http://127.0.0.1:5274',
      },
      body: JSON.stringify({ error: { code: 'rate_limited', message: 'Too many questions.' } }),
    });
  });
  await frame.getByRole('textbox', { name: 'Your question' }).fill('Rate-limited question');
  await frame.getByRole('button', { name: 'Ask question' }).click();
  await expect(frame.getByRole('status')).toContainText('Too many questions');
  await expect(frame.getByRole('button', { name: 'Ask question' })).toBeDisabled();
});

test('conversation keeps earlier turns while each Enter submission is independent', async ({
  page,
}) => {
  await page.goto(customer);
  await page.getByRole('button', { name: 'Sign in' }).click();
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  await frame.getByRole('button', { name: /Open .* assistant/i }).click();
  await expect(frame.getByRole('status')).toContainText('Ready');
  const composer = frame.getByRole('textbox', { name: 'Your question' });
  await composer.fill('First independent question');
  await composer.press('Enter');
  await expect(frame.getByRole('status')).toContainText('Answer ready', { timeout: 15000 });
  await composer.fill('Second question');
  await composer.press('Shift+Enter');
  await composer.type('with another line');
  await composer.press('Enter');
  await expect(frame.getByRole('status')).toContainText('Answer ready', { timeout: 15000 });
  await expect(frame.getByRole('group', { name: 'You asked' })).toHaveCount(2);
  await expect(frame.getByRole('heading', { name: 'Answer' })).toHaveCount(2);
  await expect(frame.getByText('First independent question')).toBeVisible();
  await expect(frame.getByText('Second question\nwith another line')).toBeVisible();
});

test('untrusted answer and citation HTML render as inert text', async ({ page }) => {
  let dialogs = 0;
  page.on('dialog', (dialog) => {
    dialogs++;
    void dialog.dismiss();
  });
  await page.goto(customer);
  await page.getByRole('button', { name: 'Sign in' }).click();
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  await frame.getByRole('button', { name: /Open .* assistant/i }).click();
  await expect(frame.getByRole('status')).toContainText('Ready');
  await frame.getByRole('textbox', { name: 'Your question' }).fill('html injection check');
  await frame.getByRole('button', { name: 'Ask question' }).click();
  await expect(frame.getByRole('status')).toContainText('Answer ready', { timeout: 15000 });
  await frame.getByRole('button', { name: 'Evidence (1)' }).click();
  await expect(frame.getByText('<img src=x onerror=alert(1)>', { exact: true })).toBeVisible();
  await expect(frame.getByText('<script>alert(1)</script>', { exact: true })).toBeVisible();
  await expect(frame.locator('.transcript img, .transcript script')).toHaveCount(0);
  expect(dialogs).toBe(0);
});

test('slow response explains that work is still running and then completes', async ({ page }) => {
  test.setTimeout(35_000);
  await page.goto(customer);
  await page.getByRole('button', { name: 'Sign in' }).click();
  const frame = page.frameLocator('iframe[title="Website question assistant"]');
  await frame.getByRole('button', { name: /Open .* assistant/i }).click();
  await expect(frame.getByRole('status')).toContainText('Ready');
  await frame.getByRole('textbox', { name: 'Your question' }).fill('slow response check');
  await frame.getByRole('button', { name: 'Ask question' }).click();
  await expect(
    frame.getByText('This is taking longer than usual. You can keep waiting.'),
  ).toBeVisible({ timeout: 20_000 });
  await expect(frame.getByRole('status')).toContainText('Answer ready', { timeout: 20_000 });
});
