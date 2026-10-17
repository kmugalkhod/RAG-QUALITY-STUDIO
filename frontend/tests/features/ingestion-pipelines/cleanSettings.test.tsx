import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, test } from 'vitest';

import { CleanSettings } from '../../../src/features/ingestion-pipelines/components/CleanSettings';
import { cleaningStepProblems } from '../../../src/features/ingestion-pipelines/components/CleaningTransformSettings';
import {
  ListTextField,
  parseList,
} from '../../../src/features/ingestion-pipelines/components/ListTextField';
import {
  cleanDifferences,
  recommendedCleanSteps,
} from '../../../src/features/ingestion-pipelines/downstreamModel';
import {
  defaultDuplicatePolicy,
  defaultSensitiveDataPolicy,
} from '../../../src/features/ingestion-pipelines/editorModel';
import type { IngestionNode } from '../../../src/features/ingestion-pipelines/model';

type Clean = Extract<IngestionNode, { type: 'clean' }>;

const recommended: Clean = {
  id: 'clean',
  type: 'clean',
  profile: 'structure-aware-v1',
  config_version: 'structure-clean-v1',
  exact_content_deduplication: true,
  steps: recommendedCleanSteps(),
  duplicate_policy: structuredClone(defaultDuplicatePolicy),
  sensitive_data_policy: structuredClone(defaultSensitiveDataPolicy),
};

/** The recommended steps with a saved literal step that has no text yet. */
const withEmptyLiteral: Clean = {
  ...recommended,
  steps: [
    ...recommendedCleanSteps().slice(0, -2),
    {
      id: 'remove-literal-boilerplate',
      type: 'remove_literal_boilerplate',
      enabled: true,
      values: [],
      block_types: ['paragraph', 'unknown'],
    },
    ...recommendedCleanSteps().slice(-2),
  ],
};

let latest: Clean | undefined;

function Harness({
  initial = recommended,
  errors = {},
}: {
  initial?: Clean;
  errors?: Record<string, string>;
}) {
  const [value, setValue] = useState(initial);
  latest = value;
  return <CleanSettings node={value} errors={errors} update={setValue} />;
}

test('the recommended cleaner shows its sentence, the text box and redaction', () => {
  render(<Harness />);
  expect(
    screen.getByText(/Removes website menus, cookie banners and repeated page headers/),
  ).toBeVisible();
  expect(screen.getByLabelText(/Redact emails, phone numbers and IDs/)).toBeChecked();
  expect(screen.getByText('· recommended')).toBeInTheDocument();
  expect(cleanDifferences(recommended)).toEqual([]);
});

test('typed text keeps its spaces and adds the literal step in the server order', () => {
  render(<Harness />);
  const box = screen.getByLabelText('Text to remove');
  fireEvent.change(box, { target: { value: 'Page 1 of \nCopyright 2026' } });
  expect(box).toHaveValue('Page 1 of \nCopyright 2026');
  const types = latest?.steps?.map((step) => step.type);
  expect(types?.slice(-3)).toEqual([
    'remove_literal_boilerplate',
    'remove_empty_blocks',
    'validate_useful_content',
  ]);
  expect(latest?.steps?.find((step) => step.type === 'remove_literal_boilerplate')).toMatchObject({
    values: ['Page 1 of ', 'Copyright 2026'],
  });
  // Literal text is a visible choice, so Advanced still says recommended.
  expect(screen.getByText('· recommended')).toBeInTheDocument();
  fireEvent.blur(box);
  expect(box).toHaveValue('Page 1 of \nCopyright 2026');
});

test('a saved literal step without text is invalid on the text box', () => {
  render(<Harness initial={withEmptyLiteral} />);
  expect(screen.getByLabelText('Text to remove')).toHaveAccessibleDescription(
    /Enter at least one line of text to remove\./,
  );
  expect(cleaningStepProblems(withEmptyLiteral)).toEqual({
    'steps.7.values': 'Enter at least one line of text to remove.',
  });
});

test('server errors show on the stage and on the text box, and open Advanced', () => {
  render(
    <Harness
      initial={withEmptyLiteral}
      errors={{
        clean: 'Normalize Unicode must run before Remove unsupported controls.',
        'clean.steps.7.values': 'Each line of text to remove must be unique.',
      }}
    />,
  );
  expect(
    screen.getByText('Normalize Unicode must run before Remove unsupported controls.'),
  ).toBeVisible();
  expect(screen.getByLabelText('Text to remove')).toHaveAccessibleDescription(
    /Each line of text to remove must be unique\./,
  );
});

test('a changed step is listed under Advanced and Reset keeps the visible choices', () => {
  render(<Harness />);
  fireEvent.change(screen.getByLabelText('Text to remove'), { target: { value: 'Footer' } });
  fireEvent.click(screen.getByLabelText(/Redact emails, phone numbers and IDs/));
  fireEvent.click(screen.getByRole('checkbox', { name: /Dehyphenate line endings/ }));
  expect(screen.getByText('· 1 changed')).toBeInTheDocument();
  expect(
    screen.getByText(/differs from recommended: Dehyphenate line endings\./),
  ).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Reset to recommended' }));
  expect(screen.getByText('· recommended')).toBeInTheDocument();
  expect(latest?.steps?.find((step) => step.type === 'dehyphenate')).toMatchObject({
    enabled: true,
  });
  expect(latest?.steps?.find((step) => step.type === 'remove_literal_boilerplate')).toMatchObject({
    values: ['Footer'],
  });
  expect(latest?.sensitive_data_policy?.enabled).toBe(false);
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
