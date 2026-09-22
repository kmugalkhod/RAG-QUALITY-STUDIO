import type { IngestionNode, IngestionRun } from './model';

export type IngestionNodeExecutionStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export function ingestionRunDisplayStatus(run: IngestionRun): IngestionNodeExecutionStatus {
  if (run.status === 'succeeded' || run.status === 'failed' || run.status === 'cancelled') {
    return run.status;
  }

  const nodeStatuses = run.node_states?.map((state) => state.status) ?? [];
  if (nodeStatuses.includes('failed')) {
    return 'failed';
  }
  if (nodeStatuses.includes('cancelled')) {
    return 'cancelled';
  }
  if (nodeStatuses.includes('running')) {
    return 'running';
  }
  return run.status;
}

const checkpointNodeType = (run: IngestionRun): IngestionNode['type'] => {
  if (run.stage === 'discovering') {
    return 'source';
  }
  if (run.stage === 'processing') {
    return 'extract';
  }
  if (run.stage === 'indexing') {
    return run.chunk_count > 0 && run.embedded_count >= run.chunk_count ? 'publish_index' : 'embed';
  }
  return 'publish_index';
};

/**
 * Projects the backend's durable run checkpoint onto the saved linear graph.
 * The backend reports processing as one checkpoint, so Extract represents that
 * active checkpoint until the run advances to indexing. No client timer or
 * synthetic progress is used to advance node state.
 */
export function ingestionNodeExecutionStates(
  run: IngestionRun | undefined,
  nodes: IngestionNode[],
): Record<string, IngestionNodeExecutionStatus | undefined> {
  if (!run) {
    return Object.fromEntries(nodes.map((node) => [node.id, undefined]));
  }

  if (run.node_states?.length) {
    const persisted = new Map(run.node_states.map((state) => [state.node_id, state.status]));
    return Object.fromEntries(nodes.map((node) => [node.id, persisted.get(node.id)]));
  }

  // Compatibility for runs created before per-node checkpoints were introduced.
  if (run.status === 'succeeded') {
    return Object.fromEntries(nodes.map((node) => [node.id, 'succeeded']));
  }

  const checkpointType = checkpointNodeType(run);
  const checkpointIndex = Math.max(
    0,
    nodes.findIndex((node) => node.type === checkpointType),
  );
  const checkpointStatus: IngestionNodeExecutionStatus = run.status;

  return Object.fromEntries(
    nodes.map((node, index) => [
      node.id,
      index < checkpointIndex
        ? 'succeeded'
        : index === checkpointIndex
          ? checkpointStatus
          : 'queued',
    ]),
  );
}
