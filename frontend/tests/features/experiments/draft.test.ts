import { emptyDraft, readDraft, saveDraft } from '../../../src/features/experiments/draft';
beforeEach(() => sessionStorage.clear());
test('isolates drafts by project and excludes unknown fields', () => {
  saveDraft('a', {
    ...emptyDraft(),
    name: 'Review',
    a: 'v1',
    b: 'v2',
    dataset: 'd1',
    metrics: ['faithfulness'],
  });
  expect(readDraft('a')).toMatchObject({
    name: 'Review',
    a: 'v1',
    b: 'v2',
    dataset: 'd1',
    metrics: ['faithfulness'],
  });
  expect(readDraft('b')).toEqual(emptyDraft());
});
test('handles corrupt storage, duplicate candidates and unknown metrics safely', () => {
  sessionStorage.setItem('experiment-draft:v1:a', '{broken');
  expect(readDraft('a')).toEqual(emptyDraft());
  sessionStorage.setItem(
    'experiment-draft:v1:a',
    JSON.stringify({
      name: 'x'.repeat(200),
      a: 'same',
      b: 'same',
      metrics: ['fake', 'context_recall'],
      file: 'secret source',
    }),
  );
  expect(readDraft('a')).toEqual({
    name: 'x'.repeat(120),
    dataset: '',
    a: 'same',
    b: '',
    metrics: ['context_recall'],
  });
});
