import { useEffect, useState } from 'react';
import { AnswerText } from '../../../components/AnswerText';
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
      <section className="experiment-section">
        <h2>Per-question comparison</h2>
        <div className="experiment-table" tabIndex={0} aria-label="Per-question comparison">
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
                <TableRow key={ordinal}>
                  <TableHead>
                    <Button
                      variant="link"
                      className="h-auto whitespace-normal p-0 text-left"
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
                      <TableCell key={candidate.id}>
                        {item.output.status === 'insufficient_evidence'
                          ? 'Insufficient evidence'
                          : readable(item.status)}
                        <small>
                          {selectedMetrics
                            .map(
                              (metric) =>
                                `${metricLabel[metric]}: ${item.metrics[metric]?.status === 'succeeded' ? number(item.metrics[metric]?.value) : readable(item.metrics[metric]?.reason || item.metrics[metric]?.status || 'pending')}`,
                            )
                            .join(' · ')}
                        </small>
                        <small>
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
      </section>
      {selectedQuestion !== undefined && (
        <section
          id="experiment-evidence"
          tabIndex={-1}
          className="experiment-section evidence-comparison"
          aria-label="Question evidence"
        >
          <div className="experiment-heading">
            <h2>{run.snapshot.dataset.rows[selectedQuestion].question}</h2>
            <Button variant="outline" onClick={() => setSelectedQuestion(undefined)}>
              Close evidence
            </Button>
          </div>
          <p>
            Reference:{' '}
            {run.snapshot.dataset.rows[selectedQuestion].reference_answer || 'Unavailable'}
          </p>
          <div className="candidate-columns">
            {run.snapshot.candidates.map((candidate, candidateIndex) => {
              const item = run.items.find(
                (value) => value.ordinal === selectedQuestion && value.candidate === candidateIndex,
              )!;
              return (
                <article key={candidate.id}>
                  <h3>Candidate {candidateIndex ? 'B' : 'A'}</h3>
                  <AnswerText text={item.output.answer || item.error || 'No answer available.'} />
                  <p>Query run: {item.query_run_id || 'Not started'}</p>
                  {item.output.snapshot?.evidence?.map((evidence) => (
                    <details key={evidence.label} open>
                      <summary>
                        {evidence.label} · {evidence.filename} · rank {evidence.rank}
                      </summary>
                      <p className="answer-text whitespace-pre-wrap">{evidence.text}</p>
                      <small>
                        Source {evidence.document_id} · page {evidence.page_number ?? 'n/a'}
                      </small>
                    </details>
                  ))}
                  {selectedMetrics.map((metric) => (
                    <details key={metric}>
                      <summary>
                        {metricLabel[metric]} · {item.metrics[metric]?.status || 'pending'}
                      </summary>
                      <p>{readable(item.metrics[metric]?.reason || '')}</p>
                      <pre>
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
                    </details>
                  ))}
                </article>
              );
            })}
          </div>
        </section>
      )}
    </>
  );
}
