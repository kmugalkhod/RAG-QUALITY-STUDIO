import { ArrowRight, FileText, Workflow } from 'lucide-react';
import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import type { ProjectSummaryData } from '../data';

export function ProjectOverview({
  projectId,
  data,
}: {
  projectId: string;
  data: ProjectSummaryData;
}) {
  const ready = data.indexes.filter((index) => index.status === 'succeeded');
  const processed = data.documents.filter(
    (document) => document.latest_run?.status === 'succeeded',
  );
  const processing = data.documents.filter((document) =>
    ['queued', 'running'].includes(document.latest_run?.status || ''),
  );
  const failed = data.documents.filter((document) => document.latest_run?.status === 'failed');
  const indexing = data.indexes.filter((index) => ['queued', 'running'].includes(index.status));
  const next = !data.documents.length
    ? [
        'Add your first source',
        'Upload a PDF or TXT document to begin.',
        'knowledge-base',
        'Upload documents',
      ]
    : !processed.length
      ? [
          'Prepare your documents',
          'Process uploaded text into inspectable chunks.',
          'knowledge-base',
          'Process documents',
        ]
      : !ready.length
        ? [
            'Make your sources searchable',
            indexing.length
              ? 'Your documents are being prepared.'
              : 'Prepare a searchable document set.',
            'knowledge-base',
            'View document sets',
          ]
        : !data.pipelines.length
          ? [
              'Configure your first pipeline',
              'Choose how answers should be retrieved and written.',
              'pipelines/new',
              'Create pipeline',
            ]
          : [
              'Ask your sources a question',
              'Run a saved pipeline and inspect its evidence.',
              'playground',
              'Open Playground',
            ];

  return (
    <>
      <div className="page-heading mb-8 flex items-start justify-between gap-6">
        <div>
          <h1>Overview</h1>
          <p>{data.project.description || 'Sources and saved configurations for this project.'}</p>
        </div>
        <Button asChild>
          <a href={`#/projects/${projectId}/${next[2]}`}>
            {next[3]}
            <ArrowRight />
          </a>
        </Button>
      </div>
      <div className="overview-layout grid grid-cols-[minmax(0,1fr)_250px] gap-10">
        <div className="overview-content">
          <section className="project-readiness border-b border-border py-7">
            <h2>{next[0]}</h2>
            <p>{next[1]}</p>
            <div className="readiness-line flex flex-wrap gap-5 text-xs text-muted-foreground">
              <span>{processed.length} processed documents</span>
              <span>{ready.length} prepared sets</span>
              <span>{data.pipelines.length} saved pipelines</span>
            </div>
          </section>
          <section className="overview-section mt-6">
            <div className="section-heading flex items-center justify-between gap-4 py-3">
              <h2>
                Recent documents <span className="count">{data.documents.length}</span>
              </h2>
              <a className="text-link" href={`#/projects/${projectId}/knowledge-base`}>
                View all
              </a>
            </div>
            {!data.documents.length ? (
              <p className="inline-empty">Add a source to build your knowledge base.</p>
            ) : (
              <ul className="compact-list m-0 list-none p-0">
                {data.documents.slice(0, 5).map((document) => {
                  const status = document.latest_run?.status || 'uploaded';
                  return (
                    <li key={document.id}>
                      <FileText />
                      <a href={`#/projects/${projectId}/knowledge-base?document=${document.id}`}>
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
          </section>
          <section className="overview-section mt-6">
            <div className="section-heading flex items-center justify-between gap-4 py-3">
              <h2>
                Saved pipelines <span className="count">{data.pipelines.length}</span>
              </h2>
              <a className="text-link" href={`#/projects/${projectId}/pipelines`}>
                View all
              </a>
            </div>
            {!data.pipelines.length ? (
              <p className="inline-empty">Create a pipeline after a document set is ready.</p>
            ) : (
              <ul className="compact-list m-0 list-none p-0">
                {data.pipelines.slice(0, 5).map((pipeline) => (
                  <li key={pipeline.id}>
                    <Workflow />
                    <a href={`#/projects/${projectId}/pipelines/${pipeline.id}`}>{pipeline.name}</a>
                    <ArrowRight />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
        <aside className="project-properties border-l border-border p-6">
          <h2>Project details</h2>
          <dl>
            <dt>Created</dt>
            <dd>{new Date(data.project.created_at).toLocaleDateString()}</dd>
            <dt>Documents</dt>
            <dd>{data.documents.length} uploaded</dd>
            <dt>Processing</dt>
            <dd>
              {processing.length} active · {failed.length} failed
            </dd>
            <dt>Indexing</dt>
            <dd>
              {indexing.length} active ·{' '}
              {data.indexes.filter((index) => index.status === 'failed').length} failed
            </dd>
            <dt>Project ID</dt>
            <dd className="technical-value">{projectId}</dd>
          </dl>
        </aside>
      </div>
    </>
  );
}
