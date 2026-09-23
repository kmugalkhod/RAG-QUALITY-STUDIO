import { formatRetrievalScores } from '../../../lib/retrieval';
import { useEffect } from 'react';
import { BookOpenCheck } from 'lucide-react';
import { AnswerText } from '../../../components/AnswerText';
import { Badge } from '../../../components/ui/badge';
import { type QueryRun } from '../model';
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
    <section className="query-result border-border" aria-label="Query result">
      <div className="chat-question">
        <span className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
          You
        </span>
        <p>{run.question}</p>
      </div>
      <h2 className="assistant-label">
        <BookOpenCheck size={16} />
        {run.status === 'insufficient_evidence'
          ? 'Insufficient evidence'
          : run.status === 'failed'
            ? 'Answer failed'
            : run.status === 'running'
              ? 'Run in progress'
              : 'Answer'}
      </h2>
      {run.error && (
        <p role="alert" className="error-message text-xs mt-4 text-destructive">
          {run.error}
        </p>
      )}
      {run.status === 'running' && <p role="status">Generating the answer…</p>}
      {run.status !== 'running' && (
        <aside
          className="my-4 rounded-lg border border-border bg-secondary/55 p-3"
          aria-label="RAG quality check"
        >
          <div className="mb-2 flex flex-wrap gap-2">
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
          <p className="m-0 text-xs text-muted-foreground">{qualityMessage}</p>
          {run.answer && (
            <p className="mb-0 mt-1 text-xs text-muted-foreground">
              Citation links verify source membership, not factual correctness. Review Sources &amp;
              details for support.
            </p>
          )}
        </aside>
      )}
      {run.answer && (
        <div className="rag-answer text-[17px]">
          <AnswerText text={run.answer} citations={s.citations?.valid} onCitation={onCitation} />
        </div>
      )}
      {!!s.citations?.invalid.length && (
        <p role="alert" className="error-message text-xs mt-4 text-destructive">
          Invalid citation references: {s.citations.invalid.join(', ')}. These references were not
          supplied to the model.
        </p>
      )}
      {s.citations?.missing && (
        <p role="alert" className="error-message text-xs mt-4 text-destructive">
          The answer has no citation references. Review its claims against the evidence.
        </p>
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
    const container = el?.closest('.answer-inspector');
    if (container && firstSource) {
      container.scrollTop = 0;
    } else {
      el?.scrollIntoView?.({ block: 'start' });
    }
  }, [run.id, mode, sourceLabel, firstSource, focusRequest]);
  return (
    <section
      className="answer-inspector"
      aria-label={mode === 'sources' ? 'Supporting evidence' : 'Answer details'}
    >
      {mode === 'sources' ? (
        <>
          <h2>Sources ({s.evidence.length})</h2>
          <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
            Evidence used for this answer. Check that it supports the claims.
          </p>
          {s.evidence.map((e) => (
            <article key={e.label} id={`evidence-${e.label}`} tabIndex={-1}>
              <h3>
                [{e.label}] {e.source_url ?? e.filename}
              </h3>
              <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
                {e.page_number ? `Page ${e.page_number} · ` : ''}Passage {e.ordinal + 1} · Rank{' '}
                {e.rank}
              </p>
              <p className="rag-source-text">{e.text}</p>
              <details className="source-metadata text-[11px] wrap-anywhere text-muted-foreground my-4.5 mx-0">
                <summary>Source metadata</summary>
                <p>
                  Processing version {e.processing_version} · {formatRetrievalScores(e)}
                </p>
                <p>
                  Distance: lower is closer. Keyword and RRF scores: higher ranks first. Scores are
                  not confidence.
                </p>
              </details>
            </article>
          ))}
          {!s.evidence.length && <p>No evidence was sent.</p>}
          {!!s.omitted_count && (
            <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
              {s.omitted_count} chunks omitted for context capacity.
            </p>
          )}
        </>
      ) : (
        <>
          <h2>Answer details</h2>
          <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
            {s.pipeline_preview
              ? `Test draft${s.base_version ? ` · Based on version ${s.base_version}` : ''}`
              : run.pipeline_version_id
                ? `Pipeline version ${s.pipeline_version}`
                : 'Default answer settings'}{' '}
            · {run.status.replaceAll('_', ' ')}
          </p>
          <p>
            Document set version {run.index_version} · Up to {s.top_k} source passages
          </p>
          <p>{s.actual_model || s.generation_config?.model || 'Model unavailable'}</p>
          <dl className="rag-metrics grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 mt-6 text-[13px]">
            <dt>Finding passages</dt>
            <dd>{duration(s.retrieval_ms)}</dd>
            <dt>Writing answer</dt>
            <dd>{duration(s.generation_ms)}</dd>
            <dt>Total</dt>
            <dd>{duration(s.total_ms)}</dd>
            <dt>Answer cost</dt>
            <dd>
              {s.cost_usd == null ? 'Unavailable' : `$${s.cost_usd.toFixed(6)} (provider reported)`}
            </dd>
            <dt>Model usage</dt>
            <dd>
              {s.usage
                ? Object.entries(s.usage)
                    .map(([k, v]) => `${k.replaceAll('_', ' ')}: ${v}`)
                    .join(' · ')
                : 'Unavailable'}
            </dd>
          </dl>
          {s.cost_basis && (
            <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
              {s.cost_basis}
            </p>
          )}
          {s.retrieval && (
            <details className="source-metadata text-[11px] wrap-anywhere text-muted-foreground my-4.5 mx-0">
              <summary>Retrieval settings and results</summary>
              <pre className="rag-source-text">
                {JSON.stringify({ settings: s.retrieval, result: s.retrieval_result }, null, 2)}
              </pre>
            </details>
          )}
          {s.messages && (
            <details className="source-metadata text-[11px] wrap-anywhere text-muted-foreground my-4.5 mx-0">
              <summary>Effective prompt and generation settings</summary>
              <pre className="rag-source-text">
                {JSON.stringify({ messages: s.messages, generation: s.generation_config }, null, 2)}
              </pre>
            </details>
          )}
          <details className="source-metadata text-[11px] wrap-anywhere text-muted-foreground my-4.5 mx-0">
            <summary>Exact pipeline settings</summary>
            <pre className="rag-source-text">{JSON.stringify(s.pipeline_execution, null, 2)}</pre>
          </details>
          <details className="source-metadata text-[11px] wrap-anywhere text-muted-foreground my-4.5 mx-0">
            <summary>Run identity</summary>
            <p>Run {run.id}</p>
            {run.pipeline_version_id && <p>Pipeline version {run.pipeline_version_id}</p>}
          </details>
        </>
      )}
    </section>
  );
}
