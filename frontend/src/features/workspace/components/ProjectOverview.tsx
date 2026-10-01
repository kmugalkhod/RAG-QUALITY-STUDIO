import type { ReactNode } from 'react';
import { ChevronRight, FileText, Workflow } from 'lucide-react';
import { PageHeader } from '../../../components/PageHeader';
import { EmptyState } from '../../../components/states/EmptyState';
import { StatusBadge } from '../../../components/StatusBadge';
import type { ProjectSummaryData } from '../data';
import { StageStrip } from './StageStrip';

function ListSection({
  id,
  title,
  count,
  viewAll,
  children,
}: {
  id: string;
  title: string;
  count: number;
  viewAll: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-2">
      <div className="flex h-control-lg items-center justify-between gap-4">
        <h2 id={id} className="flex items-center gap-2 text-base font-semibold text-foreground">
          {title}
          <span className="text-sm font-normal text-foreground-muted tabular-nums">{count}</span>
        </h2>
        <a
          className="flex h-row items-center rounded-control px-2 text-sm text-accent outline-none hover:underline focus-visible:outline-2 focus-visible:outline-accent"
          href={viewAll}
        >
          View all
        </a>
      </div>
      {children}
    </section>
  );
}

const ROW =
  'flex h-row items-center gap-3 border-b border-border px-4 text-sm last:border-b-0 hover:bg-surface-hover';

export function ProjectOverview({
  projectId,
  data,
}: {
  projectId: string;
  data: ProjectSummaryData;
}) {
  const processing = data.documents.filter((document) =>
    ['queued', 'running'].includes(document.latest_run?.status || ''),
  );
  const failed = data.documents.filter((document) => document.latest_run?.status === 'failed');
  const indexing = data.indexes.filter((index) => ['queued', 'running'].includes(index.status));
  const failedIndexes = data.indexes.filter((index) => index.status === 'failed');
  const details: [string, ReactNode][] = [
    ['Created', new Date(data.project.created_at).toLocaleDateString()],
    ['Documents', `${data.documents.length} uploaded`],
    ['Processing', `${processing.length} active · ${failed.length} failed`],
    ['Indexing', `${indexing.length} active · ${failedIndexes.length} failed`],
    [
      'Project ID',
      <span key="id" className="font-mono text-xs break-all">
        {projectId}
      </span>,
    ],
  ];

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Overview"
        meta={
          data.project.description ||
          'Prepare knowledge, ask questions and compare results for this project.'
        }
      />
      <StageStrip projectId={projectId} />
      <div className="flex flex-col gap-8 desktop:flex-row desktop:items-start">
        <div className="flex min-w-0 flex-1 flex-col gap-8">
          <ListSection
            id="recent-documents"
            title="Recent documents"
            count={data.documents.length}
            viewAll={`#/projects/${projectId}/knowledge-base`}
          >
            {!data.documents.length ? (
              <EmptyState
                icon={<FileText />}
                title="No documents yet"
                description="Add a source to build your knowledge base."
              />
            ) : (
              <ul className="overflow-hidden rounded-card border border-border bg-surface">
                {data.documents.slice(0, 5).map((document) => {
                  const status = document.latest_run?.status || 'uploaded';
                  return (
                    <li key={document.id} className={ROW}>
                      <FileText
                        aria-hidden="true"
                        className="size-4 shrink-0 text-foreground-subtle"
                      />
                      <a
                        className="min-w-0 flex-1 truncate text-foreground outline-none hover:underline focus-visible:outline-2 focus-visible:outline-accent"
                        href={`#/projects/${projectId}/knowledge-base?document=${document.id}`}
                      >
                        {document.filename}
                      </a>
                      <StatusBadge status={status}>
                        {status === 'succeeded'
                          ? 'Processed'
                          : ['running', 'queued'].includes(status)
                            ? 'Processing'
                            : status}
                      </StatusBadge>
                    </li>
                  );
                })}
              </ul>
            )}
          </ListSection>
          <ListSection
            id="saved-pipelines"
            title="Saved pipelines"
            count={data.pipelines.length}
            viewAll={`#/projects/${projectId}/pipelines`}
          >
            {!data.pipelines.length ? (
              <EmptyState
                icon={<Workflow />}
                title="No pipelines yet"
                description="Create a pipeline after a document set is ready."
              />
            ) : (
              <ul className="overflow-hidden rounded-card border border-border bg-surface">
                {data.pipelines.slice(0, 5).map((pipeline) => (
                  <li key={pipeline.id} className={ROW}>
                    <Workflow
                      aria-hidden="true"
                      className="size-4 shrink-0 text-foreground-subtle"
                    />
                    <a
                      className="min-w-0 flex-1 truncate text-foreground outline-none hover:underline focus-visible:outline-2 focus-visible:outline-accent"
                      href={`#/projects/${projectId}/pipelines/${pipeline.id}`}
                    >
                      {pipeline.name}
                    </a>
                    <ChevronRight aria-hidden="true" className="size-4 text-foreground-subtle" />
                  </li>
                ))}
              </ul>
            )}
          </ListSection>
        </div>
        <aside
          aria-labelledby="project-details"
          className="flex flex-col gap-4 rounded-card border border-border bg-surface p-6 desktop:w-panel desktop:shrink-0"
        >
          <h2 id="project-details" className="text-base font-semibold text-foreground">
            Project details
          </h2>
          <dl className="flex flex-col gap-3 text-sm">
            {details.map(([term, value]) => (
              <div key={term} className="flex flex-col gap-1">
                <dt className="text-xs text-foreground-muted">{term}</dt>
                <dd className="text-foreground tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
        </aside>
      </div>
    </div>
  );
}
