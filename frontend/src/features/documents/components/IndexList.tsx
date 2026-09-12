import { Button } from '../../../components/ui/button';
import { StatusBadge } from '../../../components/StatusBadge';
import { Pagination } from '../../../components/Pagination';
import { Progress } from '../../../components/ui/progress';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '../../../components/ui/accordion';
import type { EmbeddingSettings, IndexPage, IndexVersion } from '../model';

const isActive = (index: IndexVersion) => ['queued', 'running'].includes(index.status);

export function IndexList({
  page,
  settings,
  offset,
  selectedId,
  busy,
  searching,
  loadError,
  error,
  notice,
  onCreate,
  onRefresh,
  onPage,
  onCancel,
  onSelect,
}: {
  page?: IndexPage;
  settings?: EmbeddingSettings;
  offset: number;
  selectedId?: string;
  busy: boolean;
  searching: boolean;
  loadError: string;
  error: string;
  notice: string;
  onCreate: () => void;
  onRefresh: () => void;
  onPage: (offset: number) => void;
  onCancel: (index: IndexVersion) => void;
  onSelect: (index: IndexVersion) => void;
}) {
  const hasActive = page?.items.some(isActive) ?? false;
  return (
    <>
      <div className="section-heading flex items-start justify-between gap-5 px-7 py-4">
        <div>
          <h2 id="index-title">Prepare documents for questions</h2>
          <p className="field-hint">Create a versioned, searchable copy of processed documents.</p>
        </div>
        <Button onClick={onCreate} disabled={busy || hasActive || !settings?.configured}>
          Prepare document set
        </Button>
      </div>
      {settings?.config && (
        <Accordion type="single" collapsible className="source-metadata mx-7">
          <AccordionItem value="search-model">
            <AccordionTrigger>Search model details</AccordionTrigger>
            <AccordionContent>
              {settings.config.provider} · {settings.config.model} · {settings.config.dimensions}{' '}
              dimensions
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      )}
      {settings && !settings.configured && <p className="error-message mx-7">{settings.error}</p>}
      {(loadError || error) && (
        <p role="alert" className="error-message mx-7">
          {loadError || error}
        </p>
      )}
      {notice && (
        <p role="status" className="success-message mx-7">
          {notice}
        </p>
      )}
      <div className="section-heading flex items-center justify-between gap-5 px-7 py-4">
        <h3 tabIndex={-1}>Document sets</h3>
        <Button variant="outline" onClick={onRefresh}>
          Refresh document sets
        </Button>
      </div>
      {!page && !loadError && (
        <p role="status" className="mx-7">
          Loading document sets…
        </p>
      )}
      {page?.total === 0 && (
        <p className="mx-7">No document sets yet. Process a document, then prepare a set.</p>
      )}
      <ul className="run-list">
        {page?.items.map((index) => (
          <li key={index.id}>
            <div className="document-summary">
              <h3>
                Document set · Version {index.version}{' '}
                <StatusBadge status={index.status}>
                  {index.status === 'succeeded'
                    ? 'Ready'
                    : isActive(index)
                      ? 'Preparing'
                      : index.status}
                </StatusBadge>
              </h3>
              <p>
                {index.embedded_count} / {index.chunk_count} passages prepared
              </p>
              {isActive(index) && (
                <Progress
                  aria-label={`Document set version ${index.version} progress`}
                  value={index.chunk_count ? (index.embedded_count / index.chunk_count) * 100 : 0}
                />
              )}
              {index.error && <p className="error-message">{index.error}</p>}
              <Accordion type="single" collapsible className="source-metadata">
                <AccordionItem value="technical-details">
                  <AccordionTrigger>Technical details</AccordionTrigger>
                  <AccordionContent>
                    <p>{index.id}</p>
                    <p>Created {new Date(index.created_at).toLocaleString()}</p>
                    <p>
                      Model: {index.embedding_config.model} · {index.embedding_config.dimensions}{' '}
                      dimensions
                    </p>
                    <p>
                      Provider: {index.embedding_config.provider} · Revision:{' '}
                      {index.embedding_config.revision}
                    </p>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>
            {isActive(index) ? (
              <Button variant="outline" disabled={busy} onClick={() => onCancel(index)}>
                Cancel document set {index.version}
              </Button>
            ) : index.status === 'succeeded' ? (
              <Button
                variant="outline"
                disabled={searching}
                aria-pressed={selectedId === index.id}
                onClick={() => onSelect(index)}
              >
                Use document set {index.version}
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      {page && (
        <Pagination
          offset={offset}
          total={page.total}
          pageSize={page.limit}
          onChange={onPage}
          label="Document set pages"
        />
      )}
    </>
  );
}
