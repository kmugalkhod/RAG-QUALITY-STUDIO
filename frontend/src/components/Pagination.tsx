import { Button } from './ui/button';
export function Pagination({
  offset,
  total,
  onChange,
  label,
  busy = false,
  pageSize = 20,
  previousLabel = 'Previous',
  nextLabel = 'Next',
}: {
  offset: number;
  total: number;
  onChange: (n: number) => void;
  label: string;
  busy?: boolean;
  pageSize?: number;
  previousLabel?: string;
  nextLabel?: string;
}) {
  return total > pageSize || offset > 0 ? (
    <nav
      className="pagination flex justify-end items-center gap-2 text-[11px] p-3 m-0"
      aria-label={label}
    >
      <Button
        variant="outline"
        disabled={busy || !offset}
        onClick={() => onChange(Math.max(0, offset - pageSize))}
      >
        {previousLabel}
      </Button>
      <span>Page {Math.floor(offset / pageSize) + 1}</span>
      <Button
        variant="outline"
        disabled={busy || offset + pageSize >= total}
        onClick={() => onChange(offset + pageSize)}
      >
        {nextLabel}
      </Button>
    </nav>
  ) : null;
}
