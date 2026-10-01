import { ArrowRight, Database, RotateCw } from 'lucide-react';

import { Pagination } from '../../../components/Pagination';
import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import { EmptyState } from '../../../components/states/EmptyState';
import { ErrorState } from '../../../components/states/ErrorState';
import { LoadingState } from '../../../components/states/LoadingState';
import {
  InlineError,
  LIST,
  LIST_ROW,
  META,
  SELECT_ROW,
  SectionHeading,
} from '../../../components/parts';
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
    <section className="flex min-w-0 flex-col gap-4" aria-labelledby="collections-title">
      <SectionHeading
        id="collections-title"
        level="h2"
        title="Collections"
        description="Choose the searchable knowledge your pipelines can use."
        action={
          <Button
            variant="ghost"
            size="sm"
            icon
            onClick={onRefresh}
            aria-label="Refresh collections"
          >
            <RotateCw aria-hidden="true" />
          </Button>
        }
      />
      {loadError && groups && <InlineError onRetry={onRefresh}>{loadError}</InlineError>}
      {!groups ? (
        loadError ? (
          <ErrorState
            title="Collections couldn’t be loaded"
            message={loadError}
            onRetry={onRefresh}
          />
        ) : (
          <LoadingState label="Loading collections…" />
        )
      ) : groups.length === 0 ? (
        <EmptyState
          icon={<Database />}
          title="No searchable collections yet"
          headingLevel="h3"
          description="Prepare a document first, then publish it as a fixed collection version."
        />
      ) : (
        <ul className={LIST}>
          {groups.map((group) => {
            const active = selected?.knowledge_set_id === group.id;
            const version = active ? selected : group.representative;
            return (
              <li key={group.id} data-state={active ? 'selected' : undefined} className={LIST_ROW}>
                <Button
                  variant="ghost"
                  className={SELECT_ROW}
                  aria-pressed={active}
                  aria-label={`Open ${group.name} collection`}
                  onClick={() => onSelect(group.representative)}
                >
                  <span className="flex items-center justify-between gap-2">
                    <strong className="truncate font-semibold">{group.name}</strong>
                    <ArrowRight aria-hidden="true" className="text-foreground-subtle" />
                  </span>
                  <span className="flex flex-wrap items-center gap-2 text-xs text-foreground-muted">
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
                  <span className={META}>
                    {version.embedded_count.toLocaleString()} stored passages ·{' '}
                    {group.versions.length} version{group.versions.length === 1 ? '' : 's'}
                  </span>
                  <time dateTime={version.created_at} className={META}>
                    Last activity{' '}
                    {new Intl.DateTimeFormat(undefined, {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                    }).format(new Date(version.created_at))}
                  </time>
                </Button>
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
          onChange={onPage}
          label="Collection pages"
        />
      )}
    </section>
  );
}
