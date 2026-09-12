import { StatusBadge } from '../../../components/StatusBadge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../../components/ui/table';
import type { Experiment } from '../model';

export function ExperimentHistory({
  projectId,
  experiments,
}: {
  projectId: string;
  experiments: Experiment[];
}) {
  return (
    <section className="experiment-section mt-6 border-t border-border py-6">
      <h2>Experiment history</h2>
      {!experiments.length ? (
        <p>No experiments yet. Import a dataset and select saved pipeline versions to begin.</p>
      ) : (
        <div
          className="experiment-table my-4 max-h-120 overflow-auto"
          tabIndex={0}
          aria-label="Experiment history"
        >
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
                  <TableCell>
                    <a href={`#/projects/${projectId}/experiments/${experiment.id}`}>
                      {experiment.name}
                    </a>
                    <small>{new Date(experiment.created_at).toLocaleString()}</small>
                  </TableCell>
                  <TableCell>
                    {experiment.snapshot.dataset.name} · v{experiment.snapshot.dataset.version}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={experiment.status} />
                  </TableCell>
                  <TableCell>
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
