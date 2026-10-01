import { ArrowRight } from 'lucide-react';
import { ErrorState } from '../../../components/states/ErrorState';
import { LoadingState } from '../../../components/states/LoadingState';
import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import type { StageResult, StageState } from '../stages';

const BADGE_STATUS: Record<StageState, string> = {
  empty: 'uploaded',
  'in-progress': 'running',
  ready: 'succeeded',
};

// One step of the Overview strip (spec 0002, AC-6): title, status, counts and one action.
export function StageCard({
  step,
  title,
  description,
  result,
  actionLabel,
  href,
  primary,
  onRetry,
}: {
  step: number;
  title: string;
  description: string;
  result: StageResult;
  actionLabel: string;
  href: string;
  primary: boolean;
  onRetry: () => void;
}) {
  const titleId = `stage-${step}-title`;
  return (
    <li
      aria-labelledby={titleId}
      className="flex min-w-0 flex-col gap-4 rounded-card border border-border bg-surface p-6"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <p className="text-xs text-foreground-muted">Step {step}</p>
          <h3 id={titleId} className="text-base font-semibold text-foreground">
            {title}
          </h3>
        </div>
        {result.status === 'loaded' ? (
          <StatusBadge status={BADGE_STATUS[result.summary.state]}>
            {result.summary.status}
          </StatusBadge>
        ) : null}
      </div>
      <p className="text-sm text-foreground-muted">{description}</p>
      {result.status === 'loading' ? (
        <LoadingState label={`Loading ${title.toLowerCase()} status…`} rows={1} />
      ) : result.status === 'failed' ? (
        <ErrorState
          className="p-4"
          title="Could not load counts"
          message={result.message}
          onRetry={onRetry}
        />
      ) : (
        <>
          <p className="text-sm font-medium text-foreground tabular-nums">
            {result.summary.counts}
          </p>
          <Button
            asChild
            variant={primary ? 'primary' : 'secondary'}
            className="mt-auto w-full md:w-auto md:self-start"
          >
            <a href={href}>
              {actionLabel}
              <ArrowRight aria-hidden="true" />
            </a>
          </Button>
        </>
      )}
    </li>
  );
}
