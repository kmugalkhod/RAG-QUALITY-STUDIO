import { defaultWebsite, derivedIncludePrefixes } from './editorModel';
import type { RecommendationPath, SettingRecommendation, WebsiteConfig } from './model';

/**
 * Settings a recommendation pre-fills (spec 0011). The address and discovery mode stay as
 * the user entered them.
 */
export const PREFILLED_PATHS = [
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

/** Comparable form, as the server compares: origins normalized, prefix lists as sorted sets. */
function comparable(path: PrefilledPath, value: unknown): string {
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

/** The crawl start URL a config or recommendation refers to, normalized. */
function startUrl(selection: WebsiteConfig['selection']): string | null {
  return selection.mode === 'crawl' ? hrefOf(selection.start_url) : null;
}

/** Whether a recommendation was computed for the address now in the form. */
export function recommendationMatches(
  config: WebsiteConfig,
  recommendation: SettingRecommendation,
): boolean {
  const entered = startUrl(config.selection);
  return entered !== null && entered === startUrl(recommendation.inputs.selection);
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
