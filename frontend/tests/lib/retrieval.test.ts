import {
  changeRetrievalMode,
  createDefaultRetrievalSettings,
  formatRetrievalScores,
  validateRetrievalSettings,
  type RetrievalSettings,
} from '../../src/lib/retrieval';

test.each([NaN, Infinity, 0, 51, 1.5])('rejects invalid top k: %s', (topK) => {
  expect(validateRetrievalSettings(createDefaultRetrievalSettings(topK))).toContain(
    'Top k must be a whole number from 1 to 50.',
  );
});

test('accepts inclusive cutoffs and weights, and rejects candidates below top k', () => {
  const settings: RetrievalSettings = {
    mode: 'hybrid',
    top_k: 50,
    max_vector_distance: 0,
    vector_candidates: 50,
    keyword_candidates: 200,
    vector_weight: 0,
  };
  expect(validateRetrievalSettings(settings)).toEqual([]);
  expect(
    validateRetrievalSettings({ ...settings, max_vector_distance: 2, vector_weight: 1 }),
  ).toEqual([]);
  expect(validateRetrievalSettings({ ...settings, keyword_candidates: 49 })).toEqual([
    'Each candidate count must be a whole number between Top k and 200.',
  ]);
  expect(
    validateRetrievalSettings({ ...settings, max_vector_distance: NaN, vector_weight: Infinity }),
  ).toHaveLength(2);
});

test('switching modes preserves shared settings and removes inapplicable fields', () => {
  const vector: RetrievalSettings = { mode: 'vector', top_k: 8, max_vector_distance: 0.4 };
  const hybrid = changeRetrievalMode(vector, 'hybrid');
  expect(hybrid).toMatchObject({ mode: 'hybrid', top_k: 8, max_vector_distance: 0.4 });
  expect(changeRetrievalMode(hybrid, 'hybrid')).toBe(hybrid);
  expect(changeRetrievalMode(hybrid, 'vector')).toEqual(vector);
  expect(changeRetrievalMode(hybrid, 'keyword')).toEqual({ mode: 'keyword', top_k: 8 });
  expect(vector.mode).toBe('vector');
});

test('keeps zero scores and omits unavailable scores without calling them confidence', () => {
  expect(formatRetrievalScores({ cosine_distance: 0, lexical_score: null, fusion_score: 0 })).toBe(
    'Cosine distance 0.0000 · RRF score 0.000000',
  );
  expect(formatRetrievalScores({ cosine_distance: null })).toBe('');
});
