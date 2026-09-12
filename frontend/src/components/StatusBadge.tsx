import { Badge } from './ui/badge';
import { cn } from '../lib/utils';

const tones: Record<string, string> = {
  succeeded: 'border-transparent bg-emerald-950 text-emerald-300',
  configured: 'border-transparent bg-emerald-950 text-emerald-300',
  running: 'border-transparent bg-amber-950 text-amber-300',
  queued: 'border-transparent bg-amber-950 text-amber-300',
  failed: 'border-transparent bg-red-950 text-red-300',
  unavailable: 'border-transparent bg-red-950 text-red-300',
  cancelled: 'border-transparent bg-zinc-800 text-zinc-300',
  uploaded: 'border-transparent bg-zinc-800 text-zinc-300',
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
      className={cn('rounded-md px-2 py-0.5 text-[11px] capitalize', tones[status], className)}
    >
      {children ?? status}
    </Badge>
  );
}
