import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProviderKeySettings } from '../../../src/features/organization/ProviderKeySettings';
import * as api from '../../../src/features/organization/api';
import type { ProviderKey } from '../../../src/features/organization/api';

vi.mock('../../../src/features/organization/api');

const missing: ProviderKey = {
  provider: 'openrouter',
  scope: 'organization',
  configured: false,
  status: null,
  redacted_hint: null,
  updated_by: null,
  updated_at: null,
  last_verified_at: null,
  environment_fallback: false,
  can_manage: true,
  storage_available: true,
};

const saved: ProviderKey = {
  ...missing,
  configured: true,
  status: 'active',
  redacted_hint: 'sk-or-v1-…AAAA',
  updated_by: 'user_admin',
  updated_at: '2026-10-01T00:00:00Z',
  last_verified_at: '2026-10-01T00:00:00Z',
};

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  window.location.hash = '#/organization/settings';
});

test('admin saves a key once, then only the redacted hint remains', async () => {
  const user = userEvent.setup();
  const secret = 'sk-or-v1-never-stay-in-the-browser-AAAA';
  vi.mocked(api.getProviderKey).mockResolvedValue(missing);
  vi.mocked(api.saveProviderKey).mockResolvedValue(saved);
  render(<ProviderKeySettings />);
  expect(await screen.findByText('Model calls are blocked')).toBeVisible();
  await user.type(screen.getByLabelText('OpenRouter API key'), secret);
  await user.click(screen.getByRole('button', { name: 'Save key' }));
  expect(api.saveProviderKey).toHaveBeenCalledWith(secret);
  expect(await screen.findByText('sk-or-v1-…AAAA')).toBeVisible();
  expect(screen.getByLabelText('Replacement OpenRouter API key')).toHaveValue('');
  expect(document.body.innerHTML).not.toContain(secret);
  expect(window.location.href).not.toContain(secret);
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(secret);
});

test('members see status but no key controls', async () => {
  vi.mocked(api.getProviderKey).mockResolvedValue({ ...saved, can_manage: false });
  render(<ProviderKeySettings />);
  expect(await screen.findByText('Active')).toBeVisible();
  expect(
    screen.getByText('Only organization admins can add, replace or remove this key.'),
  ).toBeVisible();
  expect(screen.queryByRole('button', { name: /key/i })).not.toBeInTheDocument();
});

test('shows rejected keys and save errors without hiding the server message', async () => {
  const user = userEvent.setup();
  vi.mocked(api.getProviderKey).mockResolvedValue({ ...saved, status: 'rejected' });
  vi.mocked(api.saveProviderKey).mockRejectedValue(new Error('OpenRouter rejected this key.'));
  render(<ProviderKeySettings />);
  expect(await screen.findByText('OpenRouter rejected this key')).toBeVisible();
  await user.type(
    screen.getByLabelText('Replacement OpenRouter API key'),
    'sk-or-v1-0000000000000000000000',
  );
  await user.click(screen.getByRole('button', { name: 'Replace key' }));
  expect(await screen.findByText('OpenRouter rejected this key.')).toBeVisible();
});

test('explains when encrypted storage is unavailable', async () => {
  vi.mocked(api.getProviderKey).mockResolvedValue({ ...missing, storage_available: false });
  render(<ProviderKeySettings />);
  expect(await screen.findByText('Encrypted key storage is unavailable')).toBeVisible();
  expect(screen.queryByLabelText('OpenRouter API key')).not.toBeInTheDocument();
});

test('remove asks for confirmation first', async () => {
  const user = userEvent.setup();
  vi.mocked(api.getProviderKey).mockResolvedValue(saved);
  vi.mocked(api.deleteProviderKey).mockResolvedValue(missing);
  const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
  render(<ProviderKeySettings />);
  await user.click(await screen.findByRole('button', { name: 'Remove key' }));
  expect(api.deleteProviderKey).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Remove key' }));
  expect(api.deleteProviderKey).toHaveBeenCalledOnce();
  confirm.mockRestore();
});
