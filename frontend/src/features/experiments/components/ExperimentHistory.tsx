import { FlaskConical } from 'lucide-react';
import { StatusBadge } from '../../../components/StatusBadge';
import { EmptyState } from '../../../components/states/EmptyState';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../../components/ui/table';
import type { Experiment } from '../model';
import { TABLE_REGION } from './parts';

export function ExperimentHistory({
  projectId,
  experiments,
}: {
  projectId: string;
  experiments: Experiment[];
}) {
  return (
    <section aria-labelledby="experiment-history-title" className="flex flex-col gap-4">
      <h2 id="experiment-history-title" className="text-base font-semibold text-foreground">
        Experiment history
      </h2>
      {!experiments.length ? (
        <EmptyState
          icon={<FlaskConical />}
          title="No experiments yet"
          description="Import a dataset and select saved pipeline versions to begin."
        />
      ) : (
        <div className={TABLE_REGION} tabIndex={0} aria-label="Experiment history">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Dataset</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Completed</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {experiments.map((experiment) => (
                <TableRow key={experiment.id}>
                  <TableCell className="py-2">
                    <a
                      className="inline-flex min-h-row items-center font-medium text-accent outline-none hover:underline focus-visible:outline-2 focus-visible:outline-accent"
                      href={`#/projects/${projectId}/experiments/${experiment.id}`}
                    >
                      {experiment.name}
                    </a>
                    <span className="block text-xs text-foreground-muted">
                      {new Date(experiment.created_at).toLocaleString()}
                    </span>
                  </TableCell>
                  <TableCell>
                    {experiment.snapshot.dataset.name} · v{experiment.snapshot.dataset.version}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={experiment.status} />
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {experiment.progress} / {experiment.total}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  );
}
