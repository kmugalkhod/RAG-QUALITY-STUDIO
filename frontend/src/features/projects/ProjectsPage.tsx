import { useCallback, useEffect, useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { listProjects, type Project, type ProjectPage } from './api';
import { ProjectForm } from './components/ProjectForm';
import { ProjectList } from './components/ProjectList';
import { useAuth } from '@clerk/react';
import { postJson } from '../../lib/api';

function ClaimExistingProjects({ onClaimed }: { onClaimed: () => void }) {
  const { orgRole } = useAuth();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  if (orgRole !== 'org:admin') {
    return null;
  }
  return (
    <div className="mb-6">
      <Button
        variant="outline"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            const result = await postJson<{ claimed: number }>('/projects/claim-unowned', {});
            setMessage(
              `${result.claimed} existing ${result.claimed === 1 ? 'project' : 'projects'} added to your workspace.`,
            );
            onClaimed();
          } catch (error) {
            setMessage((error as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Claim existing projects
      </Button>
      {message && <p role="status">{message}</p>}
    </div>
  );
}

export function ProjectsPage({ onCreated }: { onCreated?: () => void }) {
  const [page, setPage] = useState<ProjectPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const requestId = useRef(0);
  const newButton = useRef<HTMLButtonElement>(null);

  const load = useCallback(async (nextOffset: number) => {
    const id = ++requestId.current;
    setLoading(true);
    setError('');
    try {
      const result = await listProjects(nextOffset);
      if (id === requestId.current) {
        setPage(result);
      }
    } catch (cause) {
      if (id === requestId.current) {
        setError((cause as Error).message);
      }
    } finally {
      if (id === requestId.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void load(offset);
    return () => {
      requestId.current += 1;
    };
  }, [offset, load]);

  function closeForm() {
    setFormOpen(false);
    requestAnimationFrame(() => newButton.current?.focus());
  }

  function handleCreated(project: Project) {
    onCreated?.();
    closeForm();
    setNotice(`Project “${project.name}” created.`);
    if (offset === 0) {
      void load(0);
    } else {
      setOffset(0);
    }
  }

  const isCreatingFirstProject =
    formOpen && !loading && !error && page?.items.length === 0 && offset === 0;

  return (
    <>
      <div className="page-heading mb-8 flex items-start justify-between gap-6">
        <div>
          <h1>Projects</h1>
          <p>Manage your sources, pipelines, and answers.</p>
        </div>
        <Button
          ref={newButton}
          onClick={() => {
            setFormOpen(true);
            setNotice('');
          }}
          disabled={formOpen}
        >
          <Plus />
          New project
        </Button>
      </div>
      {notice && (
        <p role="status" className="success-message">
          {notice}
        </p>
      )}
      {import.meta.env.VITE_CLERK_PUBLISHABLE_KEY && (
        <ClaimExistingProjects
          onClaimed={() => {
            void load(0);
            onCreated?.();
          }}
        />
      )}
      {formOpen && <ProjectForm onClose={closeForm} onCreated={handleCreated} />}
      {!isCreatingFirstProject && (
        <ProjectList
          page={page}
          offset={offset}
          loading={loading}
          error={error}
          formOpen={formOpen}
          onRefresh={() => void load(offset)}
          onPage={setOffset}
          onCreate={() => setFormOpen(true)}
        />
      )}
    </>
  );
}
