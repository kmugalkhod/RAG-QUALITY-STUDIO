import {
  addWebsiteSourceBlocked,
  branchChain,
  branchIndexName,
  defaultIngestionDraft,
  defaultWebsite,
  derivedIncludePrefixes,
  indexLayout,
  maxWebsiteRunPages,
  maxWebsiteSources,
  removeSource,
  sourceNodes,
  websitePageTotal,
} from './editorModel';
import type { IngestionNode, IngestionPipelineDraft, WebsiteConfig } from './model';
import {
  addSharedWebsiteSource,
  customStagesOf,
  resetToShared,
  setSharedIndexLayout,
  sharedStage,
  sharedTargets,
  stageNodes,
  updateNodes,
  type CustomizedSources,
  type SharedStage,
} from './sourcesView';

/**
 * Spec 0003 guided setup. It edits an ordinary schema 2 Website ingestion draft with the
 * same helpers as the sources-panel editor, so the saved version is the one the canvas
 * editor would save. A source with an empty URL is the placeholder of a draft without
 * websites yet.
 */

export const guidedSteps = ['Sources', 'Output', 'Processing', 'Review', 'Run'] as const;
export type GuidedStep = 1 | 2 | 3 | 4 | 5;

export const pageLimit = { min: 10, max: 1000, step: 10 } as const;
export const chunkLimit = { min: 200, max: 2000, step: 100 } as const;
export const overlapLimit = { min: 0, max: 300, step: 20 } as const;
/** The Est. chunks figure assumes about this many tokens of text per page. */
export const tokensPerPageEstimate = 2400;

export type GuidedDraft = {
  version: 1;
  step: GuidedStep;
  draft: IngestionPipelineDraft;
  customized: CustomizedSources;
  /** Set once Save and publish created the pipeline, then the run or run group it started. */
  saved?: { pipelineId: string; versionId: string; runId?: string; groupId?: string };
};

type WebsiteSource = Extract<IngestionNode, { type: 'source' }> & { config: WebsiteConfig };

/** A new draft: the editor's default stages with one empty Website source. */
export function newGuidedDraft(
  embedding: Parameters<typeof defaultIngestionDraft>[0],
  capabilities?: Parameters<typeof defaultIngestionDraft>[2],
): GuidedDraft {
  const base = defaultIngestionDraft(embedding, [], capabilities);
  const source = sourceNodes(base)[0];
  const draft = withIndexNames(
    setSourceConfig({ ...base, name: 'Website knowledge' }, source.id, defaultWebsite()),
  );
  return { version: 1, step: 1, draft, customized: {} };
}

const storageKey = (projectId: string) => `ingestion-guided:v1:${projectId}`;

/** Configuration only (URLs and settings), never fetched content. */
export function loadGuidedDraft(projectId: string): GuidedDraft | undefined {
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey(projectId)) || 'null') as unknown;
    if (
      value &&
      typeof value === 'object' &&
      (value as GuidedDraft).version === 1 &&
      (value as GuidedDraft).draft?.kind === 'ingestion' &&
      [1, 2, 3, 4, 5].includes((value as GuidedDraft).step)
    ) {
      return value as GuidedDraft;
    }
  } catch {
    // An unreadable draft starts over.
  }
  return undefined;
}

/** Whether the draft was stored; storage can be full or blocked. */
export function storeGuidedDraft(projectId: string, value: GuidedDraft): boolean {
  try {
    sessionStorage.setItem(storageKey(projectId), JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function clearGuidedDraft(projectId: string) {
  try {
    sessionStorage.removeItem(storageKey(projectId));
  } catch {
    // Nothing stored.
  }
}

function websiteUrl(config: WebsiteConfig) {
  const selection = config.selection;
  return selection.mode === 'crawl'
    ? selection.start_url
    : selection.mode === 'sitemap'
      ? selection.sitemap_url
      : selection.mode === 'single_url'
        ? selection.url
        : (selection.urls[0] ?? '');
}

/** The Website sources that have a URL, in order. */
export function guidedSites(draft: IngestionPipelineDraft): WebsiteSource[] {
  return sourceNodes(draft).filter(
    (node): node is WebsiteSource =>
      node.config.kind === 'website' && websiteUrl(node.config).trim() !== '',
  );
}

export function siteUrl(site: WebsiteSource) {
  return websiteUrl(site.config);
}

export function siteHost(site: WebsiteSource) {
  try {
    return new URL(siteUrl(site)).host;
  } catch {
    return siteUrl(site);
  }
}

export function siteScope(config: WebsiteConfig) {
  const mode = config.selection.mode;
  if (mode === 'sitemap') {
    return 'Sitemap';
  }
  if (mode === 'crawl') {
    return `Crawl · ${config.max_depth} ${config.max_depth === 1 ? 'link' : 'links'} deep`;
  }
  return mode === 'single_url' ? 'One page' : 'URL list';
}

/** Why a URL cannot be added, or null with the normalized URL. */
export function checkSiteUrl(
  draft: IngestionPipelineDraft,
  value: string,
): { error: string } | { url: string } {
  const text = value.trim();
  if (!text || /\s/.test(text)) {
    return { error: 'Enter a website address such as https://www.example.com/.' };
  }
  let parsed: URL;
  try {
    parsed = new URL(/^[a-z][a-z0-9+.-]*:/i.test(text) ? text : `https://${text}`);
  } catch {
    return { error: 'Enter a website address such as https://www.example.com/.' };
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return { error: 'Only http and https addresses can be read.' };
  }
  // The URL parser accepts and escapes odd host names; require a plain DNS name or address.
  if (!/^[a-z0-9-]+(?:\.[a-z0-9-]+)+$/i.test(parsed.hostname) && parsed.hostname !== 'localhost') {
    return { error: 'Enter a website address such as https://www.example.com/.' };
  }
  if (parsed.username || parsed.password) {
    return { error: 'Website addresses cannot contain a user name or password.' };
  }
  const sites = guidedSites(draft);
  if (sites.length >= maxWebsiteSources) {
    return { error: `A pipeline can read at most ${maxWebsiteSources} websites.` };
  }
  if (sites.some((site) => siteUrl(site) === parsed.toString())) {
    return { error: 'This address is already in the list.' };
  }
  return { url: parsed.toString() };
}

/** A Website config for one start URL, derived the way the editor's source settings do. */
export function websiteConfigFor(url: string, maxPages = 50): WebsiteConfig {
  const sitemap = /\.xml(?:$|[?#])/i.test(new URL(url).pathname);
  const selection: WebsiteConfig['selection'] = sitemap
    ? { mode: 'sitemap', sitemap_url: url }
    : { mode: 'crawl', start_url: url };
  return {
    ...defaultWebsite(),
    selection,
    allowed_origins: [new URL(url).origin],
    include_path_prefixes: derivedIncludePrefixes(url),
    max_pages: maxPages,
  };
}

function setSourceConfig(
  draft: IngestionPipelineDraft,
  sourceId: string,
  config: WebsiteConfig,
): IngestionPipelineDraft {
  return updateNodes(draft, [sourceId], (node) =>
    node.type === 'source' ? { ...node, config } : node,
  );
}

/** Index names follow the pipeline name: one shared name, or one per website. */
export function withIndexNames(draft: IngestionPipelineDraft): IngestionPipelineDraft {
  const name = draft.name.trim() || 'Ingested knowledge';
  if (indexLayout(draft) !== 'per_source') {
    const publish = draft.execution.nodes.find((node) => node.type === 'publish_index');
    return publish
      ? updateNodes(draft, [publish.id], (node) =>
          node.type === 'publish_index' ? { ...node, knowledge_set_name: name } : node,
        )
      : draft;
  }
  let next = draft;
  sourceNodes(draft).forEach((source, index) => {
    const publish = branchChain(draft, source.id).find((node) => node.type === 'publish_index');
    if (publish) {
      next = updateNodes(next, [publish.id], (node) =>
        node.type === 'publish_index'
          ? { ...node, knowledge_set_name: branchIndexName(draft, source, index + 1) }
          : node,
      );
    }
  });
  return next;
}

export function addSite(
  guided: GuidedDraft,
  url: string,
): { draft: IngestionPipelineDraft; nodeId: string } {
  const { draft, customized } = guided;
  const sources = sourceNodes(draft);
  if (sources.length === 1 && guidedSites(draft).length === 0) {
    return {
      draft: withIndexNames(setSourceConfig(draft, sources[0].id, websiteConfigFor(url))),
      nodeId: sources[0].id,
    };
  }
  if (addWebsiteSourceBlocked(draft)) {
    return { draft, nodeId: '' };
  }
  const added = addSharedWebsiteSource(draft, customized);
  return {
    draft: withIndexNames(setSourceConfig(added.draft, added.nodeId, websiteConfigFor(url))),
    nodeId: added.nodeId,
  };
}

export function removeSite(draft: IngestionPipelineDraft, sourceId: string) {
  if (sourceNodes(draft).length > 1) {
    return withIndexNames(removeSource(draft, sourceId));
  }
  return setSourceConfig(draft, sourceId, defaultWebsite());
}

export function setSitePages(draft: IngestionPipelineDraft, sourceId: string, pages: number) {
  return updateNodes(draft, [sourceId], (node) =>
    node.type === 'source' && node.config.kind === 'website'
      ? { ...node, config: { ...node.config, max_pages: pages } }
      : node,
  );
}

export function setLayout(guided: GuidedDraft, layout: 'merged' | 'per_source') {
  return withIndexNames(setSharedIndexLayout(guided.draft, layout, guided.customized));
}

export function pageTotal(draft: IngestionPipelineDraft) {
  return guidedSites(draft).length ? websitePageTotal(draft) : 0;
}

/** Problems that block leaving the Sources step, in the order a user can fix them. */
export function sourceProblems(draft: IngestionPipelineDraft): string[] {
  const problems: string[] = [];
  if (!guidedSites(draft).length) {
    problems.push('Add at least one website.');
  }
  if (pageTotal(draft) > maxWebsiteRunPages) {
    problems.push(
      `Lower the page limits: a run can read at most ${maxWebsiteRunPages.toLocaleString()} pages.`,
    );
  }
  return problems;
}

type SectionChunk = Extract<IngestionNode, { type: 'chunk'; algorithm: 'section_token' }>;

function sectionChunk(node: IngestionNode | undefined): SectionChunk | undefined {
  return node?.type === 'chunk' && node.algorithm === 'section_token' ? node : undefined;
}

/** Chunk size and overlap of the shared settings, or of one website's own branch. */
export function chunkSettings(
  guided: GuidedDraft,
  sourceId?: string,
): { size: number; overlap: number } | undefined {
  const node = sourceId
    ? stageNodes(guided.draft, 'chunk').find((entry) => entry.sourceId === sourceId)?.node
    : sharedStage(guided.draft, 'chunk', guided.customized).node;
  const chunk = sectionChunk(node);
  return chunk ? { size: chunk.target_tokens, overlap: chunk.overlap_tokens } : undefined;
}

/** The hard maximum keeps the default draft's ratio (800 for a 600-token target). */
export const maximumFor = (size: number) => Math.round((size * 4) / 3);

function withChunk(node: IngestionNode, size: number, overlap: number): IngestionNode {
  const chunk = sectionChunk(node);
  if (!chunk) {
    return node;
  }
  return {
    ...chunk,
    target_tokens: size,
    maximum_tokens: maximumFor(size),
    overlap_tokens: Math.min(overlap, size - overlapLimit.step),
  };
}

/** Applies a stage edit to the shared settings, or to one website as an override. */
export function editStage(
  guided: GuidedDraft,
  stage: SharedStage,
  update: (node: IngestionNode) => IngestionNode,
  sourceId?: string,
): GuidedDraft {
  if (sourceId) {
    const target = stageNodes(guided.draft, stage).find((entry) => entry.sourceId === sourceId);
    if (!target) {
      return guided;
    }
    const marked = guided.customized[stage] ?? [];
    return {
      ...guided,
      draft: updateNodes(guided.draft, [target.node.id], update),
      customized: {
        ...guided.customized,
        [stage]: marked.includes(sourceId) ? marked : [...marked, sourceId],
      },
    };
  }
  return {
    ...guided,
    draft: updateNodes(guided.draft, sharedTargets(guided.draft, stage, guided.customized), update),
  };
}

export function setChunk(guided: GuidedDraft, size: number, overlap: number, sourceId?: string) {
  return editStage(guided, 'chunk', (node) => withChunk(node, size, overlap), sourceId);
}

/** Drops every override of one website, copying the shared settings back. */
export function resetSiteToShared(guided: GuidedDraft, sourceId: string): GuidedDraft {
  let draft = guided.draft;
  const customized = { ...guided.customized };
  for (const stage of customStagesOf(guided.draft, sourceId, guided.customized)) {
    draft = resetToShared(draft, stage, sourceId, customized);
    customized[stage] = (customized[stage] ?? []).filter((id) => id !== sourceId);
  }
  return { ...guided, draft, customized };
}

export function customStages(guided: GuidedDraft, sourceId: string) {
  return indexLayout(guided.draft) === 'per_source'
    ? customStagesOf(guided.draft, sourceId, guided.customized)
    : [];
}

/** An estimate: pages × about 2,400 tokens, divided by the new text per chunk. */
export function estimatedChunks(draft: IngestionPipelineDraft, size: number, overlap: number) {
  return Math.round((pageTotal(draft) * tokensPerPageEstimate) / Math.max(100, size - overlap));
}
