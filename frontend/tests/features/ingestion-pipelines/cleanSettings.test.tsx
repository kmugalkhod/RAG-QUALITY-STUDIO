import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, test } from 'vitest';

import {
  CleaningTransformSettings,
  cleaningStepProblems,
} from '../../../src/features/ingestion-pipelines/components/CleaningTransformSettings';
import {
  ListTextField,
  parseList,
} from '../../../src/features/ingestion-pipelines/components/ListTextField';
import type { IngestionNode } from '../../../src/features/ingestion-pipelines/model';

type Clean = Extract<IngestionNode, { type: 'clean' }>;

const node: Clean = {
  id: 'clean',
  type: 'clean',
  profile: 'structure-aware-v1',
  config_version: 'structure-clean-v1',
  steps: [
    { id: 'unicode-normalize', type: 'unicode_normalize', enabled: true, form: 'NFC' },
    {
      id: 'remove-literal-boilerplate',
      type: 'remove_literal_boilerplate',
      enabled: true,
      values: [],
      block_types: ['paragraph', 'unknown'],
    },
  ],
};

let latest: Clean | undefined;

function Harness({ errors }: { errors?: Record<string, string> }) {
  const [value, setValue] = useState(node);
  latest = value;
  return <CleaningTransformSettings node={value} errors={errors} update={setValue} />;
}

test('typed literals keep their spaces and become one value per line', () => {
  render(<Harness />);
  const box = screen.getByLabelText('Exact literals');
  fireEvent.change(box, { target: { value: 'Page 1 of \nCopyright 2026' } });
  expect(box).toHaveValue('Page 1 of \nCopyright 2026');
  const step = latest?.steps?.[1];
  expect(step).toMatchObject({ values: ['Page 1 of ', 'Copyright 2026'] });
  fireEvent.blur(box);
  expect(box).toHaveValue('Page 1 of \nCopyright 2026');
});

test('an empty literal step is invalid on its text box', () => {
  render(<Harness />);
  expect(screen.getByLabelText('Exact literals')).toHaveAccessibleDescription(
    /Enter at least one line of text to remove\./,
  );
  expect(cleaningStepProblems(node)).toEqual({
    'steps.1.values': 'Enter at least one line of text to remove.',
  });
});

test('server errors show on the stage and on the step field', () => {
  render(
    <Harness
      errors={{
        clean: 'Normalize Unicode must run before Remove unsupported controls.',
        'clean.steps.1.values': 'Each line of text to remove must be unique.',
      }}
    />,
  );
  expect(screen.getAllByRole('alert')[0]).toHaveTextContent(
    'Normalize Unicode must run before Remove unsupported controls.',
  );
  expect(screen.getByLabelText('Exact literals')).toHaveAccessibleDescription(
    /Each line of text to remove must be unique\./,
  );
});

test('a comma-separated box lets a second value be typed', () => {
  function List() {
    const [values, setValues] = useState<string[]>([]);
    return (
      <>
        <ListTextField label="Pinned" separator="," trim values={values} onChange={setValues} />
        <output>{JSON.stringify(values)}</output>
      </>
    );
  }
  render(<List />);
  const box = screen.getByLabelText('Pinned');
  fireEvent.change(box, { target: { value: 'project-file:a,' } });
  expect(box).toHaveValue('project-file:a,');
  fireEvent.change(box, { target: { value: 'project-file:a, project-file:b' } });
  expect(screen.getByRole('status')).toHaveTextContent('["project-file:a","project-file:b"]');
  expect(parseList(' a ,, b ', ',', true)).toEqual(['a', 'b']);
});
