import type { ReactNode } from 'react';
import { CARD } from '../../../components/parts';
import { cn } from '../../../lib/utils';

// Experiments building blocks on the spec 0002 tokens and grid.

/** A labeled table region that scrolls on its own, never the page (spec 0002 layout rules). */
export const TABLE_REGION =
  'max-h-panel overflow-auto overscroll-contain rounded-card border border-border bg-surface outline-none focus-visible:outline-2 focus-visible:outline-accent';

/** A numbered step in the experiment setup. */
export function StageNumber({ children }: { children: ReactNode }) {
  return (
    <span
      aria-hidden="true"
      className="flex size-6 shrink-0 items-center justify-center rounded-full border border-border-strong text-xs font-medium text-foreground tabular-nums"
    >
      {children}
    </span>
  );
}

/** A titled card section that becomes a named region for assistive technology. */
export function Section({
  id,
  title,
  description,
  action,
  children,
  className,
}: {
  id: string;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-labelledby={id}
      className={cn(CARD, 'flex min-w-0 flex-col gap-4 p-4 md:p-6', className)}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 id={id} className="text-base font-semibold text-foreground">
            {title}
          </h2>
          {description ? <p className="text-sm text-foreground-muted">{description}</p> : null}
        </div>
        {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
      </div>
      {children}
    </section>
  );
}
