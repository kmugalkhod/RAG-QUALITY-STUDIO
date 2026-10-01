import { postJson, request } from '../../lib/api';

export type ProviderKey = {
  provider: 'openrouter';
  scope: 'organization' | 'instance';
  configured: boolean;
  status: 'active' | 'rejected' | null;
  redacted_hint: string | null;
  updated_by: string | null;
  updated_at: string | null;
  last_verified_at: string | null;
  environment_fallback: boolean;
  can_manage: boolean;
  storage_available: boolean;
};

const path = '/organizations/current/provider-credentials';

export function getProviderKey(): Promise<ProviderKey> {
  return request(path);
}

// The key is write-only: responses carry only a redacted hint.
export function saveProviderKey(apiKey: string): Promise<ProviderKey> {
  return request(`${path}/openrouter`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export function testProviderKey(): Promise<ProviderKey> {
  return postJson(`${path}/openrouter/test`, {});
}

export function deleteProviderKey(): Promise<ProviderKey> {
  return request(`${path}/openrouter`, { method: 'DELETE' });
}
