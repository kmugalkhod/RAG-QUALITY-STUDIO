import type { Page } from '../../../lib/pagination';
import { useEffect, useRef, useState } from 'react';
import { Button } from '../../../components/ui/button';
import * as api from '../api';
import { type Chunk, type Run } from '../model';
import { Pagination } from '../../../components/Pagination';
import { message } from '../documentPresentation';
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
    <section className="chunk-inspector mt-6" aria-labelledby="chunks-title">
      <h3 id="chunks-title" tabIndex={-1} ref={title}>
        Chunks · Version {run.version}
      </h3>
      <p>
        {run.chunk_size} characters · {run.overlap} overlap · {run.chunk_count} chunks
      </p>
      {loading && page && <p role="status">Loading chunks…</p>}
      {error ? (
        <div>
          <p role="alert" className="error-message text-xs mt-4 text-destructive">
            {error}
          </p>
          <Button variant="outline" onClick={() => setRevision((n) => n + 1)}>
            Retry loading chunks
          </Button>
        </div>
      ) : !page ? (
        <p role="status">Loading chunks…</p>
      ) : (
        <ol
          className="chunk-list document-chunks max-h-90 overflow-auto overscroll-contain pr-3"
          tabIndex={0}
          aria-label="Document chunks"
          start={offset + 1}
        >
          {page.items.map((chunk) => (
            <li key={chunk.ordinal}>
              <p className="chunk-provenance text-muted-foreground text-[10px]">
                Chunk {chunk.ordinal + 1} ·{' '}
                {chunk.page_number ? `PDF page ${chunk.page_number}` : 'TXT source'} · characters{' '}
                {chunk.start_char}–{chunk.end_char} (end exclusive)
              </p>
              <pre>{chunk.text}</pre>
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
