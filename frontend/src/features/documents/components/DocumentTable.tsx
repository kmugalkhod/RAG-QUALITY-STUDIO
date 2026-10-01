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
import { EmptyState } from '../../../components/states/EmptyState';
import { ErrorState } from '../../../components/states/ErrorState';
import { LoadingState } from '../../../components/states/LoadingState';
import { cn } from '../../../lib/utils';
import { InlineError, LIST, LIST_ROW, META, SectionHeading } from '../../../components/parts';
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
  onAdd,
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
  onAdd: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);

  function changePage(nextOffset: number) {
    onPage(nextOffset);
    requestAnimationFrame(() => heading.current?.focus());
  }

  return (
    <section className="flex flex-col gap-4" aria-labelledby="documents-title">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <SectionHeading
          id="documents-title"
          level="h2"
          headingRef={heading}
          title="Your documents"
          description="Each source appears once, with its latest preparation state and next action."
        />
        <div className="flex items-end gap-2">
          <div className="flex min-w-0 flex-1 flex-col md:flex-none">
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
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
            <RotateCw aria-hidden="true" />
            Refresh
          </Button>
        </div>
      </div>
      {error && groups && <InlineError onRetry={onRefresh}>{error}</InlineError>}
      {!groups ? (
        error ? (
          <ErrorState title="Documents couldn’t be loaded" message={error} onRetry={onRefresh} />
        ) : (
          <LoadingState label="Loading documents…" />
        )
      ) : groups.length === 0 ? (
        <EmptyState
          icon={<FileText />}
          title="No documents yet"
          headingLevel="h3"
          description="Add a supported document. You can inspect its extracted passages before publishing a searchable collection."
          action={
            <Button variant="outline" onClick={onAdd}>
              Add your first document
            </Button>
          }
        />
      ) : (
        <ul className={LIST} aria-label="Documents">
          {groups.map(({ document, uploadCount, createdAt }) => {
            const view = presentation(document);
            const Icon = view.icon;
            const running = active(document.latest_run);
            const isSelected = selectedId === document.id;
            return (
              <li
                key={document.content_hash || document.id}
                data-selected={isSelected}
                className={cn(
                  LIST_ROW,
                  'flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:gap-4',
                  isSelected && 'bg-surface-hover',
                )}
              >
                <div className="flex min-w-0 flex-1 items-start gap-3">
                  <span
                    aria-hidden="true"
                    className="flex size-control-md shrink-0 items-center justify-center rounded-control border border-border text-foreground-subtle"
                  >
                    <Icon className={cn('size-4', running && 'motion-safe:animate-spin')} />
                  </span>
                  <div className="flex min-w-0 flex-1 flex-col items-start">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="-ml-2 max-w-full justify-start font-semibold"
                      onClick={() => onSelect(document)}
                    >
                      <span className="truncate">{document.filename}</span>
                    </Button>
                    <p className={META}>
                      {bytes(document.size_bytes)} · added{' '}
                      <time dateTime={createdAt}>{date(createdAt)}</time>
                      {uploadCount > 1 ? ` · ${uploadCount} identical uploads consolidated` : ''}
                    </p>
                    {document.latest_run?.error && (
                      <p className="text-xs text-danger wrap-anywhere">
                        {document.latest_run.error}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex min-w-0 flex-col items-start gap-1 md:w-1/4 md:shrink-0">
                  <StatusBadge status={view.status}>{view.label}</StatusBadge>
                  <p className={META}>{view.detail}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2 max-md:*:flex-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onSelect(document)}
                    aria-label={`${view.action}: ${document.filename}`}
                  >
                    {view.action} <ArrowRight aria-hidden="true" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={deletingId === document.id}
                    onClick={() => onDelete(document, uploadCount)}
                    aria-label={`Delete document: ${document.filename}`}
                  >
                    <Trash2 aria-hidden="true" />
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
