import { createDefaultRetrievalSettings, getNodeRetrievalSettings } from '../../lib/retrieval';
import {
  pipelineNodeOrder,
  RERANK_CANDIDATES_DEFAULT,
  type PipelineDraft,
  type PipelineNodeConfig,
  type PipelineNodeKind,
  type PipelineOptions,
} from './model';

export function createNode(kind: PipelineNodeKind, options?: PipelineOptions): PipelineNodeConfig {
  const node = { id: kind, type: kind };
  switch (kind) {
    case 'retriever':
      return { ...node, index_id: '', retrieval: createDefaultRetrievalSettings() };
    case 'prompt':
      return {
        ...node,
        template:
          options?.template ??
          'Answer the question completely.\nQuestion: {question}\nRetrieved context: {context}',
        answer_policy: 'complete-v2',
      };
    case 'rerank':
      return {
        ...node,
        model: options?.rerank?.default_model ?? options?.default_model ?? options?.models[0] ?? '',
        top_n: options?.rerank?.top_n ?? 5,
      };
    case 'llm':
      return {
        ...node,
        model: options?.default_model ?? options?.models[0] ?? '',
        max_tokens: options?.max_tokens ?? 1024,
        temperature: 0,
      };
    default:
      return node;
  }
}

export function createPipelineDraft(
  options: PipelineOptions | undefined,
  name: string,
  indexId = '',
  topK = 5,
): PipelineDraft {
  const nodes = pipelineNodeOrder.map((kind) => {
    const node = createNode(kind, options);
    return kind === 'retriever'
      ? { ...node, index_id: indexId, retrieval: createDefaultRetrievalSettings(topK) }
      : node;
  });
  return {
    name,
    execution: {
      schema_version: 2,
      nodes,
      edges: pipelineNodeOrder
        .slice(1)
        .map((kind, index) => ({ source: pipelineNodeOrder[index], target: kind })),
    },
    layout: {
      positions: Object.fromEntries(
        nodes.map((node, index) => [node.id, { x: 80, y: 40 + index * 116 }]),
      ),
    },
  };
}

// A graph being edited: node settings, connections and canvas positions.
export type GraphStep = {
  nodes: PipelineNodeConfig[];
  edges: { source: string; target: string }[];
  positions: Record<string, { x: number; y: number }>;
};
const STEP_Y = 116;
const STEP_X = 240;

function isVertical(positions: GraphStep['positions']) {
  const values = Object.values(positions);
  if (values.length < 2) {
    return true;
  }
  const spread = (axis: 'x' | 'y') =>
    Math.max(...values.map((p) => p[axis])) - Math.min(...values.map((p) => p[axis]));
  return spread('y') >= spread('x');
}

function withTopK(node: PipelineNodeConfig, topK: number): PipelineNodeConfig {
  const retrieval = getNodeRetrievalSettings(node);
  const next = { ...node, retrieval: { ...retrieval, top_k: topK } };
  delete next.top_k;
  return next;
}

// Inserts the Rerank node between Retriever and Prompt (spec 0015). The Retriever's
// Top k becomes the candidates the step reads: 30 by default, never fewer than before.
export function addRerankStep(step: GraphStep, options?: PipelineOptions): GraphStep {
  const retriever = step.nodes.find((node) => node.type === 'retriever');
  const prompt = step.nodes.find((node) => node.type === 'prompt');
  if (!retriever || !prompt || step.nodes.some((node) => node.type === 'rerank')) {
    return step;
  }
  const rerank = createNode('rerank', options);
  const candidates = Math.min(
    50,
    Math.max(
      getNodeRetrievalSettings(retriever).top_k,
      options?.rerank?.candidates ?? RERANK_CANDIDATES_DEFAULT,
    ),
  );
  const vertical = isVertical(step.positions);
  const slot = step.positions[prompt.id] ?? { x: 80, y: 40 + 2 * STEP_Y };
  const positions = Object.fromEntries(
    Object.entries(step.positions).map(([id, p]) => [
      id,
      vertical
        ? p.y >= slot.y
          ? { ...p, y: p.y + STEP_Y }
          : p
        : p.x >= slot.x
          ? { ...p, x: p.x + STEP_X }
          : p,
    ]),
  );
  positions[rerank.id] = { ...slot };
  const index = step.nodes.indexOf(retriever) + 1;
  return {
    nodes: [
      ...step.nodes
        .slice(0, index)
        .map((node) => (node === retriever ? withTopK(node, candidates) : node)),
      rerank,
      ...step.nodes.slice(index),
    ],
    edges: [
      ...step.edges.filter((edge) => !(edge.source === retriever.id && edge.target === prompt.id)),
      { source: retriever.id, target: rerank.id },
      { source: rerank.id, target: prompt.id },
    ],
    positions,
  };
}

// Removes the Rerank node and reconnects Retriever → Prompt. The Retriever then
// supplies as many passages as the step kept, so the prompt sees the same amount.
export function removeRerankStep(step: GraphStep): GraphStep {
  const rerank = step.nodes.find((node) => node.type === 'rerank');
  const retriever = step.nodes.find((node) => node.type === 'retriever');
  const prompt = step.nodes.find((node) => node.type === 'prompt');
  if (!rerank) {
    return step;
  }
  const vertical = isVertical(step.positions);
  const slot = step.positions[rerank.id];
  const positions = Object.fromEntries(
    Object.entries(step.positions)
      .filter(([id]) => id !== rerank.id)
      .map(([id, p]) => [
        id,
        !slot
          ? p
          : vertical
            ? p.y > slot.y
              ? { ...p, y: p.y - STEP_Y }
              : p
            : p.x > slot.x
              ? { ...p, x: p.x - STEP_X }
              : p,
      ]),
  );
  const keep = Number.isInteger(rerank.top_n) ? (rerank.top_n as number) : 5;
  return {
    nodes: step.nodes
      .filter((node) => node !== rerank)
      .map((node) => (node === retriever ? withTopK(node, Math.max(1, Math.min(50, keep))) : node)),
    edges: [
      ...step.edges.filter((edge) => edge.source !== rerank.id && edge.target !== rerank.id),
      ...(retriever && prompt ? [{ source: retriever.id, target: prompt.id }] : []),
    ],
    positions,
  };
}
