import { DocumentInspector } from './components/DocumentInspector';
import { DocumentTable, groupDocuments } from './components/DocumentTable';
import { DocumentUpload } from './components/DocumentUpload';
import { active, message } from './documentPresentation';
import { IndexesWorkspace } from './components/IndexesWorkspace';
import { useEffect, useMemo, useState } from 'react';
import { FileText, Plus, X, Files, Database, ArrowRight } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { PageHeader } from '../../components/PageHeader';
import { cn } from '../../lib/utils';
import { CARD, InlineError, Notice } from '../../components/parts';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import * as api from './api';
import { type Document } from './model';
import { allPages } from '../../lib/pagination';
const DOCUMENT_PAGE_SIZE = 20;
const JOURNEY = [
  'Add documents',
  'Prepare content',
  'Publish a collection',
  'Retrieve in pipelines',
];
export function KnowledgeBase({
  projectId,
  documentId = '',
}: {
  projectId: string;
  documentId?: string;
}) {
  const [tab, setTabState] = useState<'documents' | 'indexes'>(() =>
    new URLSearchParams(window.location.hash.split('?')[1]).get('view') === 'indexes'
      ? 'indexes'
      : 'documents',
  );
  const [showUpload, setShowUpload] = useState(
    () => new URLSearchParams(window.location.hash.split('?')[1]).get('upload') === '1',
  );
  function setTab(value: 'documents' | 'indexes') {
    setTabState(value);
    const [path, search] = window.location.hash.split('?');
    const query = new URLSearchParams(search);
    if (value === 'indexes') {
      setShowUpload(false);
      query.set('view', value);
      if (!query.get('mode')) {
        query.set('mode', 'indexes');
      }
    } else {
      query.delete('view');
      query.delete('mode');
      query.delete('index');
      query.delete('snapshot');
      query.delete('section');
    }
    window.location.hash = `${path || `/projects/${projectId}/knowledge-base`}${query.size ? `?${query}` : ''}`;
  }
  useEffect(() => {
    const update = () =>
      setTabState(
        new URLSearchParams(window.location.hash.split('?')[1]).get('view') === 'indexes'
          ? 'indexes'
          : 'documents',
      );
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  const [limit, setLimit] = useState<number>();
  const [documents, setDocuments] = useState<Document[]>();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [settingsError, setSettingsError] = useState('');
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState('');
  const [mutationError, setMutationError] = useState('');
  const [deletingId, setDeletingId] = useState<string>();
  const [sort, setSort] = useState<'newest' | 'oldest'>('newest');
  const [selected, setSelected] = useState<Document>();
  function selectDocument(document?: Document) {
    setSelected(document);
    window.location.hash = `/projects/${projectId}/knowledge-base${document ? `?document=${document.id}` : ''}`;
  }
  useEffect(() => {
    let disposed = false;
    if (!documentId) {
      setSelected(undefined);
      return;
    }
    void allPages((o) => api.listDocuments(projectId, o))
      .then((documents) => {
        if (!disposed) {
          const found = documents.find((d) => d.id === documentId);
          setSelected(found);
          if (!found) {
            setError('This document is unavailable in this project.');
          }
        }
      })
      .catch((e) => {
        if (!disposed) {
          setError(message(e));
        }
      });
    return () => {
      disposed = true;
    };
  }, [projectId, documentId]);
  useEffect(() => {
    let disposed = false;
    void api
      .getUploadSettings(projectId)
      .then((settings) => {
        if (!disposed) {
          setLimit(settings.max_upload_bytes);
          setSettingsError('');
        }
      })
      .catch((err) => {
        if (!disposed) {
          setSettingsError(message(err));
        }
      });
    return () => {
      disposed = true;
    };
  }, [projectId, revision]);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      let nextDelay = 10_000;
      try {
        const result = await allPages((nextOffset) => api.listDocuments(projectId, nextOffset));
        if (result.some((document) => active(document.latest_run))) {
          nextDelay = 2_000;
        }
        if (!disposed) {
          setDocuments(result);
          setError('');
          setLoading(false);
        }
      } catch (err) {
        nextDelay = 5_000;
        if (!disposed) {
          setError(message(err));
          setLoading(false);
        }
      }
      if (!disposed) {
        timer = setTimeout(() => void load(), nextDelay);
      }
    }
    setLoading(true);
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [projectId, revision]);

  const documentGroups = useMemo(() => {
    const groups = groupDocuments(documents ?? []);
    return groups.sort((a, b) => {
      const difference = Date.parse(b.createdAt) - Date.parse(a.createdAt);
      return (
        (sort === 'newest' ? difference : -difference) || a.document.id.localeCompare(b.document.id)
      );
    });
  }, [documents, sort]);
  const visibleDocumentGroups = documentGroups.slice(offset, offset + DOCUMENT_PAGE_SIZE);

  useEffect(() => {
    if (offset > 0 && offset >= documentGroups.length) {
      setOffset(0);
    }
  }, [documentGroups.length, offset]);
  function handleUploaded(document: Document) {
    setNotice(`“${document.filename}” uploaded. Select chunk settings and start processing.`);
    setShowUpload(false);
    selectDocument(document);
    setOffset(0);
    setRevision((value) => value + 1);
  }
  async function handleDelete(document: Document, uploadCount: number) {
    setNotice('');
    setMutationError('');
    if (active(document.latest_run)) {
      setMutationError('Cancel the active processing run before deleting this document.');
      return;
    }
    const duplicateNote =
      uploadCount > 1
        ? ` ${uploadCount - 1} identical upload${uploadCount === 2 ? '' : 's'} will remain.`
        : '';
    if (
      !window.confirm(
        `Delete “${document.filename}”? Its unreferenced processing history will also be removed.${duplicateNote} This cannot be undone.`,
      )
    ) {
      return;
    }
    setDeletingId(document.id);
    try {
      await api.deleteDocument(projectId, document.id);
      setDocuments((current) => current?.filter((item) => item.id !== document.id));
      if (selected?.id === document.id) {
        selectDocument();
      }
      setNotice(
        uploadCount > 1
          ? `“${document.filename}” deleted. ${uploadCount - 1} identical upload${uploadCount === 2 ? '' : 's'} remain${uploadCount === 2 ? 's' : ''}.`
          : `“${document.filename}” deleted.`,
      );
      setRevision((value) => value + 1);
    } catch (err) {
      setMutationError(message(err));
    } finally {
      setDeletingId(undefined);
    }
  }
  const inspecting = Boolean(selected && tab === 'documents');
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Knowledge Base"
        meta="Add sources, prepare their content, then publish a fixed version for retrieval."
        action={
          <Button
            variant={selected || showUpload || tab === 'indexes' ? 'outline' : 'primary'}
            onClick={() => {
              setTab('documents');
              setShowUpload((v) => !v);
            }}
            aria-expanded={showUpload}
            aria-controls="upload-panel"
          >
            <Plus aria-hidden="true" />
            Add document
          </Button>
        }
      />
      <Tabs value={tab} onValueChange={(value) => setTab(value as typeof tab)} className="gap-6">
        <div className="border-b border-border">
          <TabsList variant="line" className="justify-start" aria-label="Knowledge Base views">
            <TabsTrigger value="documents" className="flex-none px-3">
              <Files aria-hidden="true" />
              Documents{' '}
              {documents && (
                <span className="text-foreground-muted tabular-nums">{documentGroups.length}</span>
              )}
            </TabsTrigger>
            <TabsTrigger value="indexes" className="flex-none px-3">
              <Database aria-hidden="true" />
              Collections
            </TabsTrigger>
          </TabsList>
        </div>
        <ol
          className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-foreground-muted"
          aria-label="How knowledge becomes searchable"
        >
          {JOURNEY.map((step, index) => (
            <li key={step} className="flex items-center gap-2">
              {index > 0 && (
                <ArrowRight aria-hidden="true" className="size-4 text-foreground-subtle" />
              )}
              <span className="flex size-4 items-center justify-center rounded-full border border-border-strong tabular-nums">
                {index + 1}
              </span>
              {step}
            </li>
          ))}
        </ol>
        {showUpload && (
          <DocumentUpload
            projectId={projectId}
            limit={limit}
            settingsError={settingsError}
            onRetrySettings={() => setRevision((value) => value + 1)}
            onUploaded={handleUploaded}
          />
        )}
        {notice && <Notice>{notice}</Notice>}
        {mutationError && <InlineError>{mutationError}</InlineError>}
        {!showUpload && settingsError && <InlineError>{settingsError}</InlineError>}
        <div className="flex flex-col gap-6 desktop:flex-row desktop:items-start">
          <div className={cn('min-w-0 flex-1', inspecting && 'max-md:hidden')}>
            <TabsContent value="documents">
              <DocumentTable
                groups={documents ? visibleDocumentGroups : undefined}
                total={documentGroups.length}
                pageSize={DOCUMENT_PAGE_SIZE}
                offset={offset}
                loading={loading}
                error={error}
                selectedId={selected?.id}
                sort={sort}
                deletingId={deletingId}
                onRefresh={() => setRevision((value) => value + 1)}
                onPage={setOffset}
                onSelect={selectDocument}
                onSort={(value) => {
                  setSort(value);
                  setOffset(0);
                }}
                onDelete={(document, uploadCount) => void handleDelete(document, uploadCount)}
                onAdd={() => setShowUpload(true)}
              />
            </TabsContent>
            <TabsContent value="indexes">
              <IndexesWorkspace key={projectId} projectId={projectId} />
            </TabsContent>
          </div>
          {selected && tab === 'documents' && (
            <aside
              className={cn(
                CARD,
                'flex w-full flex-col gap-4 p-4 desktop:w-panel desktop:shrink-0',
              )}
              aria-label="Document details"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 text-xs font-medium text-foreground-muted">
                  <FileText aria-hidden="true" className="size-4 text-foreground-subtle" />
                  Preparation details
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  icon
                  onClick={() => selectDocument()}
                  aria-label="Close document details"
                >
                  <X aria-hidden="true" />
                </Button>
              </div>
              <DocumentInspector
                key={selected.id}
                projectId={projectId}
                document={selected}
                onChange={() => setRevision((value) => value + 1)}
              />
            </aside>
          )}
        </div>
      </Tabs>
    </div>
  );
}
