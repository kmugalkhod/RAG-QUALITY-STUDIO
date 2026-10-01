// Sets data-theme on <html> before the first paint so there is no flash of the wrong
// theme (spec 0002, AC-2). An unset theme follows the OS; keep in sync with src/app/useTheme.ts.
(function () {
  var theme = 'dark';
  try {
    var stored = window.localStorage.getItem('rqs.theme');
    if (stored === 'light' || stored === 'dark') {
      theme = stored;
    } else if (window.matchMedia('(prefers-color-scheme: light)').matches) {
      theme = 'light';
    }
  } catch {
    // Storage can be blocked; fall back to the OS theme when it can be read.
    try {
      if (window.matchMedia('(prefers-color-scheme: light)').matches) {
        theme = 'light';
      }
    } catch {
      // The dark default still applies.
    }
  }
  document.documentElement.setAttribute('data-theme', theme);
})();
