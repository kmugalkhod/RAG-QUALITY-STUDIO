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

export function ComparisonSummary({ run }: { run: Detail }) {
  const selected = run.snapshot.evaluator.metrics;
  return (
    <>
      <p>
        Dataset: {run.snapshot.dataset.name} · v{run.snapshot.dataset.version}. Evaluator:{' '}
        {run.snapshot.evaluator.model} · RAGAS {run.snapshot.evaluator.ragas_version}. Scores
        require human review.
      </p>
      <div className="candidate-columns">
        {run.snapshot.candidates.map((version, index) => (
          <section key={version.id}>
            <h2>Candidate {index ? 'B' : 'A'}</h2>
            <Configuration version={version} />
          </section>
        ))}
      </div>
      {run.snapshot.candidates.length === 2 &&
        run.snapshot.candidates[0].index_id !== run.snapshot.candidates[1].index_id && (
          <p className="index-difference">
            Candidates use different indexed source versions. Inspect evidence before attributing
            differences to pipeline settings.
          </p>
        )}
      <section className="experiment-section">
        <h2>Candidate summaries</h2>
        <p>Means include successful scores only. Counts expose excluded and pending items.</p>
        <div className="experiment-table" tabIndex={0} aria-label="Candidate summaries">
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
                  <TableHead>{metricLabel[metric]}</TableHead>
                  {run.summary.candidates.map((summary) => {
                    const value = summary.metrics[metric];
                    return (
                      <TableCell key={summary.candidate}>
                        <strong>{number(value.mean)}</strong> · n={value.scored}/{summary.total}
                        <small>
                          {value.failed} failed · {value.skipped} skipped · {value.unavailable}{' '}
                          unavailable · {value.pending} pending
                        </small>
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
              <TableRow>
                <TableHead>Query latency</TableHead>
                {run.summary.candidates.map((summary) => (
                  <TableCell key={summary.candidate}>
                    {number(summary.query_latency_ms.mean)} ms · n={summary.query_latency_ms.count}
                  </TableCell>
                ))}
              </TableRow>
              <TableRow>
                <TableHead>Query tokens</TableHead>
                {run.summary.candidates.map((summary) => (
                  <TableCell key={summary.candidate}>
                    {number(summary.query_tokens.known_sum, 0)}
                    <small>
                      Known for {summary.query_tokens.known_count}/{summary.query_tokens.total}{' '}
                      queries
                    </small>
                  </TableCell>
                ))}
              </TableRow>
              <TableRow>
                <TableHead>Generation cost</TableHead>
                {run.summary.candidates.map((summary) => (
                  <TableCell key={summary.candidate}>
                    {money(summary.generation_cost_usd.known_sum)}
                    <small>
                      Known for {summary.generation_cost_usd.known_count}/{summary.total} queries
                    </small>
                  </TableCell>
                ))}
              </TableRow>
              <TableRow>
                <TableHead>Evaluation cost</TableHead>
                {run.summary.candidates.map((summary) => (
                  <TableCell key={summary.candidate}>
                    {money(summary.evaluation_cost_usd.known_sum)}
                    <small>
                      Known for {summary.evaluation_cost_usd.known_count}/
                      {summary.evaluation_cost_usd.total} metric results
                    </small>
                  </TableCell>
                ))}
              </TableRow>
              <TableRow>
                <TableHead>Failed / skipped</TableHead>
                {run.summary.candidates.map((summary) => (
                  <TableCell key={summary.candidate}>
                    {summary.generation_failures} / {summary.skipped}
                  </TableCell>
                ))}
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </section>
      {run.snapshot.candidates.length === 2 && (
        <section className="experiment-section">
          <h2>Paired comparison</h2>
          <p>Only questions scored for both candidates contribute to each difference.</p>
          <div className="experiment-table" tabIndex={0} aria-label="Paired comparison">
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
                      <TableHead>{metricLabel[metric]}</TableHead>
                      <TableCell>{pair.count}</TableCell>
                      <TableCell>{number(pair.a_mean)}</TableCell>
                      <TableCell>{number(pair.b_mean)}</TableCell>
                      <TableCell>{difference}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </section>
      )}
    </>
  );
}
