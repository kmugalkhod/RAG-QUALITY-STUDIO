import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowRight, FolderPlus, X } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { createProject, type Project } from '../api';

export function ProjectForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (project: Project) => void;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const nameInput = useRef<HTMLInputElement>(null);
  useEffect(() => nameInput.current?.focus(), []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (saving) {
      return;
    }
    if (!name.trim() || name.trim().length > 120 || description.trim().length > 2000) {
      setError(
        'Enter a project name of 1–120 characters and a description of up to 2,000 characters.',
      );
      nameInput.current?.focus();
      return;
    }
    setSaving(true);
    setError('');
    try {
      onCreated(await createProject({ name: name.trim(), description: description.trim() }));
    } catch (cause) {
      setError(
        `${(cause as Error).message} Refresh the project list before retrying an interrupted request.`,
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <section
      className="flex flex-col rounded-card border border-border bg-surface"
      aria-labelledby="create-title"
    >
      <header className="flex items-start gap-4 border-b border-border p-6">
        <span
          className="hidden size-control-md shrink-0 items-center justify-center rounded-control border border-border text-foreground-muted md:flex"
          aria-hidden="true"
        >
          <FolderPlus className="size-(--icon-lg)" />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="text-xs text-foreground-muted">New workspace</p>
          <h2 id="create-title" className="text-base font-semibold text-foreground">
            Create a project
          </h2>
          <p className="text-sm text-foreground-muted">
            Give your sources, pipelines, and experiments a shared home.
          </p>
        </div>
        <Button
          variant="ghost"
          icon
          aria-label="Close project form"
          disabled={saving}
          onClick={onClose}
        >
          <X aria-hidden="true" />
        </Button>
      </header>
      <form onSubmit={submit} noValidate aria-busy={saving}>
        <div className="grid gap-6 p-6 md:grid-cols-2">
          <div className="flex flex-col">
            <div className="flex items-baseline justify-between gap-2">
              <Label htmlFor="project-name">Project name</Label>
              <span className="text-xs text-foreground-muted">Required</span>
            </div>
            <Input
              ref={nameInput}
              id="project-name"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                setError('');
              }}
              maxLength={120}
              required
              disabled={saving}
              aria-invalid={!!error}
              aria-describedby={error ? 'name-hint name-count form-error' : 'name-hint name-count'}
              placeholder="Customer support knowledge"
            />
            <div className="mt-2 flex justify-between gap-4 text-xs text-foreground-muted">
              <p id="name-hint">Used in navigation and experiment history.</p>
              <span id="name-count" className="tabular-nums">
                {name.length}/120
              </span>
            </div>
          </div>
          <div className="flex flex-col">
            <div className="flex items-baseline justify-between gap-2">
              <Label htmlFor="project-description">Description</Label>
              <span className="text-xs text-foreground-muted">Optional</span>
            </div>
            <Textarea
              id="project-description"
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
                setError('');
              }}
              maxLength={2000}
              rows={4}
              disabled={saving}
              aria-describedby="description-hint description-count"
              placeholder="What will this project evaluate?"
            />
            <div className="mt-2 flex justify-between gap-4 text-xs text-foreground-muted">
              <p id="description-hint">Help collaborators understand the project’s scope.</p>
              <span id="description-count" className="tabular-nums">
                {description.length}/2,000
              </span>
            </div>
          </div>
        </div>
        {error && (
          <p id="form-error" role="alert" className="px-6 pb-4 text-sm text-danger">
            {error}
          </p>
        )}
        <footer className="flex flex-col gap-4 border-t border-border p-6 md:flex-row md:items-center md:justify-between">
          <p className="text-xs text-foreground-muted">
            You can add documents and configure pipelines after creation.
          </p>
          <div className="flex flex-col-reverse gap-2 md:flex-row">
            <Button type="button" variant="outline" disabled={saving} onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              Create project
              <ArrowRight aria-hidden="true" />
            </Button>
          </div>
        </footer>
      </form>
    </section>
  );
}
