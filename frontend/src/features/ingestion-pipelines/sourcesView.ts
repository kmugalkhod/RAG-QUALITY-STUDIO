import {
  addWebsiteSource,
  branchChain,
  indexLayout,
  setIndexLayout,
  sourceNodes,
} from './editorModel';
import type { IngestionNodeExecutionStatus } from './executionState';
import {
  canonicalIngestion,
  type IngestionNode,
  type IngestionPipelineDraft,
  type IngestionRun,
  type IngestionRunGroup,
} from './model';

/**
 * The sources-panel editor presents a Website pipeline as its sources plus one shared set of
 * stages. A one-index-per-source version still saves a complete chain per source; this module
 * derives the shared settings of each stage and which sources customize it.
 */

export const sharedStageTypes = ['extract', 'clean', 'chunk', 'embed'] as const;
export type SharedStage = (typeof sharedStageTypes)[number];
export type ViewStage = SharedStage | 'publish_index';
/** Sources marked customized in this editing session, per stage. */
export type CustomizedSources = Partial<Record<SharedStage, string[]>>;

const stageViewIds: Record<ViewStage, string> = {
  extract: 'view:extract',
  clean: 'view:clean',
  chunk: 'view:chunk',
  embed: 'view:embed',
  publish_index: 'view:publish',
};
const indexViewPrefix = 'view:index:';

export const stageViewId = (stage: ViewStage) => stageViewIds[stage];
export const indexViewId = (sourceId: string) => `${indexViewPrefix}${sourceId}`;

/** The stage a canvas or stage-menu selection stands for, if it is one. */
export function viewStageOf(selection: string): ViewStage | undefined {
  if (selection.startsWith(indexViewPrefix)) {
    return 'publish_index';
  }
  return (Object.entries(stageViewIds) as [ViewStage, string][]).find(
    ([, id]) => id === selection,
  )?.[0];
}

/** The source a `view:index:<source>` selection belongs to. */
export function indexSourceOf(selection: string): string | undefined {
  return selection.startsWith(indexViewPrefix)
    ? selection.slice(indexViewPrefix.length)
    : undefined;
}

/** Website pipelines on schema 2 use the sources panel; others keep the per-node editor. */
export function usesSourcesPanel(draft: IngestionPipelineDraft) {
  const first = sourceNodes(draft)[0];
  return draft.execution.schema_version === 2 && first?.config.kind === 'website';
}

function settingsKey(node: IngestionNode) {
  const { id: _id, ...settings } = node;
  void _id;
  return canonicalIngestion(
    Object.fromEntries(Object.entries(settings).filter(([, value]) => value !== undefined)),
  );
}

/** One stage's node for each source, in source order. */
export function stageNodes(
  draft: IngestionPipelineDraft,
  stage: ViewStage,
): { sourceId: string; node: IngestionNode }[] {
  return sourceNodes(draft).flatMap((source) => {
    const node =
      indexLayout(draft) === 'per_source'
        ? branchChain(draft, source.id).find((candidate) => candidate.type === stage)
        : draft.execution.nodes.find((candidate) => candidate.type === stage);
    return node ? [{ sourceId: source.id, node }] : [];
  });
}

/**
 * The shared settings of a stage and the sources that customize it. Shared settings are the
 * ones most sources use (ties go to the earliest source), ignoring sources marked customized.
 */
export function sharedStage(
  draft: IngestionPipelineDraft,
  stage: SharedStage,
  customized: CustomizedSources = {},
): { node: IngestionNode | undefined; custom: string[] } {
  const entries = stageNodes(draft, stage);
  if (indexLayout(draft) !== 'per_source') {
    return { node: entries[0]?.node, custom: [] };
  }
  const marked = new Set(customized[stage] ?? []);
  const candidates = entries.filter((entry) => !marked.has(entry.sourceId));
  const pool = candidates.length ? candidates : entries;
  const counts = new Map<string, number>();
  for (const entry of pool) {
    const key = settingsKey(entry.node);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const best = Math.max(0, ...counts.values());
  const shared = pool.find((entry) => counts.get(settingsKey(entry.node)) === best);
  const sharedKey = shared ? settingsKey(shared.node) : '';
  return {
    node: shared?.node,
    custom: entries
      .filter((entry) => marked.has(entry.sourceId) || settingsKey(entry.node) !== sharedKey)
      .map((entry) => entry.sourceId),
  };
}

/** The shared stages a source customizes, in pipeline order. */
export function customStagesOf(
  draft: IngestionPipelineDraft,
  sourceId: string,
  customized: CustomizedSources = {},
): SharedStage[] {
  return sharedStageTypes.filter((stage) =>
    sharedStage(draft, stage, customized).custom.includes(sourceId),
  );
}

/** Applies a node update to several nodes at once. */
export function updateNodes(
  draft: IngestionPipelineDraft,
  ids: string[],
  update: (node: IngestionNode) => IngestionNode,
): IngestionPipelineDraft {
  const targets = new Set(ids);
  return {
    ...draft,
    execution: {
      ...draft.execution,
      nodes: draft.execution.nodes.map((node) => (targets.has(node.id) ? update(node) : node)),
    },
  };
}

/** The node ids a shared edit of a stage changes: every source that does not customize it. */
export function sharedTargets(
  draft: IngestionPipelineDraft,
  stage: SharedStage,
  customized: CustomizedSources = {},
) {
  const { custom } = sharedStage(draft, stage, customized);
  return stageNodes(draft, stage)
    .filter((entry) => !custom.includes(entry.sourceId))
    .map((entry) => entry.node.id);
}

/** A copy of `template`'s settings under `target`'s id. */
export function withSettingsOf(target: IngestionNode, template: IngestionNode): IngestionNode {
  return { ...structuredClone(template), id: target.id } as IngestionNode;
}

/** Copies the shared settings of a stage back onto one source's branch. */
export function resetToShared(
  draft: IngestionPipelineDraft,
  stage: SharedStage,
  sourceId: string,
  customized: CustomizedSources = {},
): IngestionPipelineDraft {
  const others = {
    ...customized,
    [stage]: (customized[stage] ?? []).filter((id) => id !== sourceId),
  };
  const shared = sharedStage(draft, stage, {
    ...others,
    [stage]: [...(others[stage] ?? []), sourceId],
  }).node;
  const target = stageNodes(draft, stage).find((entry) => entry.sourceId === sourceId)?.node;
  if (!shared || !target) {
    return draft;
  }
  return updateNodes(draft, [target.id], (node) => withSettingsOf(node, shared));
}

/** Adds a Website source; in a per-source layout its stages copy the shared settings. */
export function addSharedWebsiteSource(
  draft: IngestionPipelineDraft,
  customized: CustomizedSources = {},
): { draft: IngestionPipelineDraft; nodeId: string } {
  const added = addWebsiteSource(draft);
  if (indexLayout(draft) !== 'per_source') {
    return added;
  }
  let next = added.draft;
  for (const stage of sharedStageTypes) {
    const shared = sharedStage(draft, stage, customized).node;
    const target = branchChain(next, added.nodeId).find((node) => node.type === stage);
    if (shared && target) {
      next = updateNodes(next, [target.id], (node) => withSettingsOf(node, shared));
    }
  }
  return { draft: next, nodeId: added.nodeId };
}

/** Switches the index layout; going back to one index keeps the shared settings. */
export function setSharedIndexLayout(
  draft: IngestionPipelineDraft,
  layout: 'merged' | 'per_source',
  customized: CustomizedSources = {},
): IngestionPipelineDraft {
  let next = setIndexLayout(draft, layout);
  if (layout !== 'merged' || next === draft) {
    return next;
  }
  for (const stage of sharedStageTypes) {
    const shared = sharedStage(draft, stage, customized).node;
    const target = next.execution.nodes.find((node) => node.type === stage);
    if (shared && target) {
      next = updateNodes(next, [target.id], (node) => withSettingsOf(node, shared));
    }
  }
  return next;
}

const statePriority: IngestionNodeExecutionStatus[] = [
  'running',
  'failed',
  'queued',
  'cancelled',
  'succeeded',
];

/** One state for several nodes: the most urgent one any of them is in. */
export function combinedState(
  states: (IngestionNodeExecutionStatus | undefined)[],
): IngestionNodeExecutionStatus | undefined {
  const present = states.filter((state): state is IngestionNodeExecutionStatus => !!state);
  if (!present.length) {
    return undefined;
  }
  if (present.every((state) => state === 'succeeded')) {
    return 'succeeded';
  }
  return statePriority.find((state) => state !== 'succeeded' && present.includes(state));
}

export type ViewCard = {
  id: string;
  stage: IngestionNode['type'];
  label: string;
  detail: string;
  position: { x: number; y: number };
  first: boolean;
  last: boolean;
  /** Real node ids this card stands for, for execution states. */
  members: string[];
};

const rowHeight = 116;
const columnWidth = 340;

/**
 * Canvas cards for the sources-panel editor: the sources once, every stage once, and in a
 * per-source layout one card per source index after Publish.
 */
export function sourcesViewCards(
  draft: IngestionPipelineDraft,
  describe: (node: IngestionNode) => string,
  customized: CustomizedSources = {},
): { cards: ViewCard[]; edges: { source: string; target: string }[] } {
  const sources = sourceNodes(draft);
  const perSource = indexLayout(draft) === 'per_source';
  const cards: ViewCard[] = [
    {
      // Cards reuse a real node id, so selections and tests address them as before.
      id: sources[0]?.id ?? 'source',
      stage: 'source',
      label: sources.length === 1 ? 'Website source' : `${sources.length} website sources`,
      detail: sources.length === 1 ? describe(sources[0]) : sources.map(describe).join(' · '),
      position: { x: 0, y: 0 },
      first: true,
      last: false,
      members: sources.map((source) => source.id),
    },
  ];
  const stages: ViewStage[] = [...sharedStageTypes, 'publish_index'];
  stages.forEach((stage, index) => {
    const entries = stageNodes(draft, stage);
    const shared = stage === 'publish_index' ? undefined : sharedStage(draft, stage, customized);
    const representative = shared?.node ?? entries[0]?.node;
    const customCount = shared?.custom.length ?? 0;
    const base = representative ? describe(representative) : '';
    cards.push({
      id: entries[0]?.node.id ?? stageViewId(stage),
      stage,
      label:
        stage === 'publish_index'
          ? perSource
            ? `Publish ${entries.length} indexes`
            : 'Publish index'
          : { extract: 'Extract', clean: 'Clean', chunk: 'Chunk', embed: 'Embed' }[stage],
      detail:
        stage === 'publish_index' && perSource
          ? 'One index per source'
          : customCount
            ? `${customCount === 1 ? '1 source customizes this' : `${customCount} sources customize this`} · ${base}`
            : base,
      position: { x: 0, y: (index + 1) * rowHeight },
      first: false,
      last: !perSource && stage === 'publish_index',
      members: entries.map((entry) => entry.node.id),
    });
  });
  const edges = cards.slice(1).map((card, index) => ({ source: cards[index].id, target: card.id }));
  if (perSource) {
    const publish = stageNodes(draft, 'publish_index');
    publish.forEach((entry, index) => {
      const id = indexViewId(entry.sourceId);
      cards.push({
        id,
        stage: 'publish_index',
        label: entry.node.type === 'publish_index' ? entry.node.knowledge_set_name : 'Index',
        detail: describe(sources.find((source) => source.id === entry.sourceId) ?? entry.node),
        position: {
          x: (index - (publish.length - 1) / 2) * columnWidth,
          y: (stages.length + 1) * rowHeight,
        },
        first: false,
        last: true,
        members: [entry.node.id],
      });
      edges.push({ source: cards[sharedStageTypes.length + 1].id, target: id });
    });
  }
  return { cards, edges };
}

export type SourceRunStatus = {
  /** A StatusBadge tone. */
  tone: 'succeeded' | 'running' | 'queued' | 'failed' | 'cancelled';
  label: string;
  detail: string;
};

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`;

/** What the latest run did for one source: its own branch run, or its share of a merged run. */
export function sourceRunStatus(
  sourceId: string,
  run: IngestionRun | undefined,
  group: IngestionRunGroup | undefined,
): SourceRunStatus | undefined {
  const branch = group?.runs.find((candidate) => candidate.branch_source_node_id === sourceId);
  const current = group ? branch : run;
  if (!current) {
    return undefined;
  }
  if (current.status === 'queued' || current.status === 'running') {
    return {
      tone: current.status,
      label: current.status === 'queued' ? 'Queued' : 'Running',
      detail: `${current.progress}% · ${plural(current.discovered_count, 'page')} found so far`,
    };
  }
  const outcome = current.source_outcomes?.find(
    (candidate) => candidate.source_node_id === sourceId,
  );
  // A merged run that reports per-source outcomes but none for this source never read it
  // (for example a source added after that run).
  if (!group && !outcome && (current.source_outcomes?.length ?? 0) > 0) {
    return undefined;
  }
  if (current.status === 'cancelled') {
    return { tone: 'cancelled', label: 'Cancelled', detail: 'The last run was cancelled.' };
  }
  if (outcome?.status === 'failed' || (current.status === 'failed' && (!outcome || group))) {
    const kept = outcome?.carried_forward_count ?? 0;
    return {
      tone: 'failed',
      label: 'Failed',
      detail: [
        outcome?.message ?? current.error ?? 'The last run failed.',
        kept ? `${plural(kept, 'page')} kept from earlier` : '',
      ]
        .filter(Boolean)
        .join(' · '),
    };
  }
  if (outcome?.status === 'skipped') {
    return {
      tone: 'cancelled',
      label: 'Not refreshed',
      detail: `${plural(outcome.carried_forward_count, 'page')} kept from earlier`,
    };
  }
  const included =
    outcome?.included_count ?? current.new_count + current.changed_count + current.unchanged_count;
  const details = [`${plural(included, 'page')} included`];
  if (outcome?.failed_count) {
    details.push(`${outcome.failed_count} failed`);
  }
  if (outcome?.carried_forward_count) {
    details.push(`${outcome.carried_forward_count} kept from earlier`);
  }
  return {
    tone: outcome?.status === 'partial' ? 'failed' : 'succeeded',
    label: outcome?.status === 'partial' ? 'Partly collected' : group ? 'Published' : 'Collected',
    detail: details.join(' · '),
  };
}
