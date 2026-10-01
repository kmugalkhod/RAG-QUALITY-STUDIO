import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';
// Unit suites exercise the local-owner shell; Clerk browser journeys use the
// configured development instance separately.
vi.stubEnv('VITE_CLERK_PUBLISHABLE_KEY', '');
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// jsdom has no layout engine. Browser tests exercise actual resizing.
class ResizeObserverStub {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub);

// jsdom has no media queries: every query reports no match (dark theme, fine pointer).
// Suites that need a match, such as touch vibration, stub their own.
vi.stubGlobal(
  'matchMedia',
  (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }) as MediaQueryList,
);
