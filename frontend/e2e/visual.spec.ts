import AxeBuilder from '@axe-core/playwright';
import { devices, expect, test, type Browser, type Page } from '@playwright/test';

// Visual journey for spec 0002 (AC-12). Run it against the isolated browser stack in local
// auth mode. Images land in the ignored test-results/visual/ folder for checklist review.

type Theme = 'dark' | 'light';
type State = 'loaded' | 'empty' | 'error' | 'loading';
type MigratedRoute = {
  name: string;
  path: (projectId: string) => string;
  // The route's primary list request, used to wait for data and to force states.
  request: RegExp;
  needsProject: boolean;
  // The forced states this route renders (AC-10); every state when absent.
  states?: State[];
};

// Add each route in the change that migrates it.
const MIGRATED_ROUTES: MigratedRoute[] = [
  { name: 'projects', path: () => '/', request: /\/api\/projects\?/, needsProject: false },
  {
    name: 'overview',
    path: (id) => `/#/projects/${id}/overview`,
    request: /\/api\/projects\/[a-f0-9-]{36}\/documents\?/,
    needsProject: true,
  },
  {
    name: 'knowledge',
    path: (id) => `/#/projects/${id}/knowledge-base`,
    request: /\/api\/projects\/[a-f0-9-]{36}\/documents\?/,
    needsProject: true,
  },
  {
    name: 'playground',
    path: (id) => `/#/projects/${id}/playground`,
    request: /\/api\/projects\/[a-f0-9-]{36}\/indexes\?/,
    needsProject: true,
  },
  {
    name: 'experiments',
    path: (id) => `/#/projects/${id}/experiments`,
    request: /\/api\/projects\/[a-f0-9-]{36}\/experiments\?/,
    needsProject: true,
  },
  {
    name: 'pipelines',
    path: (id) => `/#/projects/${id}/pipelines`,
    request: /\/api\/projects\/[a-f0-9-]{36}\/pipelines\?kind=answer/,
    needsProject: true,
  },
  {
    name: 'answer-editor',
    path: (id) => `/#/projects/${id}/pipelines/new`,
    request: /\/api\/projects\/[a-f0-9-]{36}\/pipelines\/options/,
    needsProject: true,
    // A failed load renders the editor's ErrorState.
    states: ['loaded', 'error'],
  },
  {
    name: 'ingestion-editor',
    path: (id) => `/#/projects/${id}/pipelines/new?kind=ingestion`,
    request: /\/api\/projects\/[a-f0-9-]{36}\/documents\?/,
    needsProject: true,
    states: ['loaded', 'error'],
  },
  {
    name: 'deployments',
    path: (id) => `/#/projects/${id}/deployments`,
    request: /\/api\/projects\/[a-f0-9-]{36}\/answer-deployments\?/,
    needsProject: true,
    // Deployments need an organization project, which local auth mode never creates, so the
    // journey reaches only the error and loading states; loaded and empty need Clerk or OIDC.
    states: ['error', 'loading'],
  },
  {
    name: 'settings',
    path: (id) => `/#/projects/${id}/settings`,
    request: /\/api\/projects\/[a-f0-9-]{36}\/upload-settings/,
    needsProject: true,
    // Settings has no list, so it renders loading and error only (AC-10).
    states: ['loaded', 'error', 'loading'],
  },
];

// Steps 1 and 2 of the build plan verified dark only; step 3 onward adds light.
const THEMES: Theme[] = ['dark', 'light'];
const STATES: State[] = ['loaded', 'empty', 'error', 'loading'];

// An empty page in the shape every list endpoint returns (`Page<T>` in src/lib/pagination.ts).
const EMPTY_PAGE = { items: [], total: 0, limit: 20, offset: 0 };

// The iPhone preset defaults to WebKit; only Chromium is installed, and the config's
// single project is Chromium, so the preset's browser type is dropped here.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const { defaultBrowserType, ...iPhone13 } = devices['iPhone 13'];
const CONTEXTS = [
  { name: 'desktop', use: { viewport: { width: 1280, height: 800 } } },
  { name: 'phone', use: iPhone13 },
];

let projectId = '';

async function createProject(browser: Browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  // Parallel workers can start in the same millisecond, so the name also carries a random id.
  const name = `Visual journey ${Date.now()} ${crypto.randomUUID().slice(0, 8)}`;
  await page.goto('/');
  await page.getByRole('button', { name: 'New project', exact: true }).click();
  await page.getByLabel('Project name').fill(name);
  await page.getByRole('button', { name: 'Create project', exact: true }).click();
  await page.getByRole('link', { name, exact: true }).click();
  await page.waitForURL(/#\/projects\/[a-f0-9-]{36}/);
  const id = /#\/projects\/([a-f0-9-]{36})/.exec(page.url())?.[1] ?? '';
  await context.close();
  return id;
}

async function prepare(page: Page, theme: Theme) {
  await page.addInitScript((value) => {
    window.localStorage.setItem('rqs.theme', value);
    const calls: unknown[] = [];
    Object.assign(window, { __vibrations: calls });
    navigator.vibrate = (pattern) => {
      calls.push(pattern);
      return true;
    };
  }, theme);
}

// Controls change variant once their data settles (the Overview primary waits for every
// stage count), so let finite transitions finish before sampling contrast. Spinners and
// skeleton pulses loop forever and are skipped.
async function settleTransitions(page: Page) {
  await page.waitForFunction(() =>
    document
      .getAnimations()
      .every(
        (animation) =>
          animation.playState !== 'running' ||
          animation.effect?.getComputedTiming().iterations === Infinity,
      ),
  );
}

async function checkPage(page: Page, phone: boolean) {
  await settleTransitions(page);
  if (phone) {
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  }
  const axe = await new AxeBuilder({ page }).withRules(['color-contrast']).analyze();
  expect(axe.violations).toEqual([]);
}

test.beforeAll(async ({ browser }) => {
  if (MIGRATED_ROUTES.some((route) => route.needsProject)) {
    projectId = await createProject(browser);
  }
});

for (const context of CONTEXTS) {
  test.describe(context.name, () => {
    test.use(context.use);
    const phone = context.name === 'phone';

    for (const route of MIGRATED_ROUTES) {
      for (const theme of THEMES) {
        for (const state of route.states ?? STATES) {
          test(`${route.name} in ${theme}, ${state}`, async ({ page }) => {
            await prepare(page, theme);
            let release = () => {};
            const held = new Promise<void>((resolve) => (release = resolve));
            if (state === 'empty') {
              await page.route(route.request, (r) => r.fulfill({ json: EMPTY_PAGE }));
            } else if (state === 'error') {
              await page.route(route.request, (r) =>
                r.fulfill({
                  status: 500,
                  json: { detail: 'Forced error for the visual journey.' },
                }),
              );
            } else if (state === 'loading') {
              await page.route(route.request, async (r) => {
                await held;
                await r.fallback();
              });
            }
            const loaded =
              state === 'loaded'
                ? page.waitForResponse((response) => route.request.test(response.url()))
                : null;
            await page.goto(route.path(projectId));
            await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
            if (loaded) {
              expect((await loaded).ok()).toBe(true);
              await page.waitForLoadState('networkidle');
            } else if (state === 'loading') {
              await expect(page.getByTestId('state-loading').first()).toBeVisible();
            } else {
              await expect(page.getByTestId(`state-${state}`).first()).toBeVisible();
            }
            await settleTransitions(page);
            const suffix = state === 'loaded' ? '' : `-${state}`;
            await page.screenshot({
              path: `test-results/visual/${route.name}-${context.name}-${theme}${suffix}.png`,
              fullPage: true,
            });
            await checkPage(page, phone);
            release();
          });
        }
      }
    }

    if (phone) {
      test('tab bar targets and touch sizing', async ({ page }) => {
        await prepare(page, 'dark');
        await page.goto(`/#/projects/${projectId}/overview`);
        const tabs = page.getByRole('navigation', { name: 'Project sections' });
        await expect(tabs).toBeVisible();
        for (const tab of await tabs.locator('a, button').all()) {
          const box = await tab.boundingBox();
          expect(box?.width).toBeGreaterThanOrEqual(44);
          expect(box?.height).toBeGreaterThanOrEqual(44);
        }
        await expect(tabs.getByRole('link', { name: 'Overview' })).toHaveAttribute(
          'aria-current',
          'page',
        );
        const primary = page.locator('[data-slot="button"][data-variant="primary"]');
        await expect(primary).toHaveCount(1);
        expect((await primary.boundingBox())?.height).toBe(48);
        await tabs.getByRole('button', { name: 'More' }).click();
        const sheet = page.getByRole('dialog', { name: 'More' });
        await expect(sheet.getByRole('link', { name: 'Experiments' })).toBeVisible();
        await page.screenshot({ path: 'test-results/visual/overview-phone-dark-more.png' });
      });
    } else {
      test('disconnected banner appears and clears on retry', async ({ page }) => {
        await prepare(page, 'dark');
        await page.route(/\/api\//, (r) => r.fulfill({ status: 502, body: '' }));
        await page.goto(`/#/projects/${projectId}/overview`);
        const banner = page.getByRole('status').filter({ hasText: 'Cannot reach the server' });
        await expect(banner).toContainText('No successful response yet');
        await page.screenshot({
          path: 'test-results/visual/overview-desktop-dark-disconnected.png',
        });
        await page.unroute(/\/api\//);
        await page.route(/\/api\/ready$/, async (r) => {
          await new Promise((resolve) => setTimeout(resolve, 300));
          await r.fallback();
        });
        await page.getByRole('button', { name: 'Retry' }).first().click();
        await expect(page.getByText('Checking…')).toBeVisible();
        await expect(page.getByText('Cannot reach the server')).toHaveCount(0);
        await expect(page.getByText('Checking…')).toHaveCount(0);
      });
    }
  });
}
