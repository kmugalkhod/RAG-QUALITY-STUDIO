import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test } from 'vitest';
import { RetrievalSettingsForm } from './RetrievalSettingsForm';
import { defaultRetrieval, type RetrievalSettings } from './settings';
import { editableExecution, type Execution } from '../pipelines/api';

function Harness() {
  const [value, setValue] = useState<RetrievalSettings>(defaultRetrieval());
  return <><RetrievalSettingsForm value={value} onChange={setValue}/><output data-testid="settings">{JSON.stringify(value)}</output></>;
}

test('switching modes submits only applicable settings and exposes candidate validation', async () => {
  render(<Harness/>);
  await userEvent.selectOptions(screen.getByLabelText('Search method'), 'hybrid');
  await userEvent.click(screen.getByText('Advanced search settings'));
  await userEvent.clear(screen.getByLabelText('Vector candidate count'));
  await userEvent.type(screen.getByLabelText('Vector candidate count'), '2');
  expect(screen.getByText(/Each candidate count must be a whole/)).toBeVisible();
  await userEvent.clear(screen.getByLabelText('Vector candidate count'));
  await userEvent.type(screen.getByLabelText('Vector candidate count'), '30');
  await userEvent.clear(screen.getByLabelText('Vector weight'));
  await userEvent.type(screen.getByLabelText('Vector weight'), '0.7');
  expect(screen.getByTestId('settings')).toHaveTextContent('"vector_weight":0.7');
  await userEvent.selectOptions(screen.getByLabelText('Search method'), 'keyword');
  expect(screen.queryByLabelText('Vector weight')).not.toBeInTheDocument();
  expect(screen.getByTestId('settings')).toHaveTextContent('{"mode":"keyword","top_k":5}');
  await userEvent.selectOptions(screen.getByLabelText('Search method'), 'vector');
  expect(screen.getByTestId('settings')).not.toHaveTextContent('vector_candidates');
});

test('upgrading an editable legacy graph preserves the original and is idempotent', () => {
  const graph: Execution = { schema_version: 1, nodes: [{ id: 'r', type: 'retriever', index_id: 'index', top_k: 3 }], edges: [] };
  const upgraded = editableExecution(graph);
  expect(upgraded.schema_version).toBe(2);
  expect(upgraded.nodes[0].retrieval).toEqual(defaultRetrieval(3));
  expect(upgraded.nodes[0]).not.toHaveProperty('top_k');
  expect(graph.nodes[0].top_k).toBe(3);
  expect(editableExecution(upgraded)).toEqual(upgraded);
});
