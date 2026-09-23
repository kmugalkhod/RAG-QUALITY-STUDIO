import { ArrowRight, Database, LoaderCircle, RotateCw } from 'lucide-react';

import { Pagination } from '../../../components/Pagination';
import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import type { IndexVersion } from '../model';

export type CollectionGroup = {
  id: string;
  name: string;
  versions: IndexVersion[];
  current?: IndexVersion;
  representative: IndexVersion;
};

export function collectionGroups(indexes?: IndexVersion[]): CollectionGroup[] {
  return Array.from(
    (indexes ?? []).reduce((grouped, index) => {
      const group = grouped.get(index.knowledge_set_id) ?? [];
      group.push(index);
      grouped.set(index.knowledge_set_id, group);
      return grouped;
    }, new Map<string, IndexVersion[]>()),
  ).map(([id, versions]) => {
    const ordered = [...versions].sort((a, b) => b.version - a.version);
    const current = ordered.find((version) => version.is_current);
    return {
      id,
      name: ordered[0].knowledge_set_name,
      versions: ordered,
      current,
      representative: current ?? ordered[0],
    };
  });
}

export function IndexList({
  groups,
  total,
  pageSize,
  offset,
  selected,
  loadError,
  onRefresh,
  onPage,
  onSelect,
}: {
  groups?: CollectionGroup[];
  total: number;
  pageSize: number;
  offset: number;
  selected?: IndexVersion;
  loadError: string;
  onRefresh: () => void;
  onPage: (offset: number) => void;
  onSelect: (index: IndexVersion) => void;
}) {
  return (
    <section className="index-catalog" aria-labelledby="collections-title">
      <div className="index-catalog-heading">
        <div>
          <h2 id="collections-title">Collections</h2>
          <p>Choose the searchable knowledge your pipelines can use.</p>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onRefresh} aria-label="Refresh collections">
          <RotateCw />
        </Button>
      </div>
      {loadError && (
        <div className="inline-error index-catalog-error" role="alert">
          <span>{loadError}</span>
          <Button variant="outline" size="sm" onClick={onRefresh}>
            Retry
          </Button>
        </div>
      )}
      {!groups && !loadError && (
        <p role="status" className="index-loading">
          <LoaderCircle /> Loading collections…
        </p>
      )}
      {groups?.length === 0 && (
        <div className="index-empty">
          <Database />
          <h3>No searchable collections yet</h3>
          <p>Prepare a document first, then publish it as a fixed collection version.</p>
        </div>
      )}
      <ul className="collection-list">
        {groups?.map((group) => {
          const active = selected?.knowledge_set_id === group.id;
          const version = active ? selected : group.representative;
          return (
            <li key={group.id} data-state={active ? 'selected' : undefined}>
              <button
                type="button"
                className="collection-select"
                aria-pressed={active}
                aria-label={`Open ${group.name} collection`}
                onClick={() => onSelect(group.representative)}
              >
                <span className="collection-title-row">
                  <strong>{group.name}</strong>
                  <ArrowRight />
                </span>
                <span className="collection-state-row">
                  <StatusBadge status={version.status}>
                    {version.status === 'succeeded'
                      ? 'Ready'
                      : ['queued', 'running'].includes(version.status)
                        ? 'Publishing'
                        : version.status}
                  </StatusBadge>
                  {group.current && <span>Current · version {group.current.version}</span>}
                  {!group.current && <span>No current ready version</span>}
                </span>
                <span className="collection-summary">
                  {version.embedded_count.toLocaleString()} stored passages ·{' '}
                  {group.versions.length} version{group.versions.length === 1 ? '' : 's'}
                </span>
                <time dateTime={version.created_at}>
                  Last activity{' '}
                  {new Intl.DateTimeFormat(undefined, {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  }).format(new Date(version.created_at))}
                </time>
              </button>
            </li>
          );
        })}
      </ul>
      {groups && (
        <Pagination
          offset={offset}
          total={total}
          pageSize={pageSize}
          onChange={onPage}
          label="Collection pages"
        />
      )}
    </section>
  );
}
