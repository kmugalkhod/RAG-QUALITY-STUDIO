import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// covers: AC-2 (the theme is set before first paint: stored value, else the OS, else dark)

const script = readFileSync(resolve(__dirname, '../../public/theme-init.js'), 'utf8');
const originalMatchMedia = window.matchMedia;
const root = document.documentElement;

function runInit() {
  new Function(script)();
  return root.getAttribute('data-theme');
}

function stubSystemLight(light: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query === '(prefers-color-scheme: light)' && light,
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  window.localStorage.clear();
  root.removeAttribute('data-theme');
});

afterEach(() => {
  window.matchMedia = originalMatchMedia;
  window.localStorage.clear();
  root.removeAttribute('data-theme');
});

test('nothing stored and a dark OS loads dark', () => {
  stubSystemLight(false);
  expect(runInit()).toBe('dark');
});

test('nothing stored and a light OS loads light', () => {
  stubSystemLight(true);
  expect(runInit()).toBe('light');
});

test('a stored choice wins over the OS theme', () => {
  stubSystemLight(true);
  window.localStorage.setItem('rqs.theme', 'dark');
  expect(runInit()).toBe('dark');
});

test('an invalid stored value is ignored in favour of the OS theme', () => {
  stubSystemLight(true);
  window.localStorage.setItem('rqs.theme', 'blue');
  expect(runInit()).toBe('light');
});

test('blocked storage still follows the OS theme', () => {
  stubSystemLight(true);
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new DOMException('blocked', 'SecurityError');
  });
  expect(runInit()).toBe('light');
});

test('blocked storage and an unreadable OS theme fall back to dark', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new DOMException('blocked', 'SecurityError');
  });
  window.matchMedia = (() => {
    throw new Error('unsupported');
  }) as unknown as typeof window.matchMedia;
  expect(runInit()).toBe('dark');
});
