import { Check, FileText, Square, X } from 'lucide-react';

import { Pagination } from '../../../components/Pagination';
import { Button } from '../../../components/ui/button';
import type { Page } from '../../../lib/pagination';
import { terminalIngestionStatuses } from '../editorModel';
import type { IngestionRun, IngestionRunItem, SourcePreview, SourcePreviewItem } from '../model';

export function IngestionPreviewResults({
  preview,
  page,
  busy,
  onCancel,
  onPageChange,
}: {
  preview: SourcePreview;
  page: Page<SourcePreviewItem>;
  busy: boolean;
  onCancel: () => void;
  onPageChange: (offset: number) => void;
}) {
  return (
    <section
      id="ingestion-preview"
      className="surface-section ingestion-results"
      aria-live="polite"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Source preview</p>
          <h2>
            {preview.included_count} included · {preview.excluded_count} excluded
          </h2>
          <p>
            {preview.status} · {preview.progress}% · {preview.duplicate_count} duplicate ·{' '}
            {preview.failed_count} failed
          </p>
        </div>
        {!terminalIngestionStatuses.has(preview.status) && (
          <Button variant="outline" onClick={onCancel}>
            <Square size={14} />
            Cancel preview
          </Button>
        )}
      </div>
      {preview.error && (
        <p role="alert" className="error-message">
          {preview.error}
        </p>
      )}
      <ul className="project-list">
        {page.items.map((item) => (
          <li key={`${item.source_node_id}-${item.ordinal}`}>
            {item.status === 'included' ? <Check size={18} /> : <X size={18} />}
            <div>
              <strong>{item.display_name}</strong>
              <p>
                {item.status} · {item.reason}
                {item.depth !== null ? ` · depth ${item.depth}` : ''}
                {item.size_bytes !== null ? ` · ${item.size_bytes} bytes` : ''}
              </p>
              {item.canonical_location && <small>{item.canonical_location}</small>}
              {item.provider_revision && <small>Provider revision: {item.provider_revision}</small>}
            </div>
          </li>
        ))}
      </ul>
      {terminalIngestionStatuses.has(preview.status) && page.total === 0 && (
        <p>No preview items were discovered.</p>
      )}
      <Pagination
        offset={page.offset}
        total={page.total}
        pageSize={page.limit}
        busy={busy}
        label="Source preview pages"
        onChange={onPageChange}
      />
    </section>
  );
}

export function IngestionRunResults({
  projectId,
  run,
  items,
}: {
  projectId: string;
  run: IngestionRun;
  items: IngestionRunItem[];
}) {
  return (
    <section
      className="surface-section ingestion-results ingestion-run-details"
      aria-labelledby="ingestion-run-details-heading"
    >
      <div className="section-heading">
        <div>
          <h2 id="ingestion-run-details-heading">Run details</h2>
          {(run.new_count > 0 ||
            run.changed_count > 0 ||
            run.unchanged_count > 0 ||
            run.removed_count > 0) && (
            <p>
              {run.new_count} new · {run.changed_count} changed · {run.unchanged_count} unchanged ·{' '}
              {run.removed_count} removed
            </p>
          )}
        </div>
      </div>
      {run.error && (
        <p role="alert" className="error-message">
          {run.error}
        </p>
      )}
      {run.status === 'succeeded' && run.published_index_id && (
        <Button asChild variant="outline">
          <a
            href={`#/projects/${projectId}/knowledge-base?view=indexes&index=${run.published_index_id}`}
          >
            Inspect published index v{run.published_index_version}
          </a>
        </Button>
      )}
      <ul className="project-list">
        {items.map((item) => (
          <li key={item.source_kind !== 'existing_files' ? item.ordinal : item.document_id}>
            <FileText size={18} />
            <div>
              {item.source_kind !== 'existing_files' ? (
                <>
                  <strong>{item.display_name}</strong>
                  <p>
                    {item.outcome} · {item.status} · {item.chunk_count} chunks · {item.reason}
                  </p>
                  {item.canonical_location && <small>{item.canonical_location}</small>}
                </>
              ) : (
                <>
                  <strong>{item.filename}</strong>
                  <p>
                    {item.status} · processing v{item.processing_version} · {item.chunk_count}{' '}
                    chunks · {item.content_hash.slice(0, 12)}
                  </p>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
