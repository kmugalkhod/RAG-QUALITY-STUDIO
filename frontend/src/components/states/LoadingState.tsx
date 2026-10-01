import { cn } from '../../lib/utils';
import { Skeleton } from '../ui/skeleton';

// Placeholder rows at the height of the content they stand in for (spec 0002, AC-10).
export function LoadingState({
  label = 'Loading…',
  rows = 3,
  className,
}: {
  label?: string;
  rows?: number;
  className?: string;
}) {
  return (
    <div role="status" data-testid="state-loading" className={cn('flex flex-col gap-2', className)}>
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} aria-hidden="true" className="h-row w-full" />
      ))}
    </div>
  );
}
