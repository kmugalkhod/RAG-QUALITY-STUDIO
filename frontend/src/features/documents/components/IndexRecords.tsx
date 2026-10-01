import { useEffect, useState } from 'react';
import { Braces, Database, FileText, RotateCw } from 'lucide-react';

import { Pagination } from '../../../components/Pagination';
import { Button } from '../../../components/ui/button';
import { StatusBadge } from '../../../components/StatusBadge';
import { EmptyState } from '../../../components/states/EmptyState';
import { ErrorState } from '../../../components/states/ErrorState';
import { LoadingState } from '../../../components/states/LoadingState';
import { cn } from '../../../lib/utils';
import { LIST, LIST_ROW, META, SUMMARY, SectionHeading } from '../../../components/parts';
import * as api from '../indexApi';
import type { IndexRecordPage, IndexVersion } from '../model';

const message = (cause: unknown) =>
  cause instanceof Error ? cause.message : 'Could not load stored passages.';

function vectorPreview(values: number[]) {
  return values.map((value) => value.toFixed(4)).join(', ');
}

export function IndexRecords({ projectId, index }: { projectId: string; index: IndexVersion }) {
  const [page, setPage] = useState<IndexRecordPage>();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');

  useEffect(() => {
    let disposed = false;
    setPage(undefined);
    setError('');
    void Promise.resolve(api.listIndexRecords(projectId, index.id, offset))
      .then((value) => !disposed && value && setPage(value))
      .catch((cause) => !disposed && setError(message(cause)));
    return () => {
      disposed = true;
    };
  }, [index.id, offset, projectId, revision]);

  useEffect(() => setOffset(0), [index.id]);

  const retry = () => setRevision((value) => value + 1);
  return (
    <section className="flex flex-col gap-4" aria-labelledby="stored-passages-title">
      <SectionHeading
        id="stored-passages-title"
        title={
          <>
            <Database aria-hidden="true" /> Stored passages
          </>
        }
        description="Content available to retrieval in this immutable version. Vector values stay inside each passage’s technical details."
        action={
          <Button variant="outline" size="sm" onClick={retry} disabled={!page}>
            <RotateCw aria-hidden="true" /> Refresh
          </Button>
        }
      />
      {error ? (
        <ErrorState title="Stored passages couldn’t be loaded" message={error} onRetry={retry} />
      ) : !page ? (
        <LoadingState label="Loading stored passages…" />
      ) : page.total === 0 ? (
        <EmptyState title="No passages were stored for this collection version." />
      ) : (
        <ol className={LIST}>
          {page.items.map((record) => (
            <li
              key={`${record.run_id}-${record.ordinal}`}
              className={cn(LIST_ROW, 'flex flex-col gap-2 p-4')}
            >
              <div className="flex items-start gap-3">
                <FileText
                  aria-hidden="true"
                  className="mt-1 size-4 shrink-0 text-foreground-subtle"
                />
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <strong className="truncate text-sm font-semibold text-foreground">
                    {record.filename}
                  </strong>
                  <p className={META}>
                    Chunk {record.ordinal + 1} · Characters {record.start_char}–{record.end_char}
                    {record.page_number ? ` · PDF page ${record.page_number}` : ''}
                  </p>
                </div>
                <StatusBadge status={record.embedded ? 'succeeded' : 'failed'}>
                  {record.embedded ? `${record.dimensions}D vector` : 'Vector missing'}
                </StatusBadge>
              </div>
              <p className="text-sm whitespace-pre-wrap text-foreground wrap-anywhere">
                {record.text}
              </p>
              <details>
                <summary className={SUMMARY}>
                  <Braces aria-hidden="true" /> Inspect stored values and provenance
                </summary>
                <dl className="flex flex-col gap-2 pb-2">
                  {[
                    [
                      'Vector preview',
                      `[${vectorPreview(record.embedding_preview)}${record.dimensions > record.embedding_preview.length ? ', …' : ''}]`,
                    ],
                    ['L2 norm', record.embedding_norm?.toFixed(6) ?? 'Not available'],
                    ['Processing version', record.processing_version],
                    ['Processing run', record.run_id],
                    ['Document ID', record.document_id],
                    ...(record.source_url ? [['Source URL', record.source_url]] : []),
                    ...(record.section_path.length > 0
                      ? [['Section', record.section_path.join(' › ')]]
                      : []),
                  ].map(([term, value]) => (
                    <div key={term} className="flex flex-col gap-1 md:flex-row md:gap-4">
                      <dt className={cn(META, 'md:w-1/4 md:shrink-0')}>{term}</dt>
                      <dd className="font-mono text-xs text-foreground wrap-anywhere">{value}</dd>
                    </div>
                  ))}
                </dl>
              </details>
            </li>
          ))}
        </ol>
      )}
      {page && (
        <Pagination
          offset={offset}
          total={page.total}
          pageSize={page.limit}
          onChange={setOffset}
          label="Stored passage pages"
        />
      )}
    </section>
  );
}
