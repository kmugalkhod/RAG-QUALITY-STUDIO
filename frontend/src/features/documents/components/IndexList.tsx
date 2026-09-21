import { Database, LoaderCircle, RotateCw } from 'lucide-react';

import { Pagination } from '../../../components/Pagination';
import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import { Progress } from '../../../components/ui/progress';
import type { IndexPage, IndexVersion } from '../model';

const isActive = (index: IndexVersion) => ['queued', 'running'].includes(index.status);

export function IndexList({
  page,
  offset,
  selectedId,
  busy,
  loadError,
  onRefresh,
  onPage,
  onCancel,
  onSelect,
}: {
  page?: IndexPage;
  offset: number;
  selectedId?: string;
  busy: boolean;
  loadError: string;
  onRefresh: () => void;
  onPage: (offset: number) => void;
  onCancel: (index: IndexVersion) => void;
  onSelect: (index: IndexVersion) => void;
}) {
  const groups = Array.from(
    (page?.items ?? []).reduce((grouped, index) => {
      const group = grouped.get(index.knowledge_set_id) ?? [];
      group.push(index);
      grouped.set(index.knowledge_set_id, group);
      return grouped;
    }, new Map<string, IndexVersion[]>()),
  );

  return (
    <section className="index-catalog" aria-labelledby="knowledge-sets-title">
      <div className="index-catalog-heading">
        <div>
          <h2 id="knowledge-sets-title">Knowledge sets</h2>
          <p>Choose an immutable version to inspect or test.</p>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onRefresh}
          aria-label="Refresh document sets"
        >
          <RotateCw />
        </Button>
      </div>
      {loadError && (
        <p role="alert" className="error-message">
          {loadError}
        </p>
      )}
      {!page && !loadError && (
        <p role="status" className="index-loading">
          <LoaderCircle /> Loading knowledge sets…
        </p>
      )}
      {page?.total === 0 && (
        <div className="index-empty">
          <Database />
          <h3>No knowledge sets yet</h3>
          <p>Process a document or run an ingestion pipeline, then prepare an index.</p>
        </div>
      )}
      <div className="index-groups">
        {groups.map(([knowledgeSetId, versions]) => (
          <section key={knowledgeSetId} aria-labelledby={`knowledge-set-${knowledgeSetId}`}>
            <div className="index-group-heading">
              <h3 id={`knowledge-set-${knowledgeSetId}`}>{versions[0].knowledge_set_name}</h3>
              <span>
                {versions.length} version{versions.length === 1 ? '' : 's'}
              </span>
            </div>
            <ul>
              {versions.map((index) => (
                <li key={index.id} data-state={selectedId === index.id ? 'selected' : undefined}>
                  <button
                    type="button"
                    className="index-version-select"
                    disabled={index.status !== 'succeeded'}
                    aria-pressed={selectedId === index.id}
                    aria-label={
                      index.status === 'succeeded' ? `Use document set ${index.version}` : undefined
                    }
                    onClick={() => onSelect(index)}
                  >
                    <span className="index-version-title">
                      <strong>Version {index.version}</strong>
                      <StatusBadge status={index.status}>
                        {index.status === 'succeeded'
                          ? 'Ready'
                          : isActive(index)
                            ? 'Preparing'
                            : index.status}
                      </StatusBadge>
                      {index.is_current && <StatusBadge status="configured">Current</StatusBadge>}
                    </span>
                    <span className="index-version-meta">
                      {index.embedded_count.toLocaleString()} / {index.chunk_count.toLocaleString()}{' '}
                      passages prepared from {index.processing_run_count} processing{' '}
                      {index.processing_run_count === 1 ? 'run' : 'runs'}
                    </span>
                    <time dateTime={index.created_at}>
                      {new Intl.DateTimeFormat(undefined, {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric',
                      }).format(new Date(index.created_at))}
                    </time>
                  </button>
                  {isActive(index) && (
                    <div className="index-progress">
                      <Progress
                        value={
                          index.chunk_count ? (index.embedded_count / index.chunk_count) * 100 : 0
                        }
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        onClick={() => onCancel(index)}
                        aria-label={`Cancel document set ${index.version}`}
                      >
                        Cancel
                      </Button>
                    </div>
                  )}
                  {index.error && <p className="error-message">{index.error}</p>}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      {page && (
        <Pagination
          offset={offset}
          total={page.total}
          pageSize={page.limit}
          onChange={onPage}
          label="Knowledge set pages"
        />
      )}
    </section>
  );
}
