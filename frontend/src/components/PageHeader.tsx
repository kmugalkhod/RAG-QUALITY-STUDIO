import type { ReactNode } from 'react';

import { cn } from '../lib/utils';

// A page title, one line of meta and at most one primary action (spec 0002). On phones the
// action drops below the title at full width.
export function PageHeader({
  title,
  meta,
  action,
  headingLevel = 'h1',
  className,
}: {
  title: ReactNode;
  meta?: ReactNode;
  action?: ReactNode;
  headingLevel?: 'h1' | 'h2';
  className?: string;
}) {
  const Heading = headingLevel;
  return (
    <header
      data-slot="page-header"
      className={cn('flex flex-col gap-4 md:flex-row md:items-end md:justify-between', className)}
    >
      <div className="flex min-w-0 flex-col gap-1">
        <Heading className="text-lg font-semibold text-foreground">{title}</Heading>
        {meta ? <p className="text-xs text-foreground-muted">{meta}</p> : null}
      </div>
      {action ? <div className="flex shrink-0 items-center max-md:*:w-full">{action}</div> : null}
    </header>
  );
}
