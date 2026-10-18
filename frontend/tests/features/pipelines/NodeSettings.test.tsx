import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { NodeSettings } from '../../../src/features/pipelines/components/NodeSettings';
import type { FlowNode } from '../../../src/features/pipelines/components/WorkflowNode';
import type { PipelineNodeConfig, PipelineOptions } from '../../../src/features/pipelines/model';

const options: PipelineOptions = {
  models: ['chat', 'cheap'],
  model_options: ['chat', 'cheap'].map((id) => ({
    id,
    label: id,
    context_tokens: 32768,
    prompt_usd_per_mtok: null,
    completion_usd_per_mtok: null,
    catalog_fetched_at: null,
    source: 'server' as const,
    is_default: id === 'chat',
  })),
  default_model: 'chat',
  template: '{question}\n{context}',
  max_tokens: 512,
  context_tokens: 32768,
  error: null,
  error_code: null,
  can_manage_models: false,
  rerank: { default_model: 'cheap', recommended_model: 'cheap', top_n: 5, candidates: 30 },
};

const retriever: PipelineNodeConfig = {
  id: 'retriever',
  type: 'retriever',
  index_id: '',
  retrieval: { mode: 'vector', top_k: 30 },
};
const rerank: PipelineNodeConfig = { id: 'rerank', type: 'rerank', model: 'cheap', top_n: 5 };

function flow(configs: PipelineNodeConfig[]): FlowNode[] {
  return configs.map((config) => ({
    id: config.id,
    position: { x: 0, y: 0 },
    data: { label: config.type, config, vertical: true },
  }));
}

function renderSettings(config: PipelineNodeConfig, configs: PipelineNodeConfig[], extra = {}) {
  const handlers = {
    onUpdate: vi.fn(),
    onDelete: vi.fn(),
    onAddRerank: vi.fn(),
    onRemoveRerank: vi.fn(),
  };
  render(
    <NodeSettings
      open
      config={config}
      selected={config.id}
      nodes={flow(configs)}
      indexes={[]}
      options={options}
      optionsLoading={false}
      onRefreshOptions={vi.fn()}
      onSelect={vi.fn()}
      {...handlers}
      {...extra}
    />,
  );
  return handlers;
}

describe('rerank step settings', () => {
  it('offers Add a rerank step on the Retriever', async () => {
    const handlers = renderSettings(retriever, [retriever]);
    await userEvent.click(screen.getByRole('button', { name: 'Add a rerank step' }));
    expect(handlers.onAddRerank).toHaveBeenCalledOnce();
    expect(screen.queryByRole('button', { name: 'Remove rerank step' })).not.toBeInTheDocument();
  });

  it('offers Remove rerank step on the Retriever once added', async () => {
    const handlers = renderSettings(retriever, [retriever, rerank]);
    expect(
      screen.getByText(/Top k is the number of candidates the Rerank step reads/),
    ).toHaveTextContent('keeps the 5 most useful');
    await userEvent.click(screen.getByRole('button', { name: 'Remove rerank step' }));
    expect(handlers.onRemoveRerank).toHaveBeenCalledOnce();
  });

  it('has a labelled form for the model and the passages kept', async () => {
    const handlers = renderSettings(rerank, [retriever, rerank]);
    expect(screen.getByRole('heading', { name: 'Rerank' })).toBeInTheDocument();
    const model = screen.getByRole('combobox', { name: 'Rerank model' });
    expect(model).toHaveValue('cheap');
    await userEvent.selectOptions(model, 'chat');
    expect(handlers.onUpdate).toHaveBeenCalledWith({ model: 'chat' });
    const kept = screen.getByRole('spinbutton', { name: 'Passages kept' });
    expect(kept).toHaveValue(5);
    fireEvent.change(kept, { target: { value: '8' } });
    expect(handlers.onUpdate).toHaveBeenLastCalledWith({ top_n: 8 });
    expect(screen.queryByRole('button', { name: 'Delete selected node' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Remove rerank step' }));
    expect(handlers.onRemoveRerank).toHaveBeenCalledOnce();
  });

  it('names the measured model when it is not approved', () => {
    render(
      <NodeSettings
        open
        config={rerank}
        selected="rerank"
        nodes={flow([retriever, rerank])}
        indexes={[]}
        options={{ ...options, rerank: { ...options.rerank!, recommended_model: 'other/lite' } }}
        optionsLoading={false}
        onRefreshOptions={vi.fn()}
        onSelect={vi.fn()}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onAddRerank={vi.fn()}
        onRemoveRerank={vi.fn()}
      />,
    );
    expect(screen.getByText(/Measured choice: other\/lite/)).toBeInTheDocument();
  });
});
