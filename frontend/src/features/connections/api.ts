import { postJson, request } from '../../lib/api';
import type { ConnectionPage, ConnectionSettings, Credentials, SourceConnection } from './model';

const path = (projectId: string) => `/projects/${encodeURIComponent(projectId)}/source-connections`;

export function getConnectionSettings(projectId: string): Promise<ConnectionSettings> {
  return request(`${path(projectId)}/settings`);
}

export function listConnections(projectId: string, offset = 0): Promise<ConnectionPage> {
  return request(`${path(projectId)}?offset=${offset}`);
}

export function createConnection(
  projectId: string,
  name: string,
  credentials: Credentials,
): Promise<SourceConnection> {
  return postJson(path(projectId), { name, credentials });
}

export function testConnection(projectId: string, connectionId: string): Promise<SourceConnection> {
  return postJson(`${path(projectId)}/${encodeURIComponent(connectionId)}/test`, {});
}

export function rotateConnection(
  projectId: string,
  connectionId: string,
  credentials: Credentials,
): Promise<SourceConnection> {
  return postJson(`${path(projectId)}/${encodeURIComponent(connectionId)}/rotate`, {
    credentials,
  });
}

export function rewrapConnection(
  projectId: string,
  connectionId: string,
): Promise<SourceConnection> {
  return postJson(`${path(projectId)}/${encodeURIComponent(connectionId)}/rewrap`, {});
}
