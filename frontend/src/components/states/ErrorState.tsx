import type { ReactNode } from 'react';
import { CircleAlert } from 'lucide-react';

import { cn } from '../../lib/utils';
import { Button } from '../ui/button';

// A request failed. Shows the safe message and, when given, a Retry (spec 0002, AC-10).
export function ErrorState({
  title = 'Could not load this',
  message,
  onRetry,
  retrying = false,
  retryLabel = 'Retry',
  action,
  headingLevel,
  className,
}: {
  title?: string;
  message?: ReactNode;
  onRetry?: () => void;
  retrying?: boolean;
  retryLabel?: string;
  /** A second, non primary way out, such as a link back to a list. */
  action?: ReactNode;
  /** Render the title as a heading when the error replaces a whole page. */
  headingLevel?: 'h1' | 'h2';
  className?: string;
}) {
  const Title = headingLevel ?? 'p';
  return (
    <div
      role="alert"
      data-testid="state-error"
      className={cn(
        'flex flex-col items-center gap-2 rounded-card border border-border bg-surface p-8 text-center',
        className,
      )}
    >
      <Title className="flex items-center gap-2 text-base font-semibold text-danger">
        <CircleAlert aria-hidden="true" size={20} />
        {title}
      </Title>
      {message ? <p className="max-w-panel text-sm text-foreground-muted">{message}</p> : null}
      {onRetry || action ? (
        <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
          {onRetry ? (
            <Button variant="outline" loading={retrying} onClick={onRetry}>
              {retryLabel}
            </Button>
          ) : null}
          {action}
        </div>
      ) : null}
    </div>
  );
}
