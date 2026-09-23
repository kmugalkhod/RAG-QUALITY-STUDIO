import { Badge } from './ui/badge';
import { cn } from '../lib/utils';

const tones: Record<string, string> = {
  succeeded: 'status-success',
  configured: 'status-success',
  running: 'status-warning',
  queued: 'status-warning',
  failed: 'status-failure',
  unavailable: 'status-failure',
  cancelled: 'status-neutral',
  uploaded: 'status-neutral',
};

export function StatusBadge({
  status,
  children,
  className,
}: {
  status: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <Badge
      variant="outline"
      className={cn(
        'status-badge rounded-md px-2 py-0.5 text-xs',
        !children && 'capitalize',
        tones[status],
        className,
      )}
    >
      {children ?? status}
    </Badge>
  );
}
