const configuredBase = import.meta.env.VITE_DOCS_BASE_URL?.trim();
const base = (configuredBase || 'http://127.0.0.1:3000').replace(/\/+$/, '');

/** Public routes only. Never append project, source, credential, or question data. */
export function docsHref(route: string): string {
  return `${base}/docs/${route.replace(/^\/+|\/+$/g, '')}/`;
}
