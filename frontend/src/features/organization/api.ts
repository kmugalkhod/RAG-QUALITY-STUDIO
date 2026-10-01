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

export type ChatModel = {
  id: string;
  label: string;
  context_tokens: number;
  prompt_usd_per_mtok: number | null;
  completion_usd_per_mtok: number | null;
  catalog_fetched_at: string | null;
  source: 'server' | 'organization';
  is_default: boolean;
};

export type ChatModels = {
  scope: 'organization' | 'instance';
  can_manage: boolean;
  context_ceiling: number;
  default_model: string | null;
  models: ChatModel[];
};

export type CatalogModel = {
  id: string;
  name: string;
  context_length: number;
  prompt_usd_per_mtok: number | null;
  completion_usd_per_mtok: number | null;
  approved: boolean;
};

export type CatalogPage = {
  items: CatalogModel[];
  total: number;
  offset: number;
  limit: number;
  fetched_at: string;
};

const modelsPath = '/organizations/current/chat-models';

export function getChatModels(): Promise<ChatModels> {
  return request(modelsPath);
}

export function searchCatalog(q: string, offset: number, limit = 25): Promise<CatalogPage> {
  const params = new URLSearchParams({ q, offset: String(offset), limit: String(limit) });
  return request(`${modelsPath}/catalog?${params}`);
}

export function approveChatModel(modelId: string): Promise<ChatModels> {
  return postJson(modelsPath, { model_id: modelId });
}

export function setDefaultChatModel(modelId: string): Promise<ChatModels> {
  return request(`${modelsPath}/default`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId }),
  });
}

export function removeChatModel(modelId: string): Promise<ChatModels> {
  return postJson(`${modelsPath}/remove`, { model_id: modelId });
}
