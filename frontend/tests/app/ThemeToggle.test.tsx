import { act, cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeToggle } from '../../src/app/ThemeToggle';

// covers: AC-2 (theme toggle precedence, storage event across tabs, OS theme when unset,
// blocked storage) and the labeled header toggle in AC-5.

const STORAGE_KEY = 'rqs.theme';
const originalMatchMedia = window.matchMedia;
const root = document.documentElement;

// A controllable OS theme: flip `light` and fire the stored change listeners.
function stubSystemTheme(initiallyLight: boolean) {
  const listeners = new Set<() => void>();
  const state = { light: initiallyLight };
  window.matchMedia = ((query: string) => ({
    get matches() {
      return query === '(prefers-color-scheme: light)' && state.light;
    },
    media: query,
    onchange: null,
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
  return {
    listeners,
    async change(light: boolean) {
      state.light = light;
      await act(async () => listeners.forEach((listener) => listener()));
    },
  };
}

async function fireStorage(key: string) {
  await act(async () => {
    window.dispatchEvent(new StorageEvent('storage', { key }));
  });
}

beforeEach(() => {
  window.localStorage.clear();
  root.setAttribute('data-theme', 'dark');
});

afterEach(() => {
  // Unmount before resetting the attribute, so the observer has nothing left to update.
  cleanup();
  window.matchMedia = originalMatchMedia;
  root.removeAttribute('data-theme');
  window.localStorage.clear();
});

test('in the dark theme the toggle offers light, with a matching title', async () => {
  render(<ThemeToggle />);
  const toggle = screen.getByRole('button', { name: 'Switch to light theme' });
  expect(toggle).toHaveAttribute('title', 'Switch to light theme');
});

test('clicking switches to light, stores the choice and relabels the button', async () => {
  const user = userEvent.setup();
  render(<ThemeToggle />);
  await user.click(screen.getByRole('button', { name: 'Switch to light theme' }));
  expect(root).toHaveAttribute('data-theme', 'light');
  expect(window.localStorage.getItem(STORAGE_KEY)).toBe('light');
  expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument();
});

test('clicking twice returns to dark', async () => {
  const user = userEvent.setup();
  render(<ThemeToggle />);
  await user.click(screen.getByRole('button', { name: 'Switch to light theme' }));
  await user.click(screen.getByRole('button', { name: 'Switch to dark theme' }));
  expect(root).toHaveAttribute('data-theme', 'dark');
  expect(window.localStorage.getItem(STORAGE_KEY)).toBe('dark');
});

test('an unknown data-theme value reads as dark', async () => {
  root.setAttribute('data-theme', 'sepia');
  render(<ThemeToggle />);
  expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument();
});

test('follows a data-theme change made outside the hook', async () => {
  render(<ThemeToggle />);
  await act(async () => root.setAttribute('data-theme', 'light'));
  expect(await screen.findByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument();
});

test('another tab storing a theme applies it here', async () => {
  stubSystemTheme(false);
  render(<ThemeToggle />);
  window.localStorage.setItem(STORAGE_KEY, 'light');
  await fireStorage(STORAGE_KEY);
  expect(root).toHaveAttribute('data-theme', 'light');
  expect(await screen.findByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument();
});

test('another tab clearing the theme falls back to the OS theme', async () => {
  stubSystemTheme(true);
  render(<ThemeToggle />);
  await fireStorage(STORAGE_KEY);
  expect(root).toHaveAttribute('data-theme', 'light');
});

test('storage events for other keys are ignored', async () => {
  stubSystemTheme(true);
  render(<ThemeToggle />);
  await fireStorage('something.else');
  expect(root).toHaveAttribute('data-theme', 'dark');
});

test('with nothing stored, an OS theme change is followed live', async () => {
  const system = stubSystemTheme(false);
  render(<ThemeToggle />);
  await system.change(true);
  expect(root).toHaveAttribute('data-theme', 'light');
  await system.change(false);
  expect(root).toHaveAttribute('data-theme', 'dark');
});

test('a stored choice wins over an OS theme change', async () => {
  const user = userEvent.setup();
  const system = stubSystemTheme(false);
  render(<ThemeToggle />);
  await user.click(screen.getByRole('button', { name: 'Switch to light theme' }));
  await user.click(screen.getByRole('button', { name: 'Switch to dark theme' }));
  await system.change(true);
  expect(root).toHaveAttribute('data-theme', 'dark');
});

test('the toggle still switches this page when storage is blocked', async () => {
  const user = userEvent.setup();
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new DOMException('blocked', 'SecurityError');
  });
  render(<ThemeToggle />);
  await user.click(screen.getByRole('button', { name: 'Switch to light theme' }));
  expect(root).toHaveAttribute('data-theme', 'light');
});

test('with storage blocked, an OS change is still followed', async () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new DOMException('blocked', 'SecurityError');
  });
  const system = stubSystemTheme(false);
  render(<ThemeToggle />);
  await system.change(true);
  expect(root).toHaveAttribute('data-theme', 'light');
});

test('unmounting removes the OS theme listener', async () => {
  const system = stubSystemTheme(false);
  const { unmount } = render(<ThemeToggle />);
  expect(system.listeners.size).toBe(1);
  unmount();
  expect(system.listeners.size).toBe(0);
});
