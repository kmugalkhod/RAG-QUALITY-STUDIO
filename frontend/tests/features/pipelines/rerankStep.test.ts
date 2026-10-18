import { describe, expect, it } from 'vitest';
import {
  addRerankStep,
  createPipelineDraft,
  removeRerankStep,
  type GraphStep,
} from '../../../src/features/pipelines/pipelineTemplate';
import {
  createEditableExecution,
  nodeIssues,
  validatePipelineExecution,
  type PipelineExecution,
  type PipelineOptions,
} from '../../../src/features/pipelines/model';
import { summarizeNodeConfig } from '../../../src/features/pipelines/components/summarizeNodeConfig';

const options: PipelineOptions = {
  models: ['chat', 'cheap'],
  model_options: [],
  default_model: 'chat',
  template: '{question}\n{context}',
  max_tokens: 512,
  context_tokens: 32768,
  error: null,
  error_code: null,
  can_manage_models: false,
  rerank: { default_model: 'cheap', recommended_model: 'cheap', top_n: 5, candidates: 30 },
};

function step(): GraphStep {
  const draft = createPipelineDraft(options, 'Support', 'index', 5);
  return {
    nodes: draft.execution.nodes,
    edges: draft.execution.edges,
    positions: draft.layout.positions,
  };
}

function execution(graph: GraphStep, version: 2 | 3): PipelineExecution {
  return { schema_version: version, nodes: graph.nodes, edges: graph.edges };
}

describe('Add a rerank step', () => {
  it('inserts the node between Retriever and Prompt and rewires the edges', () => {
    const added = addRerankStep(step(), options);
    expect(added.nodes.map((node) => node.type)).toEqual([
      'question',
      'retriever',
      'rerank',
      'prompt',
      'llm',
      'answer',
    ]);
    expect(added.edges).toEqual(
      expect.arrayContaining([
        { source: 'retriever', target: 'rerank' },
        { source: 'rerank', target: 'prompt' },
      ]),
    );
    expect(added.edges).not.toContainEqual({ source: 'retriever', target: 'prompt' });
    expect(added.edges).toHaveLength(5);
    expect(validatePipelineExecution(execution(added, 3), options, ['index'])).toEqual([]);
  });

  it('uses the server defaults and 30 candidates', () => {
    const added = addRerankStep(step(), options);
    expect(added.nodes[2]).toEqual({ id: 'rerank', type: 'rerank', model: 'cheap', top_n: 5 });
    expect(added.nodes[1].retrieval?.top_k).toBe(30);
  });

  it('keeps a larger Top k and never exceeds 50', () => {
    const graph = step();
    graph.nodes[1] = { ...graph.nodes[1], retrieval: { mode: 'vector', top_k: 40 } };
    expect(addRerankStep(graph, options).nodes[1].retrieval?.top_k).toBe(40);
    const tooMany = { ...options, rerank: { ...options.rerank!, candidates: 80 } };
    expect(addRerankStep(step(), tooMany).nodes[1].retrieval?.top_k).toBe(50);
  });

  it('places the node in the Prompt slot and moves the later nodes down', () => {
    const before = step();
    const added = addRerankStep(before, options);
    expect(added.positions.rerank).toEqual(before.positions.prompt);
    expect(added.positions.prompt.y).toBe(before.positions.prompt.y + 116);
    expect(added.positions.answer.y).toBe(before.positions.answer.y + 116);
    expect(added.positions.retriever).toEqual(before.positions.retriever);
  });

  it('moves later nodes right in a horizontal layout', () => {
    const graph = step();
    graph.positions = Object.fromEntries(
      graph.nodes.map((node, index) => [node.id, { x: index * 210, y: 80 }]),
    );
    const added = addRerankStep(graph, options);
    expect(added.positions.rerank).toEqual({ x: 420, y: 80 });
    expect(added.positions.prompt).toEqual({ x: 660, y: 80 });
  });

  it('adds only one rerank step', () => {
    const added = addRerankStep(step(), options);
    expect(addRerankStep(added, options)).toBe(added);
  });

  it('falls back to the default model without rerank defaults', () => {
    const legacy = { ...options, rerank: undefined };
    expect(addRerankStep(step(), legacy).nodes[2].model).toBe('chat');
  });
});

describe('Remove rerank step', () => {
  it('restores the five-node graph with Top k set to the passages kept', () => {
    const before = step();
    const added = addRerankStep(before, options);
    added.nodes[2] = { ...added.nodes[2], top_n: 7 };
    const removed = removeRerankStep(added);
    expect(removed.nodes.map((node) => node.type)).toEqual([
      'question',
      'retriever',
      'prompt',
      'llm',
      'answer',
    ]);
    expect(removed.edges).toContainEqual({ source: 'retriever', target: 'prompt' });
    expect(removed.edges).toHaveLength(4);
    expect(removed.nodes[1].retrieval?.top_k).toBe(7);
    expect(removed.positions).toEqual(before.positions);
    expect(validatePipelineExecution(execution(removed, 2), options, ['index'])).toEqual([]);
  });

  it('does nothing without a rerank step', () => {
    const graph = step();
    expect(removeRerankStep(graph)).toBe(graph);
  });
});

describe('rerank validation', () => {
  it('rejects an unapproved model, a bad passage count and too few candidates', () => {
    const added = addRerankStep(step(), options);
    added.nodes[2] = { ...added.nodes[2], model: 'unknown' };
    expect(validatePipelineExecution(execution(added, 3), options, ['index'])).toContain(
      'Rerank: select an approved model.',
    );
    added.nodes[2] = { ...added.nodes[2], model: 'cheap', top_n: 21 };
    expect(validatePipelineExecution(execution(added, 3), options, ['index'])).toContain(
      'Rerank: keep a whole number of passages from 1 to 20.',
    );
    added.nodes[2] = { ...added.nodes[2], top_n: 10 };
    added.nodes[1] = { ...added.nodes[1], retrieval: { mode: 'vector', top_k: 8 } };
    const errors = validatePipelineExecution(execution(added, 3), options, ['index']);
    expect(errors).toContain(
      'Retriever: Top k is the number of candidates to rerank; set it to at least 10.',
    );
    expect(nodeIssues(errors, options).retriever).toMatch(/at least 10/);
  });

  it('rejects a rerank node outside its slot', () => {
    const added = addRerankStep(step(), options);
    added.edges = [
      { source: 'question', target: 'retriever' },
      { source: 'retriever', target: 'prompt' },
      { source: 'prompt', target: 'rerank' },
      { source: 'rerank', target: 'llm' },
      { source: 'llm', target: 'answer' },
    ];
    expect(validatePipelineExecution(execution(added, 3), options, ['index'])).toContain(
      'Connect Question → Retriever → Rerank → Prompt → LLM → Answer only; branches, cycles and disconnected nodes are unsupported.',
    );
  });

  it('keeps schema 3 for editable copies with a rerank step and 2 without', () => {
    const added = addRerankStep(step(), options);
    expect(createEditableExecution(execution(added, 3)).schema_version).toBe(3);
    expect(createEditableExecution(execution(step(), 2)).schema_version).toBe(2);
  });

  it('summarizes the node card', () => {
    expect(
      summarizeNodeConfig('rerank', { id: 'r', type: 'rerank', model: 'cheap', top_n: 5 }),
    ).toBe('Keeps 5 · cheap');
    expect(summarizeNodeConfig('rerank', { id: 'r', type: 'rerank', top_n: 3 })).toBe(
      'Keeps 3 · Choose a model',
    );
  });
});
