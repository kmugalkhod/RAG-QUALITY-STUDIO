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
    <section className="create-project-panel" aria-labelledby="create-title">
      <header className="create-project-header">
        <span className="create-project-icon" aria-hidden="true">
          <FolderPlus />
        </span>
        <div className="create-project-heading">
          <p>New workspace</p>
          <h2 id="create-title">Create a project</h2>
          <span>Give your sources, pipelines, and experiments a shared home.</span>
        </div>
        <Button
          className="create-project-close"
          variant="ghost"
          size="icon"
          aria-label="Close project form"
          disabled={saving}
          onClick={onClose}
        >
          <X />
        </Button>
      </header>
      <form className="create-project-form" onSubmit={submit} noValidate aria-busy={saving}>
        <div className="create-project-fields">
          <div className="create-project-field">
            <div className="create-project-label">
              <Label htmlFor="project-name">Project name</Label>
              <span>Required</span>
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
            <div className="create-project-field-meta">
              <p id="name-hint">Used in navigation and experiment history.</p>
              <span id="name-count">{name.length}/120</span>
            </div>
          </div>
          <div className="create-project-field">
            <div className="create-project-label">
              <Label htmlFor="project-description">Description</Label>
              <span>Optional</span>
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
            <div className="create-project-field-meta">
              <p id="description-hint">Help collaborators understand the project’s scope.</p>
              <span id="description-count">{description.length}/2,000</span>
            </div>
          </div>
        </div>
        {error && (
          <p id="form-error" role="alert" className="error-message">
            {error}
          </p>
        )}
        <footer className="create-project-footer">
          <p>You can add documents and configure pipelines after creation.</p>
          <div className="create-project-actions">
            <Button type="button" variant="outline" disabled={saving} onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? 'Creating…' : 'Create project'}
              <ArrowRight />
            </Button>
          </div>
        </footer>
      </form>
    </section>
  );
}
