import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConnectionVault } from '../../../src/features/connections/ConnectionVault';
import * as api from '../../../src/features/connections/api';
import type { ConnectionSettings, SourceConnection } from '../../../src/features/connections/model';

vi.mock('../../../src/features/connections/api');

const settings: ConnectionSettings = {
  enabled: true,
  local_only: true,
  kinds: ['s3', 'notion', 'confluence'],
};

const saved: SourceConnection = {
  id: 'connection-1',
  project_id: 'project-1',
  name: 'Warehouse',
  kind: 's3',
  status: 'untested',
  redacted_summary: ['Access key ••••1234', 'Long-lived key'],
  last_error: null,
  last_tested_at: null,
  rotated_at: null,
  created_at: '2026-09-13T00:00:00Z',
  updated_at: '2026-09-13T00:00:00Z',
};

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  window.location.hash = '#/projects/project-1/settings';
  vi.mocked(api.listConnections).mockResolvedValue({
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
  });
});

test('shows a fail-closed setup state when the local vault is unavailable', () => {
  render(
    <ConnectionVault
      projectId="project-1"
      settings={{ enabled: false, local_only: true, kinds: ['s3', 'notion', 'confluence'] }}
    />,
  );
  expect(screen.getByText('Encrypted connections are disabled')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Add connection' })).not.toBeInTheDocument();
});

test('submits credentials once then clears them from DOM, URL and browser storage', async () => {
  const user = userEvent.setup();
  const access = 'AKIA-PRIVATE-1234';
  const secret = 'never-stay-in-the-browser';
  vi.mocked(api.createConnection).mockResolvedValue(saved);
  render(<ConnectionVault projectId="project-1" settings={settings} />);
  await screen.findByText('No credentials are stored for this project.');
  await user.click(screen.getByRole('button', { name: 'Add connection' }));
  await user.type(screen.getByLabelText('Connection name'), 'Warehouse');
  await user.type(screen.getByLabelText('Access key ID'), access);
  await user.type(screen.getByLabelText('Secret access key'), secret);
  await user.click(screen.getByRole('button', { name: 'Save encrypted connection' }));

  await waitFor(() =>
    expect(api.createConnection).toHaveBeenCalledWith('project-1', 'Warehouse', {
      kind: 's3',
      access_key_id: access,
      secret_access_key: secret,
    }),
  );
  expect(document.body.textContent).not.toContain(access);
  expect(document.body.textContent).not.toContain(secret);
  expect(document.querySelector(`input[value="${secret}"]`)).toBeNull();
  expect(window.location.href).not.toContain(secret);
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(secret);
  expect(screen.getAllByText('Access key ••••1234', { exact: false })).toHaveLength(2);
});

test('clears failed submissions and supports safe test and credential rotation states', async () => {
  const user = userEvent.setup();
  const failedSecret = 'failed-private-value';
  vi.mocked(api.listConnections).mockResolvedValue({
    items: [saved],
    total: 1,
    limit: 20,
    offset: 0,
  });
  vi.mocked(api.testConnection).mockResolvedValue({
    ...saved,
    status: 'unavailable',
    last_error: 'Connection testing is unavailable until this connector is installed.',
  });
  vi.mocked(api.rotateConnection).mockRejectedValueOnce(new Error('Rotation was rejected safely.'));
  render(<ConnectionVault projectId="project-1" settings={settings} />);
  await screen.findByRole('button', { name: 'Test connection' });
  await user.click(screen.getByRole('button', { name: 'Test connection' }));
  expect(await screen.findByText(/testing is unavailable/)).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Rotate credentials' }));
  await user.type(screen.getByLabelText('Access key ID'), 'replacement-id');
  await user.type(screen.getByLabelText('Secret access key'), failedSecret);
  await user.click(screen.getByRole('button', { name: 'Rotate credentials' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Rotation was rejected safely.');
  expect(screen.getByLabelText('Secret access key')).toHaveValue('');
  expect(document.body.textContent).not.toContain(failedSecret);
});
