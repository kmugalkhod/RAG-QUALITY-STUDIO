import { useCallback, useEffect, useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import { PageHeader } from '../../components/PageHeader';
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
    <div className="flex flex-col items-start gap-2">
      <Button
        variant="outline"
        loading={busy}
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
      {message && (
        <p role="status" className="text-sm text-foreground-muted">
          {message}
        </p>
      )}
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
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Projects"
        meta="Manage your sources, pipelines, and answers."
        action={
          <Button
            ref={newButton}
            onClick={() => {
              setFormOpen(true);
              setNotice('');
            }}
            disabled={formOpen}
          >
            <Plus aria-hidden="true" />
            New project
          </Button>
        }
      />
      {notice && (
        <p role="status" className="text-sm font-medium text-success">
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
    </div>
  );
}
