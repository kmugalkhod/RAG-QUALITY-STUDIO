import { createPipelineDraft } from '../../../src/features/pipelines/pipelineTemplate';
import { validatePipelineExecution } from '../../../src/features/pipelines/model';

const options = {
  models: ['configured-model'],
  template: '{question}\n{context}',
  max_tokens: 512,
  context_tokens: 4096,
  error: null,
};

test('uses server defaults and produces a valid supported graph for a ready index', () => {
  const draft = createPipelineDraft(options, 'Support', 'ready-index', 7);
  expect(validatePipelineExecution(draft.execution, options, ['ready-index'])).toEqual([]);
  expect(draft.execution.nodes.find((node) => node.type === 'retriever')?.retrieval?.top_k).toBe(7);
  expect(draft.execution.nodes.find((node) => node.type === 'llm')?.model).toBe('configured-model');
});

test('each draft owns independent editable node settings, edges, and positions', () => {
  const first = createPipelineDraft(options, 'First', 'index');
  const second = createPipelineDraft(options, 'Second', 'index');
  first.execution.nodes[1].retrieval!.top_k = 12;
  first.execution.edges[0].target = 'answer';
  first.layout.positions.question.x = 999;
  expect(second.execution.nodes[1].retrieval!.top_k).toBe(5);
  expect(second.execution.edges[0].target).toBe('retriever');
  expect(second.layout.positions.question.x).toBe(80);
});
