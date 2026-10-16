import { defaultWebsite, derivedIncludePrefixes } from './editorModel';
import type {
  ProvenanceField,
  RecommendationPath,
  SettingRecommendation,
  SettingsProvenance,
  WebsiteConfig,
  WebsiteSelection,
} from './model';

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
export function selectionKey(selection: WebsiteConfig['selection'] | undefined): string {
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
  if (!recommendation.recommended || !recommendationMatches(config, recommendation)) {
    return config;
  }
  const defaults = defaultWebsite();
  const urls = selectionUrls(config.selection);
  const derived: Partial<Record<PrefilledPath, unknown>> = {
    selection: recommendation.inputs.selection,
    allowed_origins: Array.from(new Set(urls.map(originOf))),
    include_path_prefixes:
      config.selection.mode === 'crawl' || config.selection.mode === 'sitemap'
        ? derivedIncludePrefixes(urls[0] ?? '')
        : [],
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
    return `${value} link ${value === 1 ? 'hop' : 'hops'}`;
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

/** The URLs a Website selection names, in order. */
export function selectionUrls(selection: WebsiteSelection): string[] {
  switch (selection.mode) {
    case 'url_list':
      return selection.urls;
    case 'single_url':
      return [selection.url];
    case 'crawl':
      return [selection.start_url];
    case 'sitemap':
      return [selection.sitemap_url];
  }
}

const httpUrl = (value: string) => {
  try {
    const url = new URL(value.trim());
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
};

const sitemapPath = (value: string) => {
  try {
    return /\.xml(\.gz)?$/i.test(new URL(value).pathname);
  } catch {
    return false;
  }
};

/**
 * The input a "Website address" names (spec 0011): several lines are a URL list, an
 * address ending in `.xml` or `.xml.gz` is a sitemap, and anything else is crawled.
 * A single page or a URL list stays so once the user chose that discovery.
 */
export function addressSelection(
  value: string,
  current: WebsiteSelection['mode'] = 'crawl',
): WebsiteSelection {
  const urls = value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (urls.length > 1 || current === 'url_list') {
    return { mode: 'url_list', urls };
  }
  const url = urls[0] ?? value.trim();
  if (current === 'single_url') {
    return { mode: 'single_url', url };
  }
  return sitemapPath(url)
    ? { mode: 'sitemap', sitemap_url: url }
    : { mode: 'crawl', start_url: url };
}

/** The selection with every URL a valid http(s) address, or null when one is not. */
export function analysableSelection(selection: WebsiteSelection): WebsiteSelection | null {
  const urls = selectionUrls(selection).map(httpUrl);
  if (urls.length === 0 || urls.some((url) => url === null)) {
    return null;
  }
  const valid = urls as string[];
  switch (selection.mode) {
    case 'url_list':
      return { mode: 'url_list', urls: valid };
    case 'single_url':
      return { mode: 'single_url', url: valid[0] };
    case 'crawl':
      return { mode: 'crawl', start_url: valid[0] };
    case 'sitemap':
      return { mode: 'sitemap', sitemap_url: valid[0] };
  }
}

/**
 * The input the address field shows: the analysed input while the draft uses the
 * discovery the recommendation switched to (a crawl read from the site's sitemap),
 * otherwise the draft's own selection.
 */
export function enteredSelection(
  config: WebsiteConfig,
  recommendation?: SettingRecommendation,
): WebsiteSelection {
  if (
    recommendation?.recommended &&
    selectionKey(config.selection) === selectionKey(recommendation.recommended.selection) &&
    selectionKey(config.selection) !== selectionKey(recommendation.inputs.selection)
  ) {
    return recommendation.inputs.selection;
  }
  return config.selection;
}

/** The status a reader sees: a succeeded analysis older than a day has expired. */
export function effectiveStatus(
  recommendation: SettingRecommendation,
  now = Date.now(),
): SettingRecommendation['status'] {
  if (
    recommendation.status === 'succeeded' &&
    new Date(recommendation.expires_at).getTime() <= now
  ) {
    return 'expired';
  }
  return recommendation.status;
}

/**
 * Whether a recommendation no longer describes the draft: the address changed, or the
 * other Website sources' page total that bounded its page limit changed.
 */
export function isStale(
  config: WebsiteConfig,
  recommendation: SettingRecommendation,
  otherSourcesMaxPages: number,
): boolean {
  return (
    !recommendationMatches(config, recommendation) ||
    recommendation.inputs.other_sources_max_pages !== otherSourcesMaxPages
  );
}

/** Every managed setting set back to the recommendation. */
export function resetToRecommended(
  config: WebsiteConfig,
  recommendation: SettingRecommendation,
): WebsiteConfig {
  if (!recommendation.recommended) {
    return config;
  }
  const next: WebsiteConfig = { ...config };
  for (const path of PREFILLED_PATHS) {
    Object.assign(next, { [path]: recommendedValue(recommendation, path) });
  }
  return next;
}

/** Labels of the managed settings, as the server names them in a recommendation. */
export const RECOMMENDATION_LABELS: Record<RecommendationPath, string> = {
  selection: 'Discovery',
  allowed_origins: 'Allowed sites',
  include_path_prefixes: 'Pages under',
  exclude_path_prefixes: 'Excluded',
  max_pages: 'Maximum pages',
  max_depth: 'Crawl depth',
  requests_per_second: 'Crawl speed',
};

export type WideningEdit = { path: RecommendationPath; label: string; consequence: string };

const joined = (values: string[]) => values.join(', ');

/**
 * Edits that widen the scope or the load beyond the recommendation (the high-risk
 * overrides of spec 0011), each with its consequence. Narrower edits are not listed.
 */
export function wideningEdits(
  config: WebsiteConfig,
  recommendation: SettingRecommendation,
): WideningEdit[] {
  const recommended = recommendation.recommended;
  if (!recommended) {
    return [];
  }
  const edits: WideningEdit[] = [];
  const add = (path: RecommendationPath, consequence: string) =>
    edits.push({ path, label: RECOMMENDATION_LABELS[path], consequence });
  if (
    recommended.selection.mode === 'single_url' &&
    (config.selection.mode === 'crawl' || config.selection.mode === 'sitemap')
  ) {
    add('selection', 'Pages beyond the one recommended page are discovered and fetched.');
  }
  const allowed = new Set(recommended.allowed_origins.map(originOf));
  const added = Array.from(new Set(config.allowed_origins.map(originOf))).filter(
    (origin) => !allowed.has(origin),
  );
  if (added.length) {
    add(
      'allowed_origins',
      `Pages from ${joined(added)} can also be fetched, and the analysis did not check that site.`,
    );
  }
  const scoped = config.selection.mode === 'crawl' || config.selection.mode === 'sitemap';
  const recommendedInclude = recommended.include_path_prefixes ?? [];
  const include = config.include_path_prefixes ?? [];
  if (scoped && recommendedInclude.length) {
    const outside = include.filter(
      (prefix) => !recommendedInclude.some((folder) => prefix.startsWith(folder)),
    );
    if (include.length === 0) {
      add(
        'include_path_prefixes',
        `Every path on the allowed sites can be fetched, not only pages under ${joined(recommendedInclude)}.`,
      );
    } else if (outside.length) {
      add(
        'include_path_prefixes',
        `Pages under ${joined(outside)} can be fetched, outside ${joined(recommendedInclude)}.`,
      );
    }
  }
  if (config.max_pages > recommended.max_pages) {
    add(
      'max_pages',
      `Up to ${config.max_pages} pages instead of ${recommended.max_pages}, so the run fetches more of the site and takes longer.`,
    );
  }
  if (config.requests_per_second > recommended.requests_per_second) {
    add(
      'requests_per_second',
      `${config.requests_per_second} requests per second is faster than the ${recommended.requests_per_second} recommended for this site, which may slow the site or get requests refused.`,
    );
  }
  return edits;
}

export type ProvenanceRow = {
  path: RecommendationPath;
  label: string;
  value: unknown;
  changed: boolean;
  recommended: unknown;
  rationale: string;
  rationaleCode: string;
};

/** Rows of a saved version's recommended settings, in the card's order. */
export function provenanceRows(node: SettingsProvenance['nodes'][string]): ProvenanceRow[] {
  return PREFILLED_PATHS.flatMap((path) => {
    const field: ProvenanceField | undefined = node.fields[path];
    if (!field) {
      return [];
    }
    const changed = field.basis === 'user';
    return [
      {
        path,
        label: RECOMMENDATION_LABELS[path],
        value: changed ? field.saved : field.recommended,
        changed,
        recommended: field.recommended,
        rationale: field.rationale,
        rationaleCode: field.rationale_code,
      },
    ];
  });
}
