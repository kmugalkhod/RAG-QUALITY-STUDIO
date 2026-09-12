import { createDefaultRetrievalSettings } from '../../lib/retrieval';
import {
  pipelineNodeOrder,
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
          'Answer concisely.\nQuestion: {question}\nRetrieved context: {context}',
      };
    case 'llm':
      return {
        ...node,
        model: options?.models[0] ?? '',
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
