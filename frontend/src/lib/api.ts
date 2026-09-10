export interface Project { id: string; name: string; description: string; created_at: string }
export interface ProjectPage { items: Project[]; total: number; limit: number; offset: number }

export async function request<T>(path: string, options: RequestInit = {}, timeoutMs = 12000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...options, signal: controller.signal });
  } catch {
    throw new Error('Could not reach the server. Check your connection and try again.');
  } finally { window.clearTimeout(timeout); }
  if (!response.ok) {
    if (path.includes('/documents') || path.includes('/runs') || path.includes('/query-runs') || path.includes('/indexes') || path.includes('/retrieval')) {
      const error = await response.json().catch(() => ({})) as { detail?: unknown };
      throw new Error(typeof error.detail === 'string' ? error.detail : 'Check the file and chunk settings, then try again.');
    }
    if (response.status === 422) throw new Error('Check the project name (1–120 characters) and description (up to 2,000 characters).');
    throw new Error(response.status === 503 ? 'The database is temporarily unavailable. Please try again.' : 'The request failed. Please try again.');
  }
  return response.json() as Promise<T>;
}
export const listProjects = (offset = 0) => request<ProjectPage>(`/projects?limit=20&offset=${offset}`);
export const createProject = (data: { name: string; description: string }) => request<Project>('/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
