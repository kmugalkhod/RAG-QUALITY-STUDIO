import type { Page } from '../../lib/pagination';
import { DocumentInspector } from './components/DocumentInspector';
import { DocumentTable } from './components/DocumentTable';
import { DocumentUpload } from './components/DocumentUpload';
import { message } from './documentPresentation';
import { IndexPanel } from './components/IndexPanel';
import { useEffect, useState } from 'react';
import { FileText, Plus, X, Files, Database } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import * as api from './api';
import { type Document } from './model';
import { allPages } from '../../lib/pagination';
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
  function setTab(value: 'documents' | 'indexes') {
    setTabState(value);
    const [path, search] = window.location.hash.split('?');
    const query = new URLSearchParams(search);
    if (value === 'indexes') {
      query.set('view', value);
    } else {
      query.delete('view');
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
  const [showUpload, setShowUpload] = useState(
    () => new URLSearchParams(window.location.hash.split('?')[1]).get('upload') === '1',
  );
  const [limit, setLimit] = useState<number>();
  const [page, setPage] = useState<Page<Document>>();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [settingsError, setSettingsError] = useState('');
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState('');
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
      try {
        const result = await api.listDocuments(projectId, offset);
        if (!disposed) {
          setPage(result);
          setError('');
          setLoading(false);
        }
      } catch (err) {
        if (!disposed) {
          setError(message(err));
          setLoading(false);
        }
      }
      if (!disposed) {
        timer = setTimeout(() => void load(), 2000);
      }
    }
    setLoading(true);
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [projectId, offset, revision]);
  function handleUploaded(document: Document) {
    setNotice(`“${document.filename}” uploaded. Select chunk settings and start processing.`);
    setShowUpload(false);
    selectDocument(document);
    setOffset(0);
    setRevision((value) => value + 1);
  }
  return (
    <div className="knowledge-page">
      <div className="knowledge-heading flex items-center justify-between gap-5 pt-6.5 px-7 pb-5.5">
        <div>
          <h1>Knowledge Base</h1>
          <p>Source documents and searchable indexes.</p>
        </div>
        <Button
          variant={selected || showUpload ? 'outline' : 'default'}
          onClick={() => {
            setTab('documents');
            setShowUpload((v) => !v);
          }}
          aria-expanded={showUpload}
          aria-controls="upload-panel"
        >
          <Plus size={15} />
          Add document
        </Button>
      </div>
      <Tabs value={tab} onValueChange={(value) => setTab(value as typeof tab)}>
        <TabsList
          variant="line"
          className="knowledge-tabs w-full justify-start border-b border-border px-7"
          aria-label="Knowledge Base views"
        >
          <TabsTrigger value="documents">
            <Files />
            Documents {page && <span>{page.total}</span>}
          </TabsTrigger>
          <TabsTrigger value="indexes">
            <Database />
            Document sets
          </TabsTrigger>
        </TabsList>
        {showUpload && (
          <DocumentUpload
            projectId={projectId}
            limit={limit}
            settingsError={settingsError}
            onRetrySettings={() => setRevision((value) => value + 1)}
            onUploaded={handleUploaded}
          />
        )}
        {notice && (
          <p role="status" className="success-message mx-7">
            {notice}
          </p>
        )}
        {!showUpload && settingsError && (
          <p role="alert" className="error-message text-xs mt-4 text-destructive">
            {settingsError}
          </p>
        )}
        <div
          className={`knowledge-split grid grid-cols-[minmax(0,_1fr)] min-h-[calc(100dvh_-_182px)] ${selected && tab === 'documents' ? 'has-inspector' : ''}`}
        >
          <div className="knowledge-body min-w-0">
            <TabsContent value="documents">
              <DocumentTable
                page={page}
                offset={offset}
                loading={loading}
                error={error}
                selectedId={selected?.id}
                onRefresh={() => setRevision((value) => value + 1)}
                onPage={setOffset}
                onSelect={selectDocument}
              />
            </TabsContent>
            <TabsContent value="indexes">
              <IndexPanel key={projectId} projectId={projectId} />
            </TabsContent>
          </div>
          {selected && tab === 'documents' && (
            <aside className="document-detail" aria-label="Document details">
              <div className="detail-toolbar">
                <span>
                  <FileText />
                  Document details
                </span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => selectDocument()}
                  aria-label="Close document details"
                >
                  <X />
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
