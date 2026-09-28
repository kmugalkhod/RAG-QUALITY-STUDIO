export const API_ORIGIN = import.meta.env.VITE_WIDGET_API_ORIGIN || 'http://127.0.0.1:8000';
export const VERSION = '1.0.0';
export type Branding = { title: string; greeting: string; color: 'blue' | 'slate' | 'green'; position: 'left' | 'right' };
export type Config = { protocol_version: string; deployment_id: string; enabled: boolean; public_enabled: boolean; allowed_origins: string[]; branding: Branding };
export type Citation = { label?: string; title?: string; page?: number; rank?: number; excerpt?: string; text?: string; source_id?: string };
export type Answer = { id: string; status: string; answer?: string; insufficient_evidence?: boolean; citations?: Citation[]; message?: string; error_code?: string; release_number?: number };
export class WidgetError extends Error {
  constructor(readonly status: number, readonly code: string, readonly retryAfter = 0) { super(code); }
}
export async function api<T>(deployment: string, path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_ORIGIN}/v1/answer-deployments/${deployment}/widget${path}`, {
    ...init,
    cache: 'no-store',
    headers: { Authorization: `Bearer ${token}`, ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { error?: { code?: string } };
    throw new WidgetError(response.status, body.error?.code || 'request_failed', Number(response.headers.get('Retry-After') || 0));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export async function publicConfig(deployment: string): Promise<Config> {
  const response = await fetch(`${API_ORIGIN}/v1/answer-deployments/${deployment}/widget/config`, { cache: 'no-store' });
  if (!response.ok) throw new Error('Widget unavailable');
  const value = await response.json() as Config;
  if (value.protocol_version !== VERSION || value.deployment_id !== deployment) throw new Error('Widget version mismatch');
  return value;
}
export async function publicToken(deployment: string, visitor: string, siteOrigin: string): Promise<{ token: string; expires_at: string }> {
  const response = await fetch(`${API_ORIGIN}/v1/answer-deployments/${deployment}/widget/public-token`, {
    method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ visitor_session_id: visitor, site_origin: siteOrigin }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { error?: { code?: string } };
    throw new WidgetError(response.status, body.error?.code || 'request_failed', Number(response.headers.get('Retry-After') || 0));
  }
  return response.json() as Promise<{ token: string; expires_at: string }>;
}
