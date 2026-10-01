import { useEffect, useState, type ReactNode } from 'react';
import { ChevronRight, X } from 'lucide-react';
import { AnswerText } from '../../../components/AnswerText';
import { CARD, PRE, SUMMARY } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../../components/ui/table';
import { money, number, readable } from '../format';
import { type Detail, metricLabel } from '../model';
import { docsHref } from '../../../lib/docs';
import { Section, TABLE_REGION } from './parts';

const DETAIL = 'mt-1 block text-xs text-foreground-muted';

function Disclosure({
  summary,
  open,
  children,
}: {
  summary: ReactNode;
  open?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="group border-t border-border" open={open}>
      <summary className={SUMMARY}>
        <ChevronRight
          aria-hidden="true"
          className="transition-transform duration-(--transition-fast) group-open:rotate-90"
        />
        <span className="min-w-0 wrap-anywhere">{summary}</span>
      </summary>
      <div className="flex flex-col gap-2 pb-3 text-sm">{children}</div>
    </details>
  );
}

export function QuestionComparison({ run }: { run: Detail }) {
  const [selectedQuestion, setSelectedQuestion] = useState<number>();
  const selectedMetrics = run.snapshot.evaluator.metrics;
  useEffect(() => {
    if (selectedQuestion !== undefined) {
      document.getElementById('experiment-evidence')?.focus();
    }
  }, [selectedQuestion]);

  return (
    <>
      <Section
        id="question-comparison-title"
        title="Per-question comparison"
        description="Select a question to compare both answers and the evidence behind them."
        action={
          <a
            className="text-sm text-accent hover:underline"
            href={docsHref('experiments/interpret')}
            target="_blank"
            rel="noopener noreferrer"
          >
            Interpret and improve results
          </a>
        }
      >
        <div className={TABLE_REGION} tabIndex={0} aria-label="Per-question comparison">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Question</TableHead>
                {run.snapshot.candidates.map((candidate, index) => (
                  <TableHead key={candidate.id}>Candidate {index ? 'B' : 'A'}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {run.snapshot.dataset.rows.map((row, ordinal) => (
                <TableRow
                  key={ordinal}
                  data-state={ordinal === selectedQuestion ? 'selected' : undefined}
                >
                  <TableHead scope="row" className="h-row py-2 align-top whitespace-normal">
                    <Button
                      variant="link"
                      className="h-auto min-h-row justify-start px-0 text-left whitespace-normal pointer-coarse:h-auto"
                      aria-controls={
                        ordinal === selectedQuestion ? 'experiment-evidence' : undefined
                      }
                      onClick={() => setSelectedQuestion(ordinal)}
                    >
                      {row.question}
                    </Button>
                  </TableHead>
                  {run.snapshot.candidates.map((candidate, candidateIndex) => {
                    const item = run.items.find(
                      (value) => value.ordinal === ordinal && value.candidate === candidateIndex,
                    )!;
                    return (
                      <TableCell key={candidate.id} className="py-3 align-top whitespace-normal">
                        <span className="text-foreground">
                          {item.output.status === 'insufficient_evidence'
                            ? 'Insufficient evidence'
                            : readable(item.status)}
                        </span>
                        <small className={DETAIL}>
                          {selectedMetrics
                            .map(
                              (metric) =>
                                `${metricLabel[metric]}: ${item.metrics[metric]?.status === 'succeeded' ? number(item.metrics[metric]?.value) : readable(item.metrics[metric]?.reason || item.metrics[metric]?.status || 'pending')}`,
                            )
                            .join(' · ')}
                        </small>
                        <small className={`${DETAIL} tabular-nums`}>
                          {number(item.output.snapshot?.total_ms)} ms ·{' '}
                          {number(item.output.snapshot?.usage?.total_tokens, 0)} tokens · generation{' '}
                          {money(item.output.snapshot?.cost_usd)}
                        </small>
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Section>
      {selectedQuestion !== undefined && (
        <section
          id="experiment-evidence"
          tabIndex={-1}
          className={`${CARD} flex flex-col gap-4 p-4 outline-none focus-visible:outline-2 focus-visible:outline-accent md:p-6`}
          aria-label="Question evidence"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex min-w-0 flex-col gap-1">
              <h2 className="text-base font-semibold text-foreground wrap-anywhere">
                {run.snapshot.dataset.rows[selectedQuestion].question}
              </h2>
              <p className="text-sm text-foreground-muted wrap-anywhere">
                Reference:{' '}
                {run.snapshot.dataset.rows[selectedQuestion].reference_answer || 'Unavailable'}
              </p>
            </div>
            <Button
              variant="ghost"
              icon
              aria-label="Close evidence"
              className="shrink-0"
              onClick={() => setSelectedQuestion(undefined)}
            >
              <X aria-hidden="true" />
            </Button>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {run.snapshot.candidates.map((candidate, candidateIndex) => {
              const item = run.items.find(
                (value) => value.ordinal === selectedQuestion && value.candidate === candidateIndex,
              )!;
              return (
                <article
                  key={candidate.id}
                  className="flex min-w-0 flex-col gap-3 rounded-card border border-border bg-background p-4"
                >
                  <h3 className="text-sm font-semibold text-foreground">
                    Candidate {candidateIndex ? 'B' : 'A'}
                  </h3>
                  <div className="text-sm text-foreground">
                    <AnswerText text={item.output.answer || item.error || 'No answer available.'} />
                  </div>
                  <p className="text-xs text-foreground-muted wrap-anywhere">
                    Query run: {item.query_run_id || 'Not started'}
                  </p>
                  <div className="flex flex-col">
                    {item.output.snapshot?.evidence?.map((evidence) => (
                      <Disclosure
                        key={evidence.label}
                        open
                        summary={`${evidence.label} · ${evidence.filename} · rank ${evidence.rank}`}
                      >
                        <p className="text-foreground whitespace-pre-wrap wrap-anywhere">
                          {evidence.text}
                        </p>
                        <small className="text-xs text-foreground-muted wrap-anywhere">
                          Source {evidence.document_id} · page {evidence.page_number ?? 'n/a'}
                        </small>
                      </Disclosure>
                    ))}
                    {selectedMetrics.map((metric) => (
                      <Disclosure
                        key={metric}
                        summary={`${metricLabel[metric]} · ${item.metrics[metric]?.status || 'pending'}`}
                      >
                        <p className="text-foreground-muted">
                          {readable(item.metrics[metric]?.reason || '')}
                        </p>
                        <pre className={PRE}>
                          {JSON.stringify(
                            item.metrics[metric]?.calls?.map((call) => ({
                              model: call.model,
                              explanation: call.structured_output,
                              usage: call.usage,
                            })) || [],
                            null,
                            2,
                          )}
                        </pre>
                      </Disclosure>
                    ))}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      )}
    </>
  );
}
