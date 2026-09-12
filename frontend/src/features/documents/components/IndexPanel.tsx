import {
  createDefaultRetrievalSettings,
  validateRetrievalSettings,
  type RetrievalSettings,
} from '../../../lib/retrieval';
import { useEffect, useState, type FormEvent } from 'react';
import * as api from '../indexApi';
import {
  type EmbeddingSettings,
  type IndexPage,
  type IndexVersion,
  type Retrieval,
} from '../model';
import { IndexList } from './IndexList';
import { IndexSearch } from './IndexSearch';
const message = (e: unknown) =>
  e instanceof Error ? e.message : 'Request failed. Please try again.';
export function IndexPanel({ projectId }: { projectId: string }) {
  const [page, setPage] = useState<IndexPage>();
  const [settings, setSettings] = useState<EmbeddingSettings>();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<IndexVersion>();
  const [query, setQuery] = useState('');
  const [retrieval, setRetrieval] = useState<RetrievalSettings>(createDefaultRetrievalSettings());
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [result, setResult] = useState<Retrieval>();
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const [indexes, config] = await Promise.all([
          api.listIndexes(projectId, offset),
          api.getEmbeddingSettings(projectId),
        ]);
        if (!disposed) {
          setPage(indexes);
          setSettings(config);
          setLoadError('');
        }
      } catch (e) {
        if (!disposed) {
          setLoadError(message(e));
        }
      }
      if (!disposed) {
        timer = setTimeout(() => void load(), 2000);
      }
    }
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [projectId, offset, revision]);
  useEffect(() => {
    let disposed = false;
    let request = 0;
    const restore = () => {
      const seq = ++request;
      const id = new URLSearchParams(window.location.hash.split('?')[1]).get('index');
      setSelected(undefined);
      setResult(undefined);
      setSearchError('');
      if (id) {
        void api
          .getIndex(projectId, id)
          .then((index) => {
            if (disposed || seq !== request) {
              return;
            }
            if (index.status === 'succeeded') {
              setSelected(index);
            } else {
              setSearchError(
                'These documents are still being prepared. Choose a version marked Ready for questions.',
              );
            }
          })
          .catch((e) => {
            if (!disposed && seq === request) {
              setSearchError(message(e));
            }
          });
      }
    };
    restore();
    window.addEventListener('hashchange', restore);
    return () => {
      disposed = true;
      window.removeEventListener('hashchange', restore);
    };
  }, [projectId]);
  function selectIndex(index: IndexVersion) {
    setSelected(index);
    setResult(undefined);
    setSearchError('');
    const [path, search] = window.location.hash.split('?');
    const params = new URLSearchParams(search);
    params.set('view', 'indexes');
    params.set('index', index.id);
    window.location.hash = `${path || `#/projects/${projectId}/knowledge-base`}?${params}`;
  }
  async function create() {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const index = await api.createIndex(projectId);
      setNotice(
        `Document set version ${index.version} created with ${index.chunk_count} passages. Follow its status below.`,
      );
      setOffset(0);
      setRevision((n) => n + 1);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function cancel(index: IndexVersion) {
    setBusy(true);
    setError('');
    try {
      const value = await api.cancelIndex(projectId, index.id);
      setNotice(
        value.status === 'cancelled'
          ? `Document set version ${index.version} cancelled. In-flight requests may finish, but cannot publish.`
          : `Document set version ${index.version} is already ${value.status}.`,
      );
      setRevision((n) => n + 1);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function search(event: FormEvent) {
    event.preventDefault();
    setSearchError('');
    setResult(undefined);
    if (
      !selected ||
      !query.trim() ||
      query.trim().length > 8000 ||
      validateRetrievalSettings(retrieval).length > 0
    ) {
      setSearchError(
        'Choose a prepared document set, enter a query of 1–8,000 characters, and set results to an integer from 1 to 50.',
      );
      return;
    }
    setSearching(true);
    try {
      setResult(await api.retrieve(projectId, selected.id, query.trim(), retrieval));
    } catch (e) {
      setSearchError(message(e));
    } finally {
      setSearching(false);
    }
  }
  return (
    <section className="inspector" aria-labelledby="index-title">
      <IndexList
        page={page}
        settings={settings}
        offset={offset}
        selectedId={selected?.id}
        busy={busy}
        searching={searching}
        loadError={loadError}
        error={error}
        notice={notice}
        onCreate={() => void create()}
        onRefresh={() => setRevision((value) => value + 1)}
        onPage={setOffset}
        onCancel={(index) => void cancel(index)}
        onSelect={selectIndex}
      />
      <IndexSearch
        selected={selected}
        query={query}
        settings={retrieval}
        searching={searching}
        error={searchError}
        result={result}
        onQueryChange={(value) => {
          setQuery(value);
          setResult(undefined);
        }}
        onSettingsChange={(value) => {
          setRetrieval(value);
          setResult(undefined);
        }}
        onSubmit={search}
      />
    </section>
  );
}
