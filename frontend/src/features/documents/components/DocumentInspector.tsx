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
import { LoadingState } from '../../../components/states/LoadingState';
import { cn } from '../../../lib/utils';
import { InlineError, LIST, LIST_ROW, META, Notice, SUMMARY } from '../../../components/parts';
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
    <section className="flex min-w-0 flex-col gap-4" aria-labelledby="inspector-title">
      <h2
        ref={title}
        tabIndex={-1}
        id="inspector-title"
        className="text-base font-semibold text-foreground outline-none wrap-anywhere"
      >
        Process: {document.filename}
      </h2>
      <details className="border-y border-border">
        <summary className={SUMMARY}>Source metadata</summary>
        <div className={cn(META, 'flex flex-col gap-1 pb-3 wrap-anywhere')}>
          <p>Document ID: {document.id}</p>
          <p>SHA-256: {document.content_hash}</p>
        </div>
      </details>
      <form onSubmit={start} noValidate className="flex flex-col gap-3">
        <details className="border-b border-border">
          <summary className={SUMMARY}>Advanced processing options</summary>
          <div className="grid grid-cols-2 gap-3 pb-4">
            <div className="flex min-w-0 flex-col">
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
            <div className="flex min-w-0 flex-col">
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
        <Button disabled={busy || activeRun || !runs} type="submit" className="w-full">
          {busy ? 'Saving…' : 'Start processing'}
        </Button>
        <p className={META}>
          Each start saves a new version. Fixed character windows preserve whitespace and never
          cross PDF pages. A failed or cancelled run can be retried by starting a new version.
        </p>
      </form>
      {loadError && <InlineError>{loadError}</InlineError>}
      {error && <InlineError>{error}</InlineError>}
      <Notice>{notice}</Notice>
      <div className="flex items-center justify-between gap-2 border-t border-border pt-4">
        <h3
          ref={historyTitle}
          tabIndex={-1}
          className="text-sm font-semibold text-foreground outline-none"
        >
          Processing history
        </h3>
        <Button variant="outline" size="sm" onClick={() => setRevision((n) => n + 1)}>
          Refresh history
        </Button>
      </div>
      {loading && runs && (
        <p className={META} role="status">
          Loading processing history…
        </p>
      )}
      {!runs ? (
        <LoadingState label="Loading processing history…" rows={2} />
      ) : !runs.total ? (
        <p className="text-sm text-foreground-muted">
          No processing runs yet. Choose your settings above.
        </p>
      ) : (
        <ul className={LIST}>
          {runs.items.map((run) => (
            <li key={run.id} className={cn(LIST_ROW, 'flex flex-col gap-2 p-3')}>
              <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold text-foreground">
                Version {run.version} <StatusBadge status={run.status} />
              </h3>
              <p className={META}>
                {run.chunk_size} characters · {run.overlap} overlap · {date(run.created_at)}
              </p>
              <p className={cn(META, 'wrap-anywhere')}>
                {run.parser_version} · {run.config_version}
              </p>
              {active(run) && (
                <p role="status" className="text-xs text-foreground">
                  {run.status === 'queued' ? 'Waiting for a worker' : 'Processing text'} ·{' '}
                  {run.progress}% · attempt {run.attempts}/3
                </p>
              )}
              {run.error && <p className="text-xs text-danger wrap-anywhere">{run.error}</p>}
              {(active(run) || run.status === 'succeeded') && (
                <div className="flex flex-wrap gap-2">
                  {active(run) && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => void cancel(run)}
                    >
                      Cancel run
                    </Button>
                  )}
                  {run.status === 'succeeded' && (
                    <Button variant="outline" size="sm" onClick={() => setSelectedRun(run)}>
                      Inspect {run.chunk_count} chunks
                    </Button>
                  )}
                </div>
              )}
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
