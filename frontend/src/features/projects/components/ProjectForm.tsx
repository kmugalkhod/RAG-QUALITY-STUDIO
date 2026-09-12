import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowRight, X } from 'lucide-react';
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
      className="create-panel mt-8 rounded-lg border border-border bg-background p-6"
      aria-labelledby="create-title"
    >
      <div className="section-heading flex items-center justify-between gap-4">
        <h2 id="create-title">Create a project</h2>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Close project form"
          disabled={saving}
          onClick={onClose}
        >
          <X />
        </Button>
      </div>
      <form onSubmit={submit} noValidate aria-busy={saving}>
        <div className="form-grid grid grid-cols-2 gap-6">
          <div>
            <Label htmlFor="project-name">
              Project name <span>Required</span>
            </Label>
            <Input
              ref={nameInput}
              id="project-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={120}
              required
              disabled={saving}
              aria-invalid={!!error}
              aria-describedby={error ? 'form-error' : 'name-hint'}
              placeholder="Customer support knowledge"
            />
            <p className="field-hint" id="name-hint">
              A clear name, up to 120 characters.
            </p>
          </div>
          <div>
            <Label htmlFor="project-description">
              Description <span>Optional</span>
            </Label>
            <Textarea
              id="project-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={2000}
              rows={3}
              disabled={saving}
              placeholder="What will this project evaluate?"
            />
          </div>
        </div>
        {error && (
          <p id="form-error" role="alert" className="error-message">
            {error}
          </p>
        )}
        <div className="form-actions mt-5 flex justify-end gap-3">
          <Button type="button" variant="outline" disabled={saving} onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? 'Creating…' : 'Create project'}
            <ArrowRight />
          </Button>
        </div>
      </form>
    </section>
  );
}
