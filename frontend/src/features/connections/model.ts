import type { Page } from '../../lib/pagination';

export type ConnectionKind = 's3' | 'notion' | 'confluence';
export type ConnectionStatus = 'untested' | 'valid' | 'invalid' | 'unavailable';

export interface SourceConnection {
  id: string;
  project_id: string;
  name: string;
  kind: ConnectionKind;
  status: ConnectionStatus;
  redacted_summary: string[];
  last_error: string | null;
  last_tested_at: string | null;
  rotated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConnectionSettings {
  enabled: boolean;
  local_only: true;
  kinds: ConnectionKind[];
}

export type ConnectionPage = Page<SourceConnection>;

export type Credentials =
  | {
      kind: 's3';
      access_key_id: string;
      secret_access_key: string;
      session_token?: string;
    }
  | { kind: 'notion'; integration_token: string }
  | { kind: 'confluence'; site_url: string; email: string; api_token: string };
