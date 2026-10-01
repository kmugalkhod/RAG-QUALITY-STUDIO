import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Upload } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { bytes, message } from '../documentPresentation';
import type { Document } from '../model';
import { uploadDocument } from '../api';
import { docsHref } from '../../../lib/docs';
import { cn } from '../../../lib/utils';
import { CARD, InlineError, LINK, META } from '../../../components/parts';

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
      setError('Choose a supported document file.');
      return;
    }
    if (
      !/\.(pdf|txt|md|markdown|html|htm|docx|pptx|csv|tsv|xlsx)$/i.test(file.name) ||
      !file.size ||
      (limit && file.size > limit)
    ) {
      setError('Choose a nonempty supported document within the upload limit.');
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
      className={cn(CARD, 'flex flex-col gap-4 p-6 max-md:p-4')}
      aria-labelledby="upload-title"
    >
      <h2 id="upload-title" className="text-base font-semibold text-foreground">
        Add a document
      </h2>
      <form
        className="flex flex-col gap-4 md:flex-row md:items-start"
        onSubmit={submit}
        aria-busy={uploading}
      >
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <Label htmlFor="document-file" className="mb-0">
            Document file
          </Label>
          <Input
            ref={fileInput}
            id="document-file"
            type="file"
            accept=".pdf,.txt,.md,.markdown,.html,.htm,.docx,.pptx,.csv,.tsv,.xlsx"
            disabled={uploading || !limit}
            aria-describedby="upload-hint"
          />
          <p className={META} id="upload-hint">
            One file per upload. {limit ? `Maximum ${bytes(limit)}.` : 'Loading upload limit…'} PDF,
            TXT, Markdown, HTML, DOCX, PPTX, CSV, TSV, or XLSX. Scanned PDFs use the saved OCR
            policy.
          </p>
          <a
            className={cn(LINK, 'self-start')}
            href={docsHref('knowledge-base/documents')}
            target="_blank"
            rel="noopener noreferrer"
          >
            Supported files and upload help
          </a>
        </div>
        <Button disabled={uploading || !limit} type="submit" className="md:mt-6">
          <Upload aria-hidden="true" />
          {uploading ? 'Uploading…' : 'Upload document'}
        </Button>
      </form>
      {settingsError && (
        <InlineError onRetry={onRetrySettings} retryLabel="Retry upload settings">
          {settingsError}
        </InlineError>
      )}
      {error && <InlineError>{error}</InlineError>}
    </section>
  );
}
