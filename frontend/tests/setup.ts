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
