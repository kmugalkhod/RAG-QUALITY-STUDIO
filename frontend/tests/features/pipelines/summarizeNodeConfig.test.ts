import { summarizeNodeConfig } from '../../../src/features/pipelines/components/summarizeNodeConfig';

// covers: AC-9 (one summary line per node card, Value sourcing "Node card")

describe('summarizeNodeConfig', () => {
  test('question, prompt and answer nodes use fixed copy', () => {
    expect(summarizeNodeConfig('question', { id: 'q', type: 'question' })).toBe(
      'User input · single turn',
    );
    expect(summarizeNodeConfig('prompt', { id: 'p', type: 'prompt', template: 'x' })).toBe(
      'Answer with evidence',
    );
    expect(summarizeNodeConfig('answer', { id: 'a', type: 'answer' })).toBe('Response + citations');
  });

  test('a retriever without settings shows the vector default and asks for documents', () => {
    expect(summarizeNodeConfig('retriever', { id: 'r', type: 'retriever' })).toBe(
      'Vector · Top 5 · Choose documents',
    );
  });

  test('a retriever with an index reads Documents selected', () => {
    expect(
      summarizeNodeConfig('retriever', { id: 'r', type: 'retriever', index_id: 'idx-1' }),
    ).toBe('Vector · Top 5 · Documents selected');
  });

  test('a retriever shows its saved search mode and top k', () => {
    expect(
      summarizeNodeConfig('retriever', {
        id: 'r',
        type: 'retriever',
        retrieval: { mode: 'vector', top_k: 12 },
      }),
    ).toBe('Vector · Top 12 · Choose documents');
  });

  test('a legacy retriever falls back to its top level top_k', () => {
    expect(summarizeNodeConfig('retriever', { id: 'r', type: 'retriever', top_k: 8 })).toBe(
      'Vector · Top 8 · Choose documents',
    );
  });

  test('an LLM node shows its model, or asks for one when none is set', () => {
    expect(summarizeNodeConfig('llm', { id: 'l', type: 'llm', model: 'openai/gpt-x' })).toBe(
      'openai/gpt-x',
    );
    expect(summarizeNodeConfig('llm', { id: 'l', type: 'llm' })).toBe('Choose a model');
    expect(summarizeNodeConfig('llm', { id: 'l', type: 'llm', model: '' })).toBe('Choose a model');
  });
});
