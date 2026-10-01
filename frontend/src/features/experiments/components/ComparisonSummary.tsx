import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../../components/ui/table';
import type { Detail } from '../model';
import { metricLabel } from '../model';
import { money, number } from '../format';
import { Configuration } from './Configuration';
import { docsHref } from '../../../lib/docs';
import { Callout } from '../../../components/parts';
import { Section, TABLE_REGION } from './parts';

const GUIDE = 'text-sm text-accent hover:underline';
const CELL = 'py-3 align-top whitespace-normal tabular-nums';
const DETAIL = 'mt-1 block text-xs text-foreground-muted';
const ROW_HEAD = 'h-row py-3 align-top text-sm font-medium whitespace-normal text-foreground';

export function ComparisonSummary({ run }: { run: Detail }) {
  const selected = run.snapshot.evaluator.metrics;
  const snapshotIds = run.snapshot.candidates.map((candidate) => candidate.source_snapshot_id);
  const sameSnapshot =
    snapshotIds.length > 1 && snapshotIds.every((id) => id && id === snapshotIds[0]);
  return (
    <>
      <p className="text-sm text-foreground-muted">
        Dataset: {run.snapshot.dataset.name} · v{run.snapshot.dataset.version}. Evaluator:{' '}
        {run.snapshot.evaluator.model} · RAGAS {run.snapshot.evaluator.ragas_version}. Scores
        require human review.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        {run.snapshot.candidates.map((version, index) => (
          <section
            key={version.id}
            aria-labelledby={`candidate-${index}-title`}
            className="flex min-w-0 flex-col gap-2"
          >
            <h2 id={`candidate-${index}-title`} className="text-sm font-semibold text-foreground">
              Candidate {index ? 'B' : 'A'}
            </h2>
            <Configuration version={version} />
          </section>
        ))}
      </div>
      {run.snapshot.candidates.length === 2 &&
        (sameSnapshot ? (
          <Callout tone="success">
            Same source snapshot · Snapshot {run.snapshot.candidates[0].source_snapshot_number}
          </Callout>
        ) : (
          <Callout tone="warning">
            Comparison caveat: candidates use different source snapshots, or legacy lineage is
            unavailable. Content changes may affect results.
          </Callout>
        ))}
      {run.snapshot.candidates.length === 2 &&
        run.snapshot.candidates[0].index_id !== run.snapshot.candidates[1].index_id && (
          <Callout tone="warning">
            Candidates use different indexed source versions. Inspect evidence before attributing
            differences to pipeline settings.
          </Callout>
        )}
      <Section
        id="candidate-summaries-title"
        title="Candidate summaries"
        description="Means include successful scores only. Counts expose excluded and pending items."
        action={
          <a
            className={GUIDE}
            href={docsHref('experiments/metrics')}
            target="_blank"
            rel="noopener noreferrer"
          >
            Interpret metrics and costs
          </a>
        }
      >
        <div className={TABLE_REGION} tabIndex={0} aria-label="Candidate summaries">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Measurement</TableHead>
                {run.summary.candidates.map((summary) => (
                  <TableHead key={summary.candidate}>
                    Candidate {summary.candidate ? 'B' : 'A'}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {selected.map((metric) => (
                <TableRow key={metric}>
                  <TableHead scope="row" className={ROW_HEAD}>
                    {metricLabel[metric]}
                  </TableHead>
                  {run.summary.candidates.map((summary) => {
                    const value = summary.metrics[metric];
                    return (
                      <TableCell key={summary.candidate} className={CELL}>
                        <strong className="font-semibold text-foreground">
                          {number(value.mean)}
                        </strong>{' '}
                        · n={value.scored}/{summary.total}
                        <small className={DETAIL}>
                          {value.failed} failed · {value.skipped} skipped · {value.unavailable}{' '}
                          unavailable · {value.pending} pending
                        </small>
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
              <TableRow>
                <TableHead scope="row" className={ROW_HEAD}>
                  Query latency
                </TableHead>
                {run.summary.candidates.map((summary) => (
                  <TableCell key={summary.candidate} className={CELL}>
                    {number(summary.query_latency_ms.mean)} ms · n={summary.query_latency_ms.count}
                  </TableCell>
                ))}
              </TableRow>
              <TableRow>
                <TableHead scope="row" className={ROW_HEAD}>
                  Query tokens
                </TableHead>
                {run.summary.candidates.map((summary) => (
                  <TableCell key={summary.candidate} className={CELL}>
                    {number(summary.query_tokens.known_sum, 0)}
                    <small className={DETAIL}>
                      Known for {summary.query_tokens.known_count}/{summary.query_tokens.total}{' '}
                      queries
                    </small>
                  </TableCell>
                ))}
              </TableRow>
              <TableRow>
                <TableHead scope="row" className={ROW_HEAD}>
                  Generation cost
                </TableHead>
                {run.summary.candidates.map((summary) => (
                  <TableCell key={summary.candidate} className={CELL}>
                    {money(summary.generation_cost_usd.known_sum)}
                    <small className={DETAIL}>
                      Known for {summary.generation_cost_usd.known_count}/{summary.total} queries
                    </small>
                  </TableCell>
                ))}
              </TableRow>
              <TableRow>
                <TableHead scope="row" className={ROW_HEAD}>
                  Evaluation cost
                </TableHead>
                {run.summary.candidates.map((summary) => (
                  <TableCell key={summary.candidate} className={CELL}>
                    {money(summary.evaluation_cost_usd.known_sum)}
                    <small className={DETAIL}>
                      Known for {summary.evaluation_cost_usd.known_count}/
                      {summary.evaluation_cost_usd.total} metric results
                    </small>
                  </TableCell>
                ))}
              </TableRow>
              <TableRow>
                <TableHead scope="row" className={ROW_HEAD}>
                  Failed / skipped
                </TableHead>
                {run.summary.candidates.map((summary) => (
                  <TableCell key={summary.candidate} className={CELL}>
                    {summary.generation_failures} / {summary.skipped}
                  </TableCell>
                ))}
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </Section>
      {run.snapshot.candidates.length === 2 && (
        <Section
          id="paired-comparison-title"
          title="Paired comparison"
          description="Only questions scored for both candidates contribute to each difference."
          action={
            <a
              className={GUIDE}
              href={docsHref('experiments/compare')}
              target="_blank"
              rel="noopener noreferrer"
            >
              Paired comparison guide
            </a>
          }
        >
          <div className={TABLE_REGION} tabIndex={0} aria-label="Paired comparison">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Metric</TableHead>
                  <TableHead>Shared sample</TableHead>
                  <TableHead>A mean</TableHead>
                  <TableHead>B mean</TableHead>
                  <TableHead>B − A</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {selected.map((metric) => {
                  const pair = run.summary.paired[metric]!;
                  const difference =
                    pair.b_minus_a != null &&
                    pair.b_minus_a !== 0 &&
                    Math.abs(pair.b_minus_a) < 0.001
                      ? pair.b_minus_a.toExponential(2)
                      : number(pair.b_minus_a);
                  return (
                    <TableRow key={metric}>
                      <TableHead scope="row" className={ROW_HEAD}>
                        {metricLabel[metric]}
                      </TableHead>
                      <TableCell className="tabular-nums">{pair.count}</TableCell>
                      <TableCell className="tabular-nums">{number(pair.a_mean)}</TableCell>
                      <TableCell className="tabular-nums">{number(pair.b_mean)}</TableCell>
                      <TableCell className="tabular-nums">{difference}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </Section>
      )}
    </>
  );
}
