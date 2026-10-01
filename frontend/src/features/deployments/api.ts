import { request } from '../../lib/api';
import type { Page } from '../../lib/pagination';

export type DeploymentState = 'paused' | 'active' | 'archived';
export type Limits = {
  rate_per_minute: number;
  concurrent_runs: number;
  queued_runs: number;
  daily_budget_usd: string;
  monthly_budget_usd: string;
};
export type Permissions = { role: 'owner' | 'admin' | 'editor' | 'viewer'; can_manage: boolean };
export type Deployment = {
  id: string;
  organization_id: string;
  project_id: string;
  pipeline_id: string;
  name: string;
  state: DeploymentState;
  active_release_id: string | null;
  revision: number;
  accepting_questions: boolean;
  created_at: string;
  limits: Limits;
  releases?: Release[];
};
export type Release = {
  id: string;
  release_number: number;
  pipeline_version_id: string;
  index_id: string;
  execution_sha256: string;
  embedding_sha256: string;
  schema_version: number;
  runtime_contract_version: number;
  created_at: string;
  note: string;
};
export type KeyMetadata = {
  id: string;
  prefix: string;
  client_id: string;
  label: string;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  rotation_of_key_id: string | null;
};
export type CreatedKey = KeyMetadata & { secret: string };
export type RunSummary = {
  id: string;
  release_id: string;
  status: string;
  stage: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_code: string | null;
  cost_reservation_usd: string;
};

const root = (projectId: string) => `/projects/${encodeURIComponent(projectId)}/answer-deployments`;
const item = (projectId: string, id: string) => `${root(projectId)}/${encodeURIComponent(id)}`;
const json = (body: unknown, revision?: number): RequestInit => ({
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Idempotency-Key': crypto.randomUUID(),
    ...(revision !== undefined ? { 'If-Match': `"${revision}"` } : {}),
  },
  body: JSON.stringify(body),
});

export const permissions = (projectId: string) =>
  request<Permissions>(`${root(projectId)}/permissions`);
export const list = (projectId: string, offset = 0) =>
  request<Page<Deployment>>(`${root(projectId)}?offset=${offset}`);
export const detail = (projectId: string, id: string) => request<Deployment>(item(projectId, id));
export const updateLimits = (projectId: string, id: string, limits: Limits, revision: number) =>
  request<Deployment>(`${item(projectId, id)}/limits`, {
    ...json(limits, revision),
    method: 'PUT',
  });
export const releases = (projectId: string, id: string, offset = 0) =>
  request<Page<Release>>(`${item(projectId, id)}/releases?offset=${offset}`);
export const keys = (projectId: string, id: string) =>
  request<{ items: KeyMetadata[] }>(`${item(projectId, id)}/keys`);
export const runs = (projectId: string, id: string, offset = 0) =>
  request<Page<RunSummary>>(`${item(projectId, id)}/runs?offset=${offset}`);
export const create = (
  projectId: string,
  body: {
    name: string;
    pipeline_id: string;
    pipeline_version_id: string;
    index_id: string;
    note: string;
  },
) => request<Deployment>(root(projectId), json(body));
export const stage = (
  projectId: string,
  id: string,
  body: { pipeline_version_id: string; index_id: string; note: string },
) => request<Release>(`${item(projectId, id)}/releases`, json(body));
export const promote = (
  projectId: string,
  id: string,
  releaseId: string,
  reason: string,
  revision: number,
) =>
  request<Deployment>(
    `${item(projectId, id)}/promotions`,
    json({ release_id: releaseId, reason }, revision),
  );
export const pause = (projectId: string, id: string, revision: number) =>
  request<Deployment>(`${item(projectId, id)}/pause`, json({}, revision));
export const resume = (projectId: string, id: string, revision: number) =>
  request<Deployment>(`${item(projectId, id)}/resume`, json({}, revision));
export const archive = (projectId: string, id: string, reason: string, revision: number) =>
  request<Deployment>(`${item(projectId, id)}/archive`, json({ reason }, revision));
export const createKey = (projectId: string, id: string, label: string) =>
  request<CreatedKey>(`${item(projectId, id)}/keys`, json({ label }));
export const rotateKey = (projectId: string, id: string, keyId: string) =>
  request<CreatedKey>(`${item(projectId, id)}/keys/${encodeURIComponent(keyId)}/rotate`, {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  });
export const revokeKey = (projectId: string, id: string, keyId: string) =>
  request<KeyMetadata>(`${item(projectId, id)}/keys/${encodeURIComponent(keyId)}/revoke`, {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  });
export const cancelRun = (projectId: string, id: string, runId: string) =>
  request<RunSummary>(`${item(projectId, id)}/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  });

export type WidgetSettings = {
  deployment_id: string;
  enabled: boolean;
  public_enabled: boolean;
  allowed_origins: string[];
  branding: {
    title: string;
    greeting: string;
    color: 'blue' | 'slate' | 'green';
    position: 'left' | 'right';
  };
  revision: number;
};
export const widgetSettings = (projectId: string, id: string) =>
  request<WidgetSettings>(`${item(projectId, id)}/widget`);
export const updateWidgetSettings = (
  projectId: string,
  id: string,
  body: Omit<WidgetSettings, 'deployment_id' | 'revision'>,
  revision: number,
) =>
  request<WidgetSettings>(`${item(projectId, id)}/widget`, {
    ...json(body, revision),
    method: 'PUT',
  });
