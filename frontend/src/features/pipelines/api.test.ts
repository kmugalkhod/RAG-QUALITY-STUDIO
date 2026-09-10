import { describe, expect, it } from 'vitest';
import { canonical, validate, type Execution } from './api';
const valid = (): Execution => ({ schema_version: 1, nodes: [
  { id: 'q', type: 'question' }, { id: 'r', type: 'retriever', index_id: 'index', top_k: 5 },
  { id: 'p', type: 'prompt', template: '{question} {context}' }, { id: 'l', type: 'llm', model: 'chat', max_tokens: 512, temperature: 0 }, { id: 'a', type: 'answer' },
], edges: [{ source: 'q', target: 'r' }, { source: 'r', target: 'p' }, { source: 'p', target: 'l' }, { source: 'l', target: 'a' }] });
describe('pipeline validation', () => {
  it('ignores JSONB object key ordering for unsaved state', () => expect(canonical({ layout: { question: { x: 1, y: 2 }, answer: { x: 3, y: 4 } } })).toBe(canonical({ layout: { answer: { y: 4, x: 3 }, question: { y: 2, x: 1 } } })));
  it('accepts the supported template', () => expect(validate(valid())).toEqual([]));
  it('rejects deleted nodes, branching and cycles', () => {
    const graph = valid(); graph.nodes.pop(); expect(validate(graph).length).toBeGreaterThan(0);
    const branch = valid(); branch.edges.push({ source: 'q', target: 'a' }); expect(validate(branch).length).toBeGreaterThan(0);
    const cycle = valid(); cycle.edges[3].target = 'q'; expect(validate(cycle).length).toBeGreaterThan(0);
  });
  it('rejects unsafe templates and invalid generation/retrieval settings', () => {
    const graph = valid(); graph.nodes[2].template += '{question.__class__}'; graph.nodes[1].top_k = NaN; graph.nodes[3].temperature = 3;
    expect(validate(graph)).toHaveLength(3);
  });
});
