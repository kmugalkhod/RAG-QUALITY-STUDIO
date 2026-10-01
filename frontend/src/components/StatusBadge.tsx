import { Badge } from './ui/badge';
import { cn } from '../lib/utils';

// Status text and a 1px border in the status color on the surface, never white text on a
// status fill, and always a text label (spec 0002).
const tones: Record<string, string> = {
  succeeded: 'border-success text-success',
  configured: 'border-success text-success',
  running: 'border-warning text-warning',
  queued: 'border-warning text-warning',
  failed: 'border-danger text-danger',
  unavailable: 'border-danger text-danger',
  cancelled: 'border-border-strong text-foreground-muted',
  uploaded: 'border-border-strong text-foreground-muted',
};

export function StatusBadge({
  status,
  children,
  className,
  ...props
}: React.ComponentProps<'span'> & {
  status: string;
}) {
  return (
    <Badge
      {...props}
      variant="outline"
      data-status={status}
      className={cn(
        'bg-surface',
        !children && 'capitalize',
        tones[status] ?? 'border-border-strong text-foreground-muted',
        className,
      )}
    >
      {children ?? status}
    </Badge>
  );
}
