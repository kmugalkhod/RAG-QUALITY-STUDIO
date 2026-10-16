import { defaultWebsite, derivedIncludePrefixes } from './editorModel';
import type { RecommendationPath, SettingRecommendation, WebsiteConfig } from './model';

/**
 * Settings a recommendation pre-fills (spec 0011). Discovery is pre-filled only while it
 * is still the analysed input (Slice 2 may switch a crawl to the site's sitemap).
 */
export const PREFILLED_PATHS = [
  'selection',
  'allowed_origins',
  'include_path_prefixes',
  'exclude_path_prefixes',
  'max_pages',
  'max_depth',
  'requests_per_second',
] as const satisfies readonly RecommendationPath[];

type PrefilledPath = (typeof PREFILLED_PATHS)[number];

const originOf = (value: string) => {
  try {
    return new URL(value).origin;
  } catch {
    return value;
  }
};

const hrefOf = (value: string) => {
  try {
    return new URL(value).href;
  } catch {
    return value;
  }
};

/** One key per selection, with its URLs normalized. */
function selectionKey(selection: WebsiteConfig['selection'] | undefined): string {
  if (!selection) {
    return 'null';
  }
  switch (selection.mode) {
    case 'crawl':
      return JSON.stringify(['crawl', hrefOf(selection.start_url)]);
    case 'sitemap':
      return JSON.stringify(['sitemap', hrefOf(selection.sitemap_url)]);
    case 'single_url':
      return JSON.stringify(['single_url', hrefOf(selection.url)]);
    case 'url_list':
      return JSON.stringify(['url_list', ...selection.urls.map(hrefOf)]);
  }
}

/** Comparable form, as the server compares: origins normalized, prefix lists as sorted sets. */
function comparable(path: PrefilledPath, value: unknown): string {
  if (path === 'selection') {
    return selectionKey(value as WebsiteConfig['selection'] | undefined);
  }
  if (path === 'allowed_origins') {
    return JSON.stringify(Array.from(new Set((value as string[]).map(originOf))).sort());
  }
  if (path === 'include_path_prefixes' || path === 'exclude_path_prefixes') {
    return JSON.stringify(Array.from(new Set((value as string[] | undefined) ?? [])).sort());
  }
  return JSON.stringify(value ?? null);
}

function current(config: WebsiteConfig, path: PrefilledPath): unknown {
  if (path === 'include_path_prefixes' || path === 'exclude_path_prefixes') {
    return config[path] ?? [];
  }
  return config[path];
}

function recommendedValue(recommendation: SettingRecommendation, path: PrefilledPath): unknown {
  const value = recommendation.recommended?.[path];
  return path === 'allowed_origins' ? (value as string[]).map(originOf) : value;
}

/**
 * Whether a recommendation was computed for the address now in the form: the analysed
 * input, or the discovery it recommended (a crawl switched to the site's sitemap).
 */
export function recommendationMatches(
  config: WebsiteConfig,
  recommendation: SettingRecommendation,
): boolean {
  const entered = selectionKey(config.selection);
  return (
    entered === selectionKey(recommendation.inputs.selection) ||
    (!!recommendation.recommended && entered === selectionKey(recommendation.recommended.selection))
  );
}

/**
 * Pre-fills a draft from a succeeded recommendation. A setting is replaced only while it
 * still holds the default, the value derived from the address, or the previous
 * recommendation's value; anything the user edited is kept.
 */
export function applyRecommendation(
  config: WebsiteConfig,
  recommendation: SettingRecommendation,
  previous?: SettingRecommendation,
): WebsiteConfig {
  if (!recommendation.recommended || config.selection.mode !== 'crawl') {
    return config;
  }
  const defaults = defaultWebsite();
  const derived: Partial<Record<PrefilledPath, unknown>> = {
    selection: recommendation.inputs.selection,
    allowed_origins: [originOf(config.selection.start_url)],
    include_path_prefixes: derivedIncludePrefixes(config.selection.start_url),
  };
  const next: WebsiteConfig = { ...config };
  for (const path of PREFILLED_PATHS) {
    const value = current(config, path);
    const replaceable = [
      defaults[path] ?? [],
      derived[path],
      previous?.recommended ? recommendedValue(previous, path) : undefined,
    ].some(
      (candidate) =>
        candidate !== undefined && comparable(path, candidate) === comparable(path, value),
    );
    if (replaceable) {
      Object.assign(next, { [path]: recommendedValue(recommendation, path) });
    }
  }
  return next;
}

/** Settings whose value in the form differs from the recommendation. */
export function recommendationDifferences(
  config: WebsiteConfig,
  recommendation: SettingRecommendation,
): Set<RecommendationPath> {
  const changed = new Set<RecommendationPath>();
  if (!recommendation.recommended) {
    return changed;
  }
  for (const path of PREFILLED_PATHS) {
    if (
      comparable(path, current(config, path)) !==
      comparable(path, recommendedValue(recommendation, path))
    ) {
      changed.add(path);
    }
  }
  return changed;
}

/** One line for a recommended value: lists joined, an empty list named. */
export function formatRecommendedValue(path: RecommendationPath, value: unknown): string {
  if (path === 'selection') {
    const selection = value as WebsiteConfig['selection'];
    return selection.mode === 'crawl'
      ? 'Crawl from the address'
      : selection.mode === 'sitemap'
        ? 'Sitemap'
        : selection.mode === 'url_list'
          ? 'URL list'
          : 'Single page';
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return path === 'include_path_prefixes' ? 'Every path' : 'None';
    }
    return value.map((item) => (path === 'allowed_origins' ? originOf(item) : item)).join(', ');
  }
  if (path === 'requests_per_second') {
    return `${value} per second`;
  }
  if (path === 'max_depth') {
    return `${value} link hops`;
  }
  return String(value);
}

/** Whether a recommended field does not apply to the recommended discovery mode. */
export const notUsed = (rationaleCode: string) => rationaleCode.endsWith('_not_used');

/**
 * Minutes a page limit takes at a speed, rounded up. robots.txt can only slow a crawl, so
 * a crawl delay longer than the speed's interval sets the pace.
 */
export function estimatedMinutes(pages: number, rps: number, crawlDelay?: number | null): number {
  const interval = Math.max(1 / rps, crawlDelay ?? 0);
  return Math.max(1, Math.ceil((pages * interval) / 60));
}

/** The longest Crawl-delay the analysis read, from its robots.txt evidence. */
export function evidenceCrawlDelay(recommendation: SettingRecommendation): number | null {
  const facts = [recommendation.evidence.robots, ...(recommendation.evidence.extra_robots ?? [])];
  const delays = facts
    .map((item) => item?.crawl_delay)
    .filter((value): value is number => typeof value === 'number' && value > 0);
  return delays.length ? Math.max(...delays) : null;
}
