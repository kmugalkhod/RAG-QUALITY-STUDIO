import type { Page } from '../../../lib/pagination';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button } from '../../../components/ui/button';
import * as api from '../api';
import { type Document, type Run } from '../model';
import { Pagination } from '../../../components/Pagination';
import { active, date, message } from '../documentPresentation';
import { ChunkInspector } from './ChunkInspector';
import { StatusBadge } from '../../../components/StatusBadge';
export function DocumentInspector({
  projectId,
  document,
  onChange,
}: {
  projectId: string;
  document: Document;
  onChange: () => void;
}) {
  const [size, setSize] = useState('1000');
  const [overlap, setOverlap] = useState('200');
  const [runs, setRuns] = useState<Page<Run>>();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [selectedRun, setSelectedRun] = useState<Run>();
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const historyTitle = useRef<HTMLHeadingElement>(null);
  const focusPage = useRef(false);
  const [notice, setNotice] = useState('');
  const [activeRun, setActiveRun] = useState(false);
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    title.current?.focus();
  }, []);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const result = await api.listProcessingRuns(projectId, document.id, offset);
        const latest = offset === 0 ? result : await api.listProcessingRuns(projectId, document.id);
        if (!disposed) {
          setRuns(result);
          setActiveRun(latest.items.some(active));
          setLoadError('');
          setLoading(false);
          if (focusPage.current) {
            historyTitle.current?.focus();
            focusPage.current = false;
          }
        }
      } catch (err) {
        if (!disposed) {
          setLoadError(message(err));
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
  }, [projectId, document.id, offset, revision]);
  async function start(event: FormEvent) {
    event.preventDefault();
    setNotice('');
    setError('');
    const chunkSize = Number(size),
      chunkOverlap = Number(overlap);
    if (
      !size ||
      !overlap ||
      !Number.isInteger(chunkSize) ||
      !Number.isInteger(chunkOverlap) ||
      chunkSize <= 0 ||
      chunkSize > 100000 ||
      chunkOverlap < 0 ||
      chunkOverlap >= chunkSize
    ) {
      setError(
        'Chunk size must be 1–100,000 characters. Overlap must be zero or more and smaller than chunk size.',
      );
      return;
    }
    setBusy(true);
    try {
      const result = await api.startProcessingRun(projectId, document.id, chunkSize, chunkOverlap);
      setNotice(`Version ${result.version} created. Follow its status in processing history.`);
      setActiveRun(true);
      setOffset(0);
      setRevision((n) => n + 1);
      onChange();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  async function cancel(run: Run) {
    setBusy(true);
    setError('');
    try {
      const result = await api.cancelProcessingRun(projectId, document.id, run.id);
      setNotice(
        result.status === 'cancelled'
          ? 'Run cancelled. In-flight parsing stops at its next checkpoint; no chunks will be published.'
          : `Run is already ${result.status}.`,
      );
      setRevision((n) => n + 1);
      onChange();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="inspector mt-9 border-t border-border pt-7 scroll-mt-5"
      aria-labelledby="inspector-title"
    >
      <h2 ref={title} tabIndex={-1} id="inspector-title">
        Process: {document.filename}
      </h2>
      <details className="source-metadata text-[11px] wrap-anywhere text-muted-foreground my-4.5 mx-0">
        <summary>Source metadata</summary>
        <p>Document ID: {document.id}</p>
        <p>SHA-256: {document.content_hash}</p>
      </details>
      <form onSubmit={start} noValidate>
        <details className="source-metadata text-[11px] wrap-anywhere text-muted-foreground my-4.5 mx-0">
          <summary>Advanced processing options</summary>
          <div className="chunk-settings flex items-end flex-wrap gap-3">
            <div>
              <Label htmlFor="chunk-size">Chunk size (characters)</Label>
              <Input
                id="chunk-size"
                type="number"
                min="1"
                max="100000"
                value={size}
                onChange={(e) => setSize(e.target.value)}
                disabled={busy}
              />
            </div>
            <div>
              <Label htmlFor="chunk-overlap">Overlap (characters)</Label>
              <Input
                id="chunk-overlap"
                type="number"
                min="0"
                value={overlap}
                onChange={(e) => setOverlap(e.target.value)}
                disabled={busy}
              />
            </div>
          </div>
        </details>
        <Button disabled={busy || activeRun || !runs} type="submit">
          {busy ? 'Saving…' : 'Start processing'}
        </Button>
        <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
          Each start saves a new version. Fixed character windows preserve whitespace and never
          cross PDF pages. A failed or cancelled run can be retried by starting a new version.
        </p>
      </form>
      {loadError && (
        <p role="alert" className="error-message text-xs mt-4 text-destructive">
          {loadError}
        </p>
      )}
      {error && (
        <p role="alert" className="error-message text-xs mt-4 text-destructive">
          {error}
        </p>
      )}
      <p
        role="status"
        className="success-message pt-4 px-0 pb-0 text-[11px] wrap-anywhere text-success"
      >
        {notice}
      </p>
      <div className="section-heading flex justify-between items-center gap-2.5 m-0 py-4 px-7">
        <h3 ref={historyTitle} tabIndex={-1}>
          Processing history
        </h3>
        <Button variant="outline" size="sm" onClick={() => setRevision((n) => n + 1)}>
          Refresh history
        </Button>
      </div>
      {loading && runs && <p role="status">Loading processing history…</p>}
      {!runs ? (
        <p role="status">Loading processing history…</p>
      ) : !runs.total ? (
        <p>No processing runs yet. Choose your settings above.</p>
      ) : (
        <ul className="run-list">
          {runs.items.map((run) => (
            <li key={run.id}>
              <div>
                <h3>
                  Version {run.version} <StatusBadge status={run.status} />
                </h3>
                <p>
                  {run.chunk_size} characters · {run.overlap} overlap · {date(run.created_at)}
                </p>
                <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
                  {run.parser_version} · {run.config_version}
                </p>
                {active(run) && (
                  <p role="status">
                    {run.status === 'queued' ? 'Waiting for a worker' : 'Processing text'} ·{' '}
                    {run.progress}% · attempt {run.attempts}/3
                  </p>
                )}
                {run.error && (
                  <p className="error-message text-xs mt-4 text-destructive">{run.error}</p>
                )}
              </div>
              <div>
                {active(run) && (
                  <Button variant="outline" disabled={busy} onClick={() => void cancel(run)}>
                    Cancel run
                  </Button>
                )}
                {run.status === 'succeeded' && (
                  <Button variant="outline" onClick={() => setSelectedRun(run)}>
                    Inspect {run.chunk_count} chunks
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {runs && (
        <Pagination
          offset={offset}
          total={runs.total}
          onChange={(value) => {
            focusPage.current = true;
            setOffset(value);
          }}
          busy={loading}
          label="Processing history pages"
        />
      )}
      {selectedRun && (
        <ChunkInspector
          key={selectedRun.id}
          projectId={projectId}
          documentId={document.id}
          run={selectedRun}
        />
      )}
    </section>
  );
}
