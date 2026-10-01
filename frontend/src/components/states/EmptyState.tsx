import type { ReactNode } from 'react';

import { cn } from '../../lib/utils';

// Nothing to show yet, with one action that fixes it (spec 0002, AC-10).
export function EmptyState({
  icon,
  title,
  description,
  action,
  headingLevel,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  /** Render the title as a heading when the empty state stands in for a section. */
  headingLevel?: 'h2' | 'h3';
  className?: string;
}) {
  const Title = headingLevel ?? 'p';
  return (
    <div
      data-testid="state-empty"
      className={cn(
        'flex flex-col items-center gap-2 rounded-card border border-border bg-surface p-8 text-center',
        className,
      )}
    >
      {icon ? (
        <span aria-hidden="true" className="text-foreground-subtle [&_svg]:size-(--icon-lg)">
          {icon}
        </span>
      ) : null}
      <Title className="text-base font-semibold text-foreground">{title}</Title>
      {description ? (
        <p className="max-w-panel text-sm text-foreground-muted">{description}</p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
