import { formatRetrievalScores } from '../../../lib/retrieval';
import { useEffect, type ReactNode } from 'react';
import { BookOpenCheck, ChevronRight, CircleAlert } from 'lucide-react';
import { AnswerText } from '../../../components/AnswerText';
import { Badge } from '../../../components/ui/badge';
import { LIST, LIST_ROW, META, PRE, SUMMARY } from '../../../components/parts';
import { cn } from '../../../lib/utils';
import { type QueryRun } from '../model';

/** The asked question, aligned to the right like a sent message. */
export function QuestionBubble({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="ml-auto flex w-fit max-w-4/5 flex-col gap-1 rounded-card bg-surface-hover px-4 py-3">
      <span className={META}>{label}</span>
      <p className="text-sm text-foreground wrap-anywhere whitespace-pre-wrap">{children}</p>
    </div>
  );
}

/** A collapsed block of supporting detail, such as raw settings or metadata. */
export function Disclosure({
  summary,
  children,
  open,
}: {
  summary: ReactNode;
  children: ReactNode;
  open?: boolean;
}) {
  return (
    <details className="group border-t border-border" open={open}>
      <summary className={SUMMARY}>
        <ChevronRight
          aria-hidden="true"
          className="transition-transform duration-(--transition-fast) group-open:rotate-90"
        />
        {summary}
      </summary>
      <div className="flex flex-col gap-2 pb-3 text-xs text-foreground-muted wrap-anywhere">
        {children}
      </div>
    </details>
  );
}

function RunAlert({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="flex items-start gap-2 text-sm text-danger">
      <span className="flex size-(--icon-lg) shrink-0 items-center justify-center">
        <CircleAlert aria-hidden="true" className="size-4" />
      </span>
      <span className="min-w-0 wrap-anywhere">{children}</span>
    </p>
  );
}

export function RunResult({
  run,
  onCitation,
}: {
  run: QueryRun;
  onCitation?: (label: string) => void;
}) {
  const s = run.snapshot;
  const citationCount = s.citations?.valid.length ?? 0;
  const qualityMessage =
    run.status === 'failed'
      ? s.evidence.length
        ? 'Retrieval completed; answer generation failed.'
        : 'The run failed before usable evidence was available.'
      : run.status === 'insufficient_evidence'
        ? 'The model correctly stopped because the passages were insufficient.'
        : s.citations?.missing || s.citations?.invalid.length
          ? 'Review citation coverage before trusting this answer.'
          : 'The answer includes links to the supplied evidence.';
  return (
    <section className="flex flex-col gap-4 py-4" aria-label="Query result">
      <QuestionBubble label="You">{run.question}</QuestionBubble>
      <h2
        className={cn(
          'flex items-center gap-2 text-sm font-semibold',
          run.status === 'failed' ? 'text-danger' : 'text-foreground-muted',
        )}
      >
        <BookOpenCheck aria-hidden="true" className="size-4" />
        {run.status === 'insufficient_evidence'
          ? 'Insufficient evidence'
          : run.status === 'failed'
            ? 'Answer failed'
            : run.status === 'running'
              ? 'Run in progress'
              : 'Answer'}
      </h2>
      {run.error && <RunAlert>{run.error}</RunAlert>}
      {run.status === 'running' && (
        <p role="status" className="text-sm text-foreground-muted">
          Generating the answer…
        </p>
      )}
      {run.status !== 'running' && (
        <aside
          className="flex flex-col gap-2 rounded-card border border-border bg-surface p-4"
          aria-label="RAG quality check"
        >
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">Index version {run.index_version}</Badge>
            <Badge variant="outline">
              {s.evidence.length} {s.evidence.length === 1 ? 'passage' : 'passages'} supplied
            </Badge>
            {run.answer && (
              <Badge variant="outline">
                {citationCount} citation {citationCount === 1 ? 'link' : 'links'}
              </Badge>
            )}
          </div>
          <p className="text-xs text-foreground-muted">{qualityMessage}</p>
          {run.answer && (
            <p className="text-xs text-foreground-muted">
              Citation links verify source membership, not factual correctness. Review Sources &amp;
              details for support.
            </p>
          )}
        </aside>
      )}
      {run.answer && (
        <div className="text-base text-foreground">
          <AnswerText text={run.answer} citations={s.citations?.valid} onCitation={onCitation} />
        </div>
      )}
      {!!s.citations?.invalid.length && (
        <RunAlert>
          Invalid citation references: {s.citations.invalid.join(', ')}. These references were not
          supplied to the model.
        </RunAlert>
      )}
      {s.citations?.missing && (
        <RunAlert>
          The answer has no citation references. Review its claims against the evidence.
        </RunAlert>
      )}
    </section>
  );
}
export function RunInspector({
  run,
  mode,
  sourceLabel = '',
  focusRequest = 0,
}: {
  run: QueryRun;
  mode: 'sources' | 'details';
  sourceLabel?: string;
  focusRequest?: number;
}) {
  const s = run.snapshot;
  const duration = (n: number | null) => (n == null ? 'Unavailable' : `${(n / 1000).toFixed(2)} s`);
  const firstSource = s.evidence[0]?.label === sourceLabel;
  useEffect(() => {
    if (mode !== 'sources' || !sourceLabel) {
      return;
    }
    const el = document.getElementById(`evidence-${sourceLabel}`);
    el?.focus({ preventScroll: true });
    // The side panel body is the scrolling container on desktop.
    const container = el?.closest('#playground-settings')?.querySelector('[data-panel-body]');
    if (container && firstSource) {
      container.scrollTop = 0;
    } else {
      el?.scrollIntoView?.({ block: 'start' });
    }
  }, [run.id, mode, sourceLabel, firstSource, focusRequest]);
  return (
    <section
      className="flex min-w-0 flex-col gap-3 wrap-anywhere"
      aria-label={mode === 'sources' ? 'Supporting evidence' : 'Answer details'}
    >
      {mode === 'sources' ? (
        <>
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold text-foreground">Sources ({s.evidence.length})</h3>
            <p className={META}>
              Evidence used for this answer. Check that it supports the claims.
            </p>
          </div>
          {s.evidence.length ? (
            <ol className={LIST}>
              {s.evidence.map((e) => (
                <li
                  key={e.label}
                  id={`evidence-${e.label}`}
                  tabIndex={-1}
                  className={cn(
                    LIST_ROW,
                    'flex flex-col gap-2 p-4 outline-none focus:outline-2 focus:-outline-offset-2 focus:outline-accent',
                  )}
                >
                  <h4 className="text-sm font-medium text-foreground">
                    [{e.label}] {e.source_url ?? e.filename}
                  </h4>
                  <p className={META}>
                    {e.page_number ? `Page ${e.page_number} · ` : ''}Passage {e.ordinal + 1} · Rank{' '}
                    {e.rank}
                  </p>
                  <p className="text-sm text-foreground whitespace-pre-wrap">{e.text}</p>
                  <Disclosure summary="Source metadata">
                    <p>
                      Processing version {e.processing_version} · {formatRetrievalScores(e)}
                    </p>
                    <p>
                      Distance: lower is closer. Keyword and RRF scores: higher ranks first. Scores
                      are not confidence.
                    </p>
                  </Disclosure>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-foreground-muted">No evidence was sent.</p>
          )}
          {!!s.omitted_count && (
            <p className={META}>{s.omitted_count} chunks omitted for context capacity.</p>
          )}
        </>
      ) : (
        <>
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold text-foreground">Answer details</h3>
            <p className={META}>
              {s.pipeline_preview
                ? `Test draft${s.base_version ? ` · Based on version ${s.base_version}` : ''}`
                : run.pipeline_version_id
                  ? `Pipeline version ${s.pipeline_version}`
                  : 'Default answer settings'}{' '}
              · {run.status.replaceAll('_', ' ')}
            </p>
          </div>
          <p className="text-sm text-foreground">
            Document set version {run.index_version} · Up to {s.top_k} source passages
          </p>
          <p className="text-sm text-foreground">
            {s.actual_model || s.generation_config?.model || 'Model unavailable'}
          </p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-card border border-border p-4 text-sm">
            <dt className="text-foreground-muted">Finding passages</dt>
            <dd className="text-foreground tabular-nums">{duration(s.retrieval_ms)}</dd>
            <dt className="text-foreground-muted">Writing answer</dt>
            <dd className="text-foreground tabular-nums">{duration(s.generation_ms)}</dd>
            <dt className="text-foreground-muted">Total</dt>
            <dd className="text-foreground tabular-nums">{duration(s.total_ms)}</dd>
            <dt className="text-foreground-muted">Answer cost</dt>
            <dd className="text-foreground tabular-nums">
              {s.cost_usd == null ? 'Unavailable' : `$${s.cost_usd.toFixed(6)} (provider reported)`}
            </dd>
            <dt className="text-foreground-muted">Model usage</dt>
            <dd className="text-foreground tabular-nums">
              {s.usage
                ? Object.entries(s.usage)
                    .map(([k, v]) => `${k.replaceAll('_', ' ')}: ${v}`)
                    .join(' · ')
                : 'Unavailable'}
            </dd>
          </dl>
          {s.cost_basis && <p className={META}>{s.cost_basis}</p>}
          <div className="flex flex-col">
            {s.retrieval && (
              <Disclosure summary="Retrieval settings and results">
                <pre className={PRE}>
                  {JSON.stringify({ settings: s.retrieval, result: s.retrieval_result }, null, 2)}
                </pre>
              </Disclosure>
            )}
            {s.messages && (
              <Disclosure summary="Effective prompt and generation settings">
                <pre className={PRE}>
                  {JSON.stringify(
                    { messages: s.messages, generation: s.generation_config },
                    null,
                    2,
                  )}
                </pre>
              </Disclosure>
            )}
            <Disclosure summary="Exact pipeline settings">
              <pre className={PRE}>{JSON.stringify(s.pipeline_execution, null, 2)}</pre>
            </Disclosure>
            <Disclosure summary="Run identity">
              <p>Run {run.id}</p>
              {run.pipeline_version_id && <p>Pipeline version {run.pipeline_version_id}</p>}
            </Disclosure>
          </div>
        </>
      )}
    </section>
  );
}
