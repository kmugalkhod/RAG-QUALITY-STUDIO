import { type Row } from '../model';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../../components/ui/table';
import { TABLE_REGION } from './parts';

export function Questions({ rows }: { rows: Row[] }) {
  return (
    <div className={TABLE_REGION} tabIndex={0} aria-label="Dataset questions">
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
              <TableCell className="py-3 align-top whitespace-normal">{r.question}</TableCell>
              <TableCell className="py-3 align-top whitespace-normal text-foreground-muted">
                {r.reference_answer || 'No reference — context recall unavailable'}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
