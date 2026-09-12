import { describe, expect, it } from 'vitest';
import {
  canonical,
  createEditableExecution,
  validatePipelineExecution,
  type PipelineExecution,
} from '../../../src/features/pipelines/model';
const valid = (): PipelineExecution => ({
  schema_version: 1,
  nodes: [
    { id: 'q', type: 'question' },
    { id: 'r', type: 'retriever', index_id: 'index', top_k: 5 },
    { id: 'p', type: 'prompt', template: '{question} {context}' },
    { id: 'l', type: 'llm', model: 'chat', max_tokens: 512, temperature: 0 },
    { id: 'a', type: 'answer' },
  ],
  edges: [
    { source: 'q', target: 'r' },
    { source: 'r', target: 'p' },
    { source: 'p', target: 'l' },
    { source: 'l', target: 'a' },
  ],
});
describe('pipeline validation', () => {
  it('ignores JSONB object key ordering for unsaved state', () =>
    expect(canonical({ layout: { question: { x: 1, y: 2 }, answer: { x: 3, y: 4 } } })).toBe(
      canonical({ layout: { answer: { y: 4, x: 3 }, question: { y: 2, x: 1 } } }),
    ));
  it('accepts the supported template', () =>
    expect(validatePipelineExecution(valid())).toEqual([]));
  it('rejects deleted nodes, branching and cycles', () => {
    const graph = valid();
    graph.nodes.pop();
    expect(validatePipelineExecution(graph).length).toBeGreaterThan(0);
    const branch = valid();
    branch.edges.push({ source: 'q', target: 'a' });
    expect(validatePipelineExecution(branch).length).toBeGreaterThan(0);
    const cycle = valid();
    cycle.edges[3].target = 'q';
    expect(validatePipelineExecution(cycle).length).toBeGreaterThan(0);
  });
  it('rejects unsafe templates and invalid generation/retrieval settings', () => {
    const graph = valid();
    graph.nodes[2].template += '{question.__class__}';
    graph.nodes[1].top_k = NaN;
    graph.nodes[3].temperature = 3;
    expect(validatePipelineExecution(graph)).toHaveLength(3);
  });
});

test('editable graph changes cannot mutate a saved version, including nested settings and edges', () => {
  const saved = valid();
  const editable = createEditableExecution(saved);
  editable.nodes[1].retrieval!.top_k = 12;
  editable.nodes[2].template = 'Changed draft';
  editable.edges[0].target = 'answer';
  expect(saved.nodes[1].top_k).toBe(5);
  expect(saved.nodes[1].retrieval).toBeUndefined();
  expect(saved.nodes[2].template).toBe('{question} {context}');
  expect(saved.edges[0].target).toBe('r');
});
