import { postJson, request } from '../../lib/api';
import type { Page } from '../../lib/pagination';

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
}
export type ProjectPage = Page<Project>;

export function getProject(projectId: string): Promise<Project> {
  return request<Project>(`/projects/${encodeURIComponent(projectId)}`);
}

export function listProjects(offset = 0): Promise<ProjectPage> {
  return request<ProjectPage>(`/projects?limit=20&offset=${offset}`);
}

export function createProject(data: Pick<Project, 'name' | 'description'>): Promise<Project> {
  return postJson<Project>('/projects', data);
}
