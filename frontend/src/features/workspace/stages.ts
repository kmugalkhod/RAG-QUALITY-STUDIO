import { allPages } from '../../lib/pagination';
import { listDocuments } from '../documents/api';
import { listIndexes } from '../documents/indexApi';
import { listDatasets, listExperiments } from '../experiments/api';
import { listPipelines } from '../pipelines/api';

// The three Overview stages and where each count comes from (spec 0002, AC-6, Value sourcing).

export type StageId = 'prepare' | 'ask' | 'compare';
export type StageState = 'empty' | 'in-progress' | 'ready';

export type StageSummary = {
  state: StageState;
  /** The count line, for example "3 documents · 1 ready index". */
  counts: string;
  /** Short status text shown next to the title. */
  status: string;
};

function plural(count: number, one: string, many: string) {
  return `${count} ${count === 1 ? one : many}`;
}

export async function loadPrepareStage(projectId: string): Promise<StageSummary> {
  const [documents, indexes] = await Promise.all([
    listDocuments(projectId),
    allPages((offset) => listIndexes(projectId, offset)),
  ]);
  // A published index is one whose build succeeded; the index API has no separate "ready".
  const ready = indexes.filter((index) => index.status === 'succeeded').length;
  const counts = `${plural(documents.total, 'document', 'documents')} · ${plural(ready, 'ready index', 'ready indexes')}`;
  // A ready index wins, so knowledge published by an ingestion pipeline without uploads
  // still counts as prepared.
  if (ready) {
    return { state: 'ready', counts, status: 'Ready' };
  }
  if (!documents.total) {
    return { state: 'empty', counts, status: 'No documents' };
  }
  return { state: 'in-progress', counts, status: 'Needs indexing' };
}

export async function loadAskStage(projectId: string): Promise<StageSummary> {
  const pipelines = await listPipelines(projectId, 'answer');
  const counts = plural(pipelines.total, 'answer pipeline', 'answer pipelines');
  return pipelines.total
    ? { state: 'ready', counts, status: 'Ready' }
    : { state: 'empty', counts, status: 'No pipelines' };
}

export async function loadCompareStage(projectId: string): Promise<StageSummary> {
  const [datasets, experiments] = await Promise.all([
    listDatasets(projectId),
    allPages((offset) => listExperiments(projectId, offset)),
  ]);
  const completed = experiments.filter((experiment) => experiment.status === 'succeeded').length;
  const counts = `${plural(datasets.total, 'dataset', 'datasets')} · ${plural(completed, 'completed run', 'completed runs')}`;
  if (completed) {
    return { state: 'ready', counts, status: 'Ready' };
  }
  if (!datasets.total) {
    return { state: 'empty', counts, status: 'No datasets' };
  }
  return { state: 'in-progress', counts, status: 'No completed runs' };
}

export type StageResult =
  | { status: 'loading' }
  | { status: 'failed'; message: string }
  | { status: 'loaded'; summary: StageSummary };

/**
 * Which stage carries the one primary button: none until every request has settled, then
 * the first loaded stage that is not ready, else Compare.
 */
export function primaryStage(results: Record<StageId, StageResult>): StageId | null {
  const order: StageId[] = ['prepare', 'ask', 'compare'];
  if (order.some((id) => results[id].status === 'loading')) {
    return null;
  }
  const next = order.find((id) => {
    const result = results[id];
    return result.status === 'loaded' && result.summary.state !== 'ready';
  });
  if (next) {
    return next;
  }
  return results.compare.status === 'loaded' ? 'compare' : null;
}
