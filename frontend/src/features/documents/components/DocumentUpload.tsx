import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Upload } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { bytes, message } from '../documentPresentation';
import type { Document } from '../model';
import { uploadDocument } from '../api';

export function DocumentUpload({
  projectId,
  limit,
  settingsError,
  onRetrySettings,
  onUploaded,
}: {
  projectId: string;
  limit?: number;
  settingsError: string;
  onRetrySettings: () => void;
  onUploaded: (document: Document) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => fileInput.current?.focus(), []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    setError('');
    if (!file) {
      setError('Choose a PDF or UTF-8 TXT file.');
      return;
    }
    if (!/\.(pdf|txt)$/i.test(file.name) || !file.size || (limit && file.size > limit)) {
      setError('Choose a nonempty PDF or UTF-8 TXT within the upload limit.');
      return;
    }
    setUploading(true);
    try {
      onUploaded(await uploadDocument(projectId, file));
    } catch (uploadError) {
      setError(
        `${message(uploadError)} Refresh the list before retrying an interrupted upload; repeated uploads create separate documents.`,
      );
    } finally {
      setUploading(false);
    }
  }

  return (
    <section
      id="upload-panel"
      className="mx-7 my-4 rounded-md border border-border bg-background p-5"
      aria-labelledby="upload-title"
    >
      <h2 id="upload-title">Add a document</h2>
      <form className="mt-4 flex items-end gap-4" onSubmit={submit} aria-busy={uploading}>
        <div className="min-w-0 flex-1">
          <Label htmlFor="document-file">PDF or UTF-8 TXT</Label>
          <Input
            ref={fileInput}
            id="document-file"
            type="file"
            accept=".pdf,.txt"
            disabled={uploading || !limit}
            aria-describedby="upload-hint"
          />
          <p className="field-hint" id="upload-hint">
            One file per upload. {limit ? `Maximum ${bytes(limit)}.` : 'Loading upload limit…'}{' '}
            Scanned PDFs require OCR and are unsupported.
          </p>
        </div>
        <Button disabled={uploading || !limit} type="submit">
          <Upload />
          {uploading ? 'Uploading…' : 'Upload document'}
        </Button>
      </form>
      {settingsError && (
        <div className="mt-4 flex items-center gap-3">
          <p role="alert" className="error-message">
            {settingsError}
          </p>
          <Button variant="outline" onClick={onRetrySettings}>
            Retry upload settings
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
    </section>
  );
}
