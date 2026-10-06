import { sourceNodes } from '../../../src/features/ingestion-pipelines/editorModel';
import {
  addSite,
  checkSiteUrl,
  chunkSettings,
  customStages,
  estimatedChunks,
  guidedSites,
  loadGuidedDraft,
  newGuidedDraft,
  removeSite,
  resetSiteToShared,
  setChunk,
  setLayout,
  setSitePages,
  sourceProblems,
  storeGuidedDraft,
  type GuidedDraft,
} from '../../../src/features/ingestion-pipelines/guidedModel';
import { usesSourcesPanel } from '../../../src/features/ingestion-pipelines/sourcesView';

const embedding = {
  provider: 'test',
  model: 'embedding-v1',
  dimensions: 3,
  revision: 'revision-2',
  endpoint_id: 'endpoint-1',
};

function withSites(...urls: string[]): GuidedDraft {
  let guided = newGuidedDraft(embedding);
  for (const url of urls) {
    guided = { ...guided, draft: addSite(guided, url).draft };
  }
  return guided;
}

describe('guided ingestion setup model', () => {
  test('starts as a Website draft the sources-panel editor opens', () => {
    const guided = newGuidedDraft(embedding);
    expect(guided.step).toBe(1);
    expect(usesSourcesPanel(guided.draft)).toBe(true);
    expect(guidedSites(guided.draft)).toHaveLength(0);
    expect(sourceProblems(guided.draft)).toEqual(['Add at least one website.']);
  });

  test('the first site fills the placeholder; later sites join the shared chain', () => {
    const guided = withSites('https://docs.example.com/guide/', 'https://help.example.com/');
    const sources = sourceNodes(guided.draft);
    expect(sources).toHaveLength(2);
    expect(sources[0].config).toMatchObject({
      kind: 'website',
      selection: { mode: 'crawl', start_url: 'https://docs.example.com/guide/' },
      allowed_origins: ['https://docs.example.com'],
      include_path_prefixes: ['/guide/'],
      max_pages: 50,
    });
    const extract = guided.draft.execution.nodes.find((node) => node.type === 'extract')!;
    expect(guided.draft.execution.edges).toContainEqual({
      source: sources[1].id,
      target: extract.id,
    });
    expect(sourceProblems(guided.draft)).toEqual([]);
  });

  test('a sitemap address uses sitemap mode', () => {
    const guided = withSites('https://status.example.com/sitemap.xml');
    expect(sourceNodes(guided.draft)[0].config).toMatchObject({
      selection: { mode: 'sitemap', sitemap_url: 'https://status.example.com/sitemap.xml' },
    });
  });

  test('validates addresses, duplicates and the five-site limit', () => {
    const guided = withSites('https://a.example.com/');
    expect(checkSiteUrl(guided.draft, 'b.example.com')).toEqual({ url: 'https://b.example.com/' });
    expect(checkSiteUrl(guided.draft, 'https://a.example.com/')).toEqual({
      error: 'This address is already in the list.',
    });
    expect(checkSiteUrl(guided.draft, 'ftp://a.example.com/')).toHaveProperty('error');
    expect(checkSiteUrl(guided.draft, 'not a url at all')).toHaveProperty('error');
    expect(checkSiteUrl(guided.draft, 'https://exa_mple/')).toHaveProperty('error');
    expect(checkSiteUrl(guided.draft, 'https://user:pass@x.example.com/')).toHaveProperty('error');
    const full = withSites(...['a', 'b', 'c', 'd', 'e'].map((n) => `https://${n}.example.com/`));
    expect(checkSiteUrl(full.draft, 'https://f.example.com/')).toEqual({
      error: 'A pipeline can read at most 5 websites.',
    });
  });

  test('page limits count against the 2,500-page run limit', () => {
    let guided = withSites('https://a.example.com/', 'https://b.example.com/');
    const [first, second] = sourceNodes(guided.draft);
    guided = { ...guided, draft: setSitePages(guided.draft, first.id, 1000) };
    guided = { ...guided, draft: setSitePages(guided.draft, second.id, 1000) };
    expect(sourceProblems(guided.draft)).toEqual([]);
    const third = addSite(guided, 'https://c.example.com/');
    const over = setSitePages(third.draft, third.nodeId, 600);
    expect(sourceProblems(over)[0]).toMatch(/at most 2,500 pages/);
  });

  test('removing the last site leaves an empty placeholder', () => {
    const guided = withSites('https://a.example.com/', 'https://b.example.com/');
    const [first, second] = sourceNodes(guided.draft);
    const one = removeSite(guided.draft, first.id);
    expect(guidedSites(one).map((site) => site.id)).toEqual([second.id]);
    expect(guidedSites(removeSite(one, second.id))).toHaveLength(0);
  });

  test('one index per source names each index after its site', () => {
    const guided = withSites('https://docs.example.com/', 'https://help.example.com/');
    const draft = setLayout(
      { ...guided, draft: { ...guided.draft, name: 'Product' } },
      'per_source',
    );
    const names = draft.execution.nodes
      .filter((node) => node.type === 'publish_index')
      .map((node) => (node.type === 'publish_index' ? node.knowledge_set_name : ''));
    expect(names).toEqual(['Product · docs.example.com', 'Product · help.example.com']);
    expect(draft.execution.index_layout).toBe('per_source');
  });

  test('a per-site override stays custom until reset to the shared settings', () => {
    let guided = withSites('https://docs.example.com/', 'https://help.example.com/');
    guided = { ...guided, draft: setLayout(guided, 'per_source') };
    const [docs, help] = sourceNodes(guided.draft);
    guided = setChunk(guided, 1000, 100);
    guided = setChunk(guided, 400, 40, help.id);
    expect(chunkSettings(guided)).toEqual({ size: 1000, overlap: 100 });
    expect(chunkSettings(guided, docs.id)).toEqual({ size: 1000, overlap: 100 });
    expect(chunkSettings(guided, help.id)).toEqual({ size: 400, overlap: 40 });
    expect(customStages(guided, help.id)).toEqual(['chunk']);
    guided = setChunk(guided, 1200, 100);
    expect(chunkSettings(guided, help.id)).toEqual({ size: 400, overlap: 40 });
    guided = resetSiteToShared(guided, help.id);
    expect(customStages(guided, help.id)).toEqual([]);
    expect(chunkSettings(guided, help.id)).toEqual({ size: 1200, overlap: 100 });
  });

  test('chunk edits keep the hard maximum above the target and overlap below it', () => {
    const guided = setChunk(withSites('https://a.example.com/'), 300, 300);
    const chunk = guided.draft.execution.nodes.find((node) => node.type === 'chunk');
    expect(chunk).toMatchObject({ target_tokens: 300, maximum_tokens: 400, overlap_tokens: 280 });
  });

  test('estimates chunks from about 2,400 tokens per page', () => {
    const guided = withSites('https://a.example.com/');
    expect(estimatedChunks(guided.draft, 800, 100)).toBe(Math.round((50 * 2400) / 700));
  });

  test('stores and restores the draft per project', () => {
    const guided = withSites('https://a.example.com/');
    expect(storeGuidedDraft('project-1', { ...guided, step: 3 })).toBe(true);
    expect(loadGuidedDraft('project-1')).toEqual({ ...guided, step: 3 });
    expect(loadGuidedDraft('project-2')).toBeUndefined();
    sessionStorage.setItem('ingestion-guided:v1:project-3', '{not json');
    expect(loadGuidedDraft('project-3')).toBeUndefined();
  });
});
