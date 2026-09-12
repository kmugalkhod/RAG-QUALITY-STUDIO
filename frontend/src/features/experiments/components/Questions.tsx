import { type Row } from '../model';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../../components/ui/table';

export function Questions({ rows }: { rows: Row[] }) {
  return (
    <div
      className="experiment-table max-h-120 overflow-auto my-4"
      tabIndex={0}
      aria-label="Dataset questions"
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">Question</TableHead>
            <TableHead scope="col">Reference answer</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r, i) => (
            <TableRow key={i}>
              <TableCell>{r.question}</TableCell>
              <TableCell>
                {r.reference_answer || 'No reference — context recall unavailable'}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
