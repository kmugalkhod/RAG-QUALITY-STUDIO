import {
  getNodeRetrievalSettings,
  validateRetrievalSettings,
  type RetrievalSettings,
} from '../../lib/retrieval';
export const pipelineNodeOrder = ['question', 'retriever', 'prompt', 'llm', 'answer'] as const;
export type PipelineNodeKind = (typeof pipelineNodeOrder)[number];
export type PipelineNodeConfig = {
  id: string;
  type: PipelineNodeKind;
  index_id?: string;
  top_k?: number;
  retrieval?: RetrievalSettings;
  template?: string;
  model?: string;
  max_tokens?: number;
  temperature?: number;
};
export type PipelineExecution = {
  schema_version: 1 | 2;
  nodes: PipelineNodeConfig[];
  edges: { source: string; target: string }[];
};
export type PipelineDraft = {
  name: string;
  execution: PipelineExecution;
  layout: { positions: Record<string, { x: number; y: number }> };
};
export type PipelineVersion = PipelineDraft & {
  id: string;
  pipeline_id: string;
  project_id: string;
  version: number;
  created_at: string;
};
export type Pipeline = { id: string; name: string };
export type PipelineOptions = {
  models: string[];
  template: string;
  max_tokens: number;
  context_tokens: number;
  error: string | null;
};
function hasValidPrompt(template: string | undefined): boolean {
  if (!template || template.length > 8000) {
    return false;
  }
  if (!template.includes('{question}') || !template.includes('{context}')) {
    return false;
  }
  const textWithoutPlaceholders = template.replaceAll('{question}', '').replaceAll('{context}', '');
  return !/[{}]/.test(textWithoutPlaceholders);
}

function hasValidGenerationSettings(node: PipelineNodeConfig, options?: PipelineOptions): boolean {
  if (!node.model || (options && !options.models.includes(node.model))) {
    return false;
  }
  const maxTokens = node.max_tokens ?? NaN;
  const temperature = node.temperature ?? NaN;
  if (!Number.isInteger(maxTokens) || maxTokens < 128 || maxTokens > 8192) {
    return false;
  }
  if (options && maxTokens + 1024 >= options.context_tokens) {
    return false;
  }
  return Number.isFinite(temperature) && temperature >= 0 && temperature <= 2;
}

export function validatePipelineExecution(
  execution: PipelineExecution,
  options?: PipelineOptions,
  readyIndexIds?: string[],
): string[] {
  const errors: string[] = [];
  const hasEveryNode = pipelineNodeOrder.every(
    (kind) => execution.nodes.filter((node) => node.type === kind).length === 1,
  );
  if (execution.nodes.length !== pipelineNodeOrder.length || !hasEveryNode) {
    errors.push('Require exactly one Question, Retriever, Prompt, LLM and Answer node.');
  }

  const nodeIds = pipelineNodeOrder.map(
    (kind) => execution.nodes.find((node) => node.type === kind)?.id,
  );
  const hasEveryConnection = nodeIds
    .slice(1)
    .every((targetId, index) =>
      execution.edges.some((edge) => edge.source === nodeIds[index] && edge.target === targetId),
    );
  if (execution.edges.length !== pipelineNodeOrder.length - 1 || !hasEveryConnection) {
    errors.push(
      'Connect Question → Retriever → Prompt → LLM → Answer only; branches, cycles and disconnected nodes are unsupported.',
    );
  }

  for (const node of execution.nodes) {
    switch (node.type) {
      case 'retriever':
        if (!node.index_id || (readyIndexIds && !readyIndexIds.includes(node.index_id))) {
          errors.push('Retriever: choose documents to search in Node settings.');
        }
        errors.push(
          ...validateRetrievalSettings(getNodeRetrievalSettings(node)).map(
            (message) => `Retriever: ${message}`,
          ),
        );
        break;
      case 'prompt':
        if (!hasValidPrompt(node.template)) {
          errors.push(
            'Prompt: include {question} and {context}; other braces or expressions are unsupported.',
          );
        }
        break;
      case 'llm':
        if (!hasValidGenerationSettings(node, options)) {
          errors.push(
            'LLM: select a configured model, output tokens within the server budget and temperature from 0 to 2.',
          );
        }
        break;
    }
  }
  return errors;
}

// PostgreSQL JSONB object key order is not meaningful; compare canonical data.
export function canonical(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonical).join(',')}]`;
  }
  if (value !== null && typeof value === 'object') {
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

// Convert only editable copies; persisted v1 JSON remains immutable.
export function createEditableExecution(execution: PipelineExecution): PipelineExecution {
  const editable = structuredClone(execution);
  editable.schema_version = 2;
  for (const node of editable.nodes) {
    if (node.type === 'retriever') {
      node.retrieval = getNodeRetrievalSettings(node);
      delete node.top_k;
    }
  }
  return editable;
}

export const getNodeLabel = (kind: PipelineNodeKind) =>
  kind === 'llm' ? 'LLM' : kind[0].toUpperCase() + kind.slice(1);
