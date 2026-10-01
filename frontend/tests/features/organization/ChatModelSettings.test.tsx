import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatModelSettings } from '../../../src/features/organization/ChatModelSettings';
import * as api from '../../../src/features/organization/api';
import type { CatalogPage, ChatModels } from '../../../src/features/organization/api';

vi.mock('../../../src/features/organization/api');

const empty: ChatModels = {
  scope: 'organization',
  can_manage: true,
  context_ceiling: 32000,
  default_model: null,
  models: [],
};
const approved: ChatModels = {
  ...empty,
  default_model: 'openai/gpt-4.1-mini',
  models: [
    {
      id: 'openai/gpt-4.1-mini',
      label: 'GPT-4.1 Mini',
      context_tokens: 32000,
      prompt_usd_per_mtok: 0.4,
      completion_usd_per_mtok: 1.6,
      catalog_fetched_at: '2026-10-01T00:00:00Z',
      source: 'organization',
      is_default: true,
    },
    {
      id: 'server/model',
      label: 'server/model',
      context_tokens: 32000,
      prompt_usd_per_mtok: null,
      completion_usd_per_mtok: null,
      catalog_fetched_at: null,
      source: 'server',
      is_default: false,
    },
  ],
};
const page: CatalogPage = {
  items: [
    {
      id: 'openai/gpt-4.1-mini',
      name: 'GPT-4.1 Mini',
      context_length: 1047576,
      prompt_usd_per_mtok: 0.4,
      completion_usd_per_mtok: 1.6,
      approved: false,
    },
  ],
  total: 1,
  offset: 0,
  limit: 25,
  fetched_at: '2026-10-01T00:00:00Z',
};

test('admin searches the catalog and approves a model', async () => {
  const user = userEvent.setup();
  vi.mocked(api.getChatModels).mockResolvedValue(empty);
  vi.mocked(api.searchCatalog).mockResolvedValue(page);
  vi.mocked(api.approveChatModel).mockResolvedValue(approved);
  render(<ChatModelSettings />);
  expect(await screen.findByText('No chat models are available')).toBeVisible();
  // The catalog is fetched only after the admin opens it.
  expect(api.searchCatalog).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Add models' }));
  expect(await screen.findByText('Showing 1–1 of 1 models')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Approve openai/gpt-4.1-mini' }));
  expect(api.approveChatModel).toHaveBeenCalledWith('openai/gpt-4.1-mini');
  expect(await screen.findByText('openai/gpt-4.1-mini was approved.')).toBeVisible();
  expect(screen.getByText('Default')).toBeVisible();
  expect(screen.getByText('Set on the server')).toBeVisible();
});

test('server models cannot be removed and organization models need confirmation', async () => {
  const user = userEvent.setup();
  vi.mocked(api.getChatModels).mockResolvedValue(approved);
  vi.mocked(api.removeChatModel).mockResolvedValue(empty);
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  render(<ChatModelSettings />);
  await screen.findByText('GPT-4.1 Mini');
  expect(screen.queryByRole('button', { name: 'Remove server/model' })).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Remove openai/gpt-4.1-mini' }));
  expect(confirm).toHaveBeenCalled();
  expect(api.removeChatModel).not.toHaveBeenCalled();
  confirm.mockReturnValue(true);
  await user.click(screen.getByRole('button', { name: 'Remove openai/gpt-4.1-mini' }));
  expect(api.removeChatModel).toHaveBeenCalledWith('openai/gpt-4.1-mini');
  confirm.mockRestore();
});

test('members see the models without management controls', async () => {
  vi.mocked(api.getChatModels).mockResolvedValue({ ...approved, can_manage: false });
  render(<ChatModelSettings />);
  expect(await screen.findByText('GPT-4.1 Mini')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Add models' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Remove/ })).not.toBeInTheDocument();
  expect(screen.getByText(/Only organization admins/)).toBeVisible();
});
