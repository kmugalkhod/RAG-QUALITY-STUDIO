import { useEffect, useState } from 'react';
import { Braces, Database, FileText, RotateCw } from 'lucide-react';

import { Pagination } from '../../../components/Pagination';
import { Button } from '../../../components/ui/button';
import { StatusBadge } from '../../../components/StatusBadge';
import * as api from '../indexApi';
import type { IndexRecordPage, IndexVersion } from '../model';

const message = (cause: unknown) =>
  cause instanceof Error ? cause.message : 'Could not load vector records.';

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

  return (
    <section className="vector-browser" aria-labelledby="vector-records-title">
      <div className="vector-browser-heading">
        <div>
          <h3 id="vector-records-title">
            <Database /> Vector records
          </h3>
          <p>
            Stored passages and embedding metadata from this immutable index. The first eight vector
            values are shown for verification.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setRevision((value) => value + 1)}
          disabled={!page}
        >
          <RotateCw /> Refresh
        </Button>
      </div>
      {error && (
        <div className="inline-error" role="alert">
          <p>{error}</p>
          <Button variant="outline" size="sm" onClick={() => setRevision((value) => value + 1)}>
            Retry
          </Button>
        </div>
      )}
      {!page && !error && <p role="status">Loading vector records…</p>}
      {page?.total === 0 && <p>No records were stored for this index.</p>}
      <ol className="vector-record-list">
        {page?.items.map((record) => (
          <li key={`${record.run_id}-${record.ordinal}`}>
            <div className="vector-record-main">
              <FileText />
              <div>
                <strong>{record.filename}</strong>
                <p>
                  Chunk {record.ordinal + 1} · Characters {record.start_char}–{record.end_char}
                  {record.page_number ? ` · PDF page ${record.page_number}` : ''}
                </p>
              </div>
              <StatusBadge status={record.embedded ? 'succeeded' : 'failed'}>
                {record.embedded ? `${record.dimensions}D vector` : 'Vector missing'}
              </StatusBadge>
            </div>
            <p className="vector-record-text">{record.text}</p>
            <details className="vector-record-technical">
              <summary>
                <Braces /> Inspect stored values and provenance
              </summary>
              <dl>
                <div>
                  <dt>Vector preview</dt>
                  <dd>
                    [{vectorPreview(record.embedding_preview)}
                    {record.dimensions > record.embedding_preview.length ? ', …' : ''}]
                  </dd>
                </div>
                <div>
                  <dt>L2 norm</dt>
                  <dd>{record.embedding_norm?.toFixed(6) ?? 'Not available'}</dd>
                </div>
                <div>
                  <dt>Processing version</dt>
                  <dd>{record.processing_version}</dd>
                </div>
                <div>
                  <dt>Processing run</dt>
                  <dd>{record.run_id}</dd>
                </div>
                <div>
                  <dt>Document ID</dt>
                  <dd>{record.document_id}</dd>
                </div>
                {record.source_url && (
                  <div>
                    <dt>Source URL</dt>
                    <dd>{record.source_url}</dd>
                  </div>
                )}
                {record.section_path.length > 0 && (
                  <div>
                    <dt>Section</dt>
                    <dd>{record.section_path.join(' › ')}</dd>
                  </div>
                )}
              </dl>
            </details>
          </li>
        ))}
      </ol>
      {page && (
        <Pagination
          offset={offset}
          total={page.total}
          pageSize={page.limit}
          onChange={setOffset}
          label="Vector record pages"
        />
      )}
    </section>
  );
}
