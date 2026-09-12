import { useRef } from 'react';
import { FileText, PanelRight, RotateCw } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../../components/ui/table';
import { StatusBadge } from '../../../components/StatusBadge';
import { Pagination } from '../../../components/Pagination';
import type { Page } from '../../../lib/pagination';
import { active, bytes } from '../documentPresentation';
import type { Document } from '../model';

export function DocumentTable({
  page,
  offset,
  loading,
  error,
  selectedId,
  onRefresh,
  onPage,
  onSelect,
}: {
  page?: Page<Document>;
  offset: number;
  loading: boolean;
  error: string;
  selectedId?: string;
  onRefresh: () => void;
  onPage: (offset: number) => void;
  onSelect: (document: Document) => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  function changePage(nextOffset: number) {
    onPage(nextOffset);
    requestAnimationFrame(() => heading.current?.focus());
  }

  return (
    <section className="project-section m-0" aria-labelledby="documents-title">
      <div className="section-heading flex items-center justify-between gap-4 px-7 py-4">
        <h2 ref={heading} tabIndex={-1} id="documents-title">
          All documents
        </h2>
        <Button variant="outline" onClick={onRefresh} disabled={loading}>
          <RotateCw />
          Refresh
        </Button>
      </div>
      {error && (
        <p role="alert" className="error-message mx-7">
          {error}
        </p>
      )}
      {!page && !error ? (
        <p role="status" className="loading-state px-7 py-6 text-muted-foreground">
          Loading documents…
        </p>
      ) : page?.items.length === 0 ? (
        <div className="empty-state py-16 text-center text-muted-foreground">
          <FileText size={32} />
          <h3>No documents yet</h3>
          <p>Upload a source file to begin inspecting its text.</p>
        </div>
      ) : (
        <div className="source-table-wrap">
          <Table className="source-table table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Added</TableHead>
                <TableHead>
                  <span className="sr-only">Details</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page?.items.map((document) => {
                const status = document.latest_run?.status ?? 'uploaded';
                const label =
                  status === 'succeeded'
                    ? 'Processed'
                    : active(document.latest_run)
                      ? 'Processing'
                      : status;
                return (
                  <TableRow
                    key={document.id}
                    data-state={selectedId === document.id ? 'selected' : undefined}
                  >
                    <TableCell>
                      <div className="source-name flex min-w-0 items-center gap-3">
                        <FileText />
                        <Button
                          variant="ghost"
                          className="document-name"
                          onClick={() => onSelect(document)}
                        >
                          {document.filename}
                        </Button>
                      </div>
                      {document.latest_run?.error && (
                        <p className="error-message">{document.latest_run.error}</p>
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={status}>{label}</StatusBadge>
                      {active(document.latest_run) && (
                        <small className="ml-2">{document.latest_run?.progress}%</small>
                      )}
                    </TableCell>
                    <TableCell>{bytes(document.size_bytes)}</TableCell>
                    <TableCell>
                      <time dateTime={document.created_at}>
                        {new Intl.DateTimeFormat(undefined, {
                          month: 'short',
                          day: 'numeric',
                        }).format(new Date(document.created_at))}
                      </time>
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => onSelect(document)}
                        aria-label={`Manage ${document.filename}`}
                      >
                        <PanelRight />
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <p className="table-note mx-7 my-4 text-xs text-muted-foreground">
            After processing, prepare a document set to start asking questions.
          </p>
        </div>
      )}
      {page && (
        <Pagination
          offset={offset}
          total={page.total}
          onChange={changePage}
          busy={loading}
          label="Document pages"
        />
      )}
    </section>
  );
}
