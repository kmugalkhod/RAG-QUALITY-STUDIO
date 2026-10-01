import { useCallback, useSyncExternalStore } from 'react';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'rqs.theme';
// An unset theme follows the OS. Keep in sync with public/theme-init.js.
const LIGHT_QUERY = '(prefers-color-scheme: light)';

function isTheme(value: unknown): value is Theme {
  return value === 'light' || value === 'dark';
}

function readStoredTheme(): Theme | null {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isTheme(stored) ? stored : null;
  } catch {
    return null;
  }
}

function fallbackTheme(): Theme {
  return window.matchMedia(LIGHT_QUERY).matches ? 'light' : 'dark';
}

function currentTheme(): Theme {
  const value = document.documentElement.getAttribute('data-theme');
  return isTheme(value) ? value : 'dark';
}

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute('data-theme', theme);
}

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  // Another tab changed the stored theme.
  function onStorage(event: StorageEvent) {
    if (event.key === STORAGE_KEY) {
      applyTheme(readStoredTheme() ?? fallbackTheme());
    }
  }
  // The OS theme only matters while nothing is stored.
  const media = window.matchMedia(LIGHT_QUERY);
  function onSystemChange() {
    if (readStoredTheme() === null) {
      applyTheme(fallbackTheme());
    }
  }

  window.addEventListener('storage', onStorage);
  media.addEventListener('change', onSystemChange);
  return () => {
    observer.disconnect();
    window.removeEventListener('storage', onStorage);
    media.removeEventListener('change', onSystemChange);
  };
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, currentTheme, () => 'dark' as Theme);
  const toggleTheme = useCallback(() => {
    const next: Theme = currentTheme() === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // The theme still switches for this page when storage is blocked.
    }
  }, []);
  return { theme, toggleTheme };
}
