import { useEffect, useState } from 'react';
import { getProject, listProjects, type Project } from '../features/projects/api';
import { allPages } from '../lib/pagination';

export function useWorkspaceProjects(projectId: string | undefined) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project>();
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let disposed = false;
    void allPages(listProjects)
      .then((projects) => {
        if (!disposed) {
          setProjects(projects);
        }
      })
      .catch(() => {
        // The Projects page provides list errors and retry controls.
      });
    return () => {
      disposed = true;
    };
  }, [revision]);

  useEffect(() => {
    let disposed = false;
    setError('');
    if (!projectId) {
      setProject(undefined);
      return;
    }
    void getProject(projectId)
      .then((project) => {
        if (!disposed) {
          setProject(project);
        }
      })
      .catch((error: unknown) => {
        if (!disposed) {
          setError(error instanceof Error ? error.message : 'Could not load the project.');
        }
      });
    return () => {
      disposed = true;
    };
  }, [projectId, revision]);

  return {
    projects,
    current: project?.id === projectId ? project : undefined,
    error,
    refresh: () => setRevision((revision) => revision + 1),
  };
}
