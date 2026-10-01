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
      className="flex items-center justify-end gap-2 text-xs text-foreground-muted"
      aria-label={label}
    >
      <Button
        variant="outline"
        size="sm"
        disabled={busy || !offset}
        onClick={() => onChange(Math.max(0, offset - pageSize))}
      >
        {previousLabel}
      </Button>
      <span className="tabular-nums">Page {Math.floor(offset / pageSize) + 1}</span>
      <Button
        variant="outline"
        size="sm"
        disabled={busy || offset + pageSize >= total}
        onClick={() => onChange(offset + pageSize)}
      >
        {nextLabel}
      </Button>
    </nav>
  ) : null;
}
