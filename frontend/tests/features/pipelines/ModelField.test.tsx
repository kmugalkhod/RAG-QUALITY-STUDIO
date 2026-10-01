import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ModelField } from '../../../src/features/pipelines/components/ModelField';
import {
  nodeIssues,
  validatePipelineExecution,
  type ChatModelOption,
  type PipelineExecution,
  type PipelineOptions,
} from '../../../src/features/pipelines/model';

const approved: ChatModelOption = {
  id: 'openai/gpt-4.1-mini',
  label: 'GPT-4.1 Mini',
  context_tokens: 32000,
  prompt_usd_per_mtok: 0.4,
  completion_usd_per_mtok: 1.6,
  catalog_fetched_at: '2026-10-01T00:00:00Z',
  source: 'organization',
  is_default: true,
};
const small: ChatModelOption = {
  ...approved,
  id: 'tiny/model',
  label: 'tiny/model',
  context_tokens: 2048,
  prompt_usd_per_mtok: null,
  completion_usd_per_mtok: null,
  source: 'server',
  is_default: false,
};

function options(overrides: Partial<PipelineOptions> = {}): PipelineOptions {
  const model_options = overrides.model_options ?? [approved, small];
  return {
    models: model_options.map((model) => model.id),
    model_options,
    default_model: model_options[0]?.id ?? null,
    template: '{question} {context}',
    max_tokens: 1024,
    context_tokens: 32000,
    error: null,
    error_code: null,
    can_manage_models: false,
    ...overrides,
  };
}

function renderField(value: string, value_options: PipelineOptions, onChange = vi.fn()) {
  const onRefresh = vi.fn();
  render(
    <ModelField
      value={value}
      options={value_options}
      loading={false}
      onChange={onChange}
      onRefresh={onRefresh}
    />,
  );
  return { onChange, onRefresh };
}

test('lists models grouped by provider with the selected model budget and price', async () => {
  const user = userEvent.setup();
  const { onChange } = renderField(approved.id, options());
  const select = screen.getByLabelText('Chat model');
  expect(within(select).getByRole('group', { name: 'openai' })).toBeInTheDocument();
  expect(within(select).getByRole('group', { name: 'tiny' })).toBeInTheDocument();
  expect(
    screen.getByText(/32,000 token budget · \$0\.4 in \/ \$1\.6 out per 1M tokens/),
  ).toBeVisible();
  await user.selectOptions(select, 'tiny/model');
  expect(onChange).toHaveBeenCalledWith('tiny/model');
});

test('an empty list explains why and offers a refresh instead of an empty select', async () => {
  const user = userEvent.setup();
  const { onRefresh } = renderField(
    '',
    options({
      model_options: [],
      error: 'No chat models are approved for this organization.',
      error_code: 'no_models',
    }),
  );
  expect(screen.queryByLabelText('Chat model')).not.toBeInTheDocument();
  expect(screen.getByText('Chat model needed')).toBeVisible();
  expect(screen.getByText('No chat models are approved for this organization.')).toBeVisible();
  expect(screen.getByText(/Ask an organization admin/)).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Manage models' })).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Refresh models' }));
  expect(onRefresh).toHaveBeenCalled();
});

test('admins get a link to manage models', () => {
  renderField('', options({ model_options: [], can_manage_models: true }));
  expect(screen.getByRole('link', { name: 'Manage models' })).toHaveAttribute(
    'href',
    '#/organization',
  );
});

test('a saved model that is no longer approved stays visible and is flagged', () => {
  renderField('old/model', options());
  expect(screen.getByLabelText('Chat model')).toHaveValue('old/model');
  expect(screen.getByRole('option', { name: 'old/model (not approved)' })).toBeInTheDocument();
  expect(screen.getByText('This model is no longer approved')).toBeVisible();
});

test('a missing provider key is reported separately from the model list', () => {
  renderField(
    approved.id,
    options({ error: 'No OpenRouter key is configured.', error_code: 'provider_key' }),
  );
  expect(screen.getByText('OpenRouter key needed')).toBeVisible();
  expect(screen.getByLabelText('Chat model')).toBeEnabled();
});

const execution = (model: string, max_tokens: number): PipelineExecution => ({
  schema_version: 2,
  nodes: [
    { id: 'q', type: 'question' },
    { id: 'r', type: 'retriever', index_id: 'index' },
    { id: 'p', type: 'prompt', template: '{question} {context}' },
    { id: 'l', type: 'llm', model, max_tokens, temperature: 0 },
    { id: 'a', type: 'answer' },
  ],
  edges: [
    { source: 'q', target: 'r' },
    { source: 'r', target: 'p' },
    { source: 'p', target: 'l' },
    { source: 'l', target: 'a' },
  ],
});

test('output tokens are validated against the selected model budget', () => {
  expect(validatePipelineExecution(execution(approved.id, 2048), options())).toEqual([]);
  const errors = validatePipelineExecution(execution('tiny/model', 1024), options());
  expect(errors.some((error) => error.startsWith('LLM:'))).toBe(true);
});

test('node issues map validation and model availability to node kinds', () => {
  const issues = nodeIssues(
    ['Retriever: choose documents to search in Node settings.', 'Require exactly one node.'],
    options({ model_options: [], error: 'No chat models.', error_code: 'no_models' }),
  );
  expect(issues).toEqual({
    retriever: 'choose documents to search in Node settings.',
    llm: 'No chat models.',
  });
});
