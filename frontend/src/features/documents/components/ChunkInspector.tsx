import type { Page } from '../../../lib/pagination';
import { useEffect, useRef, useState } from 'react';
import * as api from '../api';
import { type Chunk, type Run } from '../model';
import { Pagination } from '../../../components/Pagination';
import { message } from '../documentPresentation';
import { LoadingState } from '../../../components/states/LoadingState';
import { cn } from '../../../lib/utils';
import { InlineError, LIST, LIST_ROW, META } from '../../../components/parts';
export function ChunkInspector({
  projectId,
  documentId,
  run,
}: {
  projectId: string;
  documentId: string;
  run: Run;
}) {
  const [page, setPage] = useState<Page<Chunk>>();
  const [loading, setLoading] = useState(true);
  const focusPage = useRef(false);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    title.current?.focus();
  }, []);
  useEffect(() => {
    let disposed = false;
    setLoading(true);
    setError('');
    void api
      .listDocumentChunks(projectId, documentId, run.id, offset)
      .then((result) => {
        if (!disposed) {
          setPage(result);
          setLoading(false);
          if (focusPage.current) {
            title.current?.focus();
            focusPage.current = false;
          }
        }
      })
      .catch((err) => {
        if (!disposed) {
          setError(message(err));
          setLoading(false);
        }
      });
    return () => {
      disposed = true;
    };
  }, [projectId, documentId, run.id, offset, revision]);
  return (
    <section
      className="flex flex-col gap-3 border-t border-border pt-4"
      aria-labelledby="chunks-title"
    >
      <div className="flex flex-col gap-1">
        <h3
          id="chunks-title"
          tabIndex={-1}
          ref={title}
          className="text-sm font-semibold text-foreground outline-none"
        >
          Chunks · Version {run.version}
        </h3>
        <p className={META}>
          {run.chunk_size} characters · {run.overlap} overlap · {run.chunk_count} chunks
        </p>
      </div>
      {loading && page && (
        <p className={META} role="status">
          Loading chunks…
        </p>
      )}
      {error ? (
        <InlineError onRetry={() => setRevision((n) => n + 1)} retryLabel="Retry loading chunks">
          {error}
        </InlineError>
      ) : !page ? (
        <LoadingState label="Loading chunks…" rows={2} />
      ) : (
        <ol
          className={cn(
            LIST,
            'max-h-panel overflow-auto overscroll-contain outline-none focus-visible:outline-2 focus-visible:outline-accent',
          )}
          tabIndex={0}
          aria-label="Document chunks"
          start={offset + 1}
        >
          {page.items.map((chunk) => (
            <li key={chunk.ordinal} className={cn(LIST_ROW, 'flex flex-col gap-2 p-3')}>
              <p className={META}>
                Chunk {chunk.ordinal + 1} ·{' '}
                {chunk.page_number ? `PDF page ${chunk.page_number}` : 'Source file'} · characters{' '}
                {chunk.start_char}–{chunk.end_char} (end exclusive)
              </p>
              <pre className="font-mono text-xs whitespace-pre-wrap text-foreground wrap-anywhere">
                {chunk.text}
              </pre>
            </li>
          ))}
        </ol>
      )}
      {page && (
        <Pagination
          offset={offset}
          total={page.total}
          onChange={(value) => {
            focusPage.current = true;
            setOffset(value);
          }}
          busy={loading}
          label="Chunk pages"
        />
      )}
    </section>
  );
}
