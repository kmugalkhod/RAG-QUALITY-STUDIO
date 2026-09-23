import { useRef } from 'react';
import {
  ArrowRight,
  CircleAlert,
  FileCheck2,
  FileClock,
  FileText,
  LoaderCircle,
  RotateCw,
  Trash2,
} from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { StatusBadge } from '../../../components/StatusBadge';
import { Pagination } from '../../../components/Pagination';
import { active, bytes, date } from '../documentPresentation';
import type { Document } from '../model';

export type DocumentGroup = {
  document: Document;
  uploadCount: number;
  createdAt: string;
};

const statusPriority: Record<string, number> = {
  running: 5,
  queued: 4,
  succeeded: 3,
  failed: 2,
  cancelled: 1,
  uploaded: 0,
};

/** Exact-content uploads share a SHA-256 and represent one source in the UI. */
export function groupDocuments(documents: Document[]): DocumentGroup[] {
  const groups = new Map<string, Document[]>();
  for (const document of documents) {
    const key = document.content_hash || document.id;
    groups.set(key, [...(groups.get(key) ?? []), document]);
  }
  return Array.from(groups.values()).map((matches) => {
    const ranked = [...matches].sort((a, b) => {
      const aStatus = a.latest_run?.status ?? 'uploaded';
      const bStatus = b.latest_run?.status ?? 'uploaded';
      return (
        (statusPriority[bStatus] ?? 0) - (statusPriority[aStatus] ?? 0) ||
        (b.latest_run?.version ?? 0) - (a.latest_run?.version ?? 0) ||
        Date.parse(b.created_at) - Date.parse(a.created_at)
      );
    });
    return {
      document: ranked[0],
      uploadCount: matches.length,
      createdAt: matches.reduce(
        (latest, match) =>
          Date.parse(match.created_at) > Date.parse(latest) ? match.created_at : latest,
        matches[0].created_at,
      ),
    };
  });
}

function presentation(document: Document) {
  const run = document.latest_run;
  if (!run) {
    return {
      status: 'uploaded',
      label: 'Needs preparation',
      detail: 'Uploaded safely. Prepare it before publishing a searchable collection.',
      action: 'Prepare document',
      icon: FileClock,
    };
  }
  if (active(run)) {
    return {
      status: run.status,
      label: run.status === 'queued' ? 'Queued' : 'Preparing',
      detail:
        run.status === 'queued'
          ? `Version ${run.version} is waiting for a worker.`
          : `Version ${run.version} is ${run.progress}% complete.`,
      action: 'View progress',
      icon: LoaderCircle,
    };
  }
  if (run.status === 'succeeded') {
    return {
      status: run.status,
      label: 'Prepared',
      detail: `Version ${run.version} is ready with ${run.chunk_count.toLocaleString()} passages for the next collection publication.`,
      action: `Inspect version ${run.version}`,
      icon: FileCheck2,
    };
  }
  return {
    status: run.status,
    label: run.status === 'failed' ? 'Preparation failed' : 'Preparation cancelled',
    detail:
      run.status === 'failed'
        ? `Version ${run.version} failed. Open the document to review the error and retry.`
        : `Version ${run.version} was cancelled. You can prepare a new version.`,
    action: 'Review and retry',
    icon: CircleAlert,
  };
}

export function DocumentTable({
  groups,
  total,
  pageSize,
  offset,
  loading,
  error,
  selectedId,
  sort,
  deletingId,
  onRefresh,
  onPage,
  onSelect,
  onSort,
  onDelete,
}: {
  groups?: DocumentGroup[];
  total: number;
  pageSize: number;
  offset: number;
  loading: boolean;
  error: string;
  selectedId?: string;
  sort: 'newest' | 'oldest';
  deletingId?: string;
  onRefresh: () => void;
  onPage: (offset: number) => void;
  onSelect: (document: Document) => void;
  onSort: (sort: 'newest' | 'oldest') => void;
  onDelete: (document: Document, uploadCount: number) => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);

  function changePage(nextOffset: number) {
    onPage(nextOffset);
    requestAnimationFrame(() => heading.current?.focus());
  }

  return (
    <section className="document-library" aria-labelledby="documents-title">
      <div className="document-library-heading">
        <div>
          <h2 ref={heading} tabIndex={-1} id="documents-title">
            Your documents
          </h2>
          <p>Each source appears once, with its latest preparation state and next action.</p>
        </div>
        <div className="document-library-controls">
          <div className="document-sort-control">
            <Label htmlFor="document-sort">Sort by date and time</Label>
            <NativeSelect
              id="document-sort"
              size="sm"
              value={sort}
              onChange={(event) => onSort(event.target.value as 'newest' | 'oldest')}
            >
              <NativeSelectOption value="newest">Newest added</NativeSelectOption>
              <NativeSelectOption value="oldest">Oldest added</NativeSelectOption>
            </NativeSelect>
          </div>
          <Button variant="outline" onClick={onRefresh} disabled={loading}>
            <RotateCw />
            Refresh
          </Button>
        </div>
      </div>
      {error && (
        <div role="alert" className="inline-error document-library-error">
          <p>{error}</p>
          <Button variant="outline" size="sm" onClick={onRefresh}>
            Retry
          </Button>
        </div>
      )}
      {!groups && !error ? (
        <p role="status" className="document-loading">
          <LoaderCircle /> Loading documents…
        </p>
      ) : groups?.length === 0 ? (
        <div className="empty-state document-empty">
          <FileText size={30} />
          <h3>No documents yet</h3>
          <p>Add a PDF or TXT file, then prepare it for search.</p>
        </div>
      ) : (
        <ul className="document-list" aria-label="Documents">
          {groups?.map(({ document, uploadCount, createdAt }) => {
            const view = presentation(document);
            const Icon = view.icon;
            return (
              <li
                key={document.content_hash || document.id}
                data-selected={selectedId === document.id}
              >
                <div className="document-file-mark" aria-hidden="true">
                  <Icon className={active(document.latest_run) ? 'is-spinning' : ''} />
                </div>
                <div className="document-card-main">
                  <Button
                    variant="ghost"
                    className="document-name"
                    onClick={() => onSelect(document)}
                  >
                    {document.filename}
                  </Button>
                  <p className="document-file-meta">
                    {bytes(document.size_bytes)} · added{' '}
                    <time dateTime={createdAt}>{date(createdAt)}</time>
                    {uploadCount > 1 ? ` · ${uploadCount} identical uploads consolidated` : ''}
                  </p>
                  {document.latest_run?.error && (
                    <p className="document-inline-error">{document.latest_run.error}</p>
                  )}
                </div>
                <div className="document-readiness">
                  <StatusBadge status={view.status}>{view.label}</StatusBadge>
                  <p>{view.detail}</p>
                </div>
                <div className="document-row-actions">
                  <Button
                    variant={document.latest_run?.status === 'succeeded' ? 'outline' : 'default'}
                    className="document-next-action"
                    onClick={() => onSelect(document)}
                    aria-label={`${view.action}: ${document.filename}`}
                  >
                    {view.action} <ArrowRight />
                  </Button>
                  <Button
                    variant="outline"
                    className="document-delete-action"
                    disabled={deletingId === document.id}
                    onClick={() => onDelete(document, uploadCount)}
                    aria-label={`Delete document: ${document.filename}`}
                  >
                    {deletingId === document.id ? (
                      <LoaderCircle className="is-spinning" />
                    ) : (
                      <Trash2 />
                    )}
                    {deletingId === document.id ? 'Deleting…' : 'Delete'}
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {groups && (
        <Pagination
          offset={offset}
          total={total}
          pageSize={pageSize}
          onChange={changePage}
          busy={loading}
          label="Document pages"
        />
      )}
    </section>
  );
}
