import type { ReactNode } from 'react';
import { CircleAlert, CircleCheck, Info, TriangleAlert } from 'lucide-react';

import { Button } from './ui/button';
import { cn } from '../lib/utils';

// Shared page building blocks on the spec 0002 tokens and grid.

export const CARD = 'rounded-card border border-border bg-surface';
/** A bordered list whose rows are separated by hairlines. */
export const LIST = `${CARD} flex flex-col overflow-hidden`;
export const LIST_ROW = 'border-b border-border last:border-b-0';
export const META = 'text-xs text-foreground-muted';
/** A disclosure summary with a 44px target. */
export const SUMMARY =
  'flex min-h-row items-center gap-2 rounded-control text-sm font-medium text-foreground outline-none focus-visible:outline-2 focus-visible:outline-accent [&_svg]:size-4 [&_svg]:text-foreground-subtle';
/** A selectable card row built on the ghost Button. */
export const SELECT_ROW =
  'h-auto w-full flex-col items-stretch gap-1 px-4 py-3 text-left whitespace-normal pointer-coarse:h-auto aria-pressed:bg-surface-hover';
/** Preformatted JSON or passage text, scrolling inside its own box. */
export const PRE =
  'max-h-panel overflow-auto rounded-control border border-border bg-background p-3 font-mono text-xs whitespace-pre-wrap wrap-anywhere text-foreground';
/** A checkbox beside a one line label, with a 44px row. */
export const CHECK_ROW =
  'flex min-h-row cursor-pointer items-center gap-3 text-sm text-foreground [&>span]:min-w-0';
export const LINK =
  'inline-flex min-h-row items-center text-sm text-accent outline-none hover:underline focus-visible:outline-2 focus-visible:outline-accent';

export function SectionHeading({
  id,
  title,
  description,
  action,
  level = 'h3',
  headingRef,
}: {
  id?: string;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  level?: 'h2' | 'h3';
  headingRef?: React.Ref<HTMLHeadingElement>;
}) {
  const Heading = level;
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <Heading
          id={id}
          ref={headingRef}
          tabIndex={headingRef ? -1 : undefined}
          className="flex items-center gap-2 text-base font-semibold text-foreground outline-none [&_svg]:size-4 [&_svg]:text-foreground-subtle"
        >
          {title}
        </Heading>
        {description ? <p className="text-sm text-foreground-muted">{description}</p> : null}
      </div>
      {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
    </div>
  );
}

/** A failure beside data that is still shown, with an optional Retry. */
export function InlineError({
  children,
  onRetry,
  retryLabel = 'Retry',
  className,
  id,
  tabIndex,
}: {
  children: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
  /** Set both when a screen moves focus to the error after a failed action. */
  id?: string;
  tabIndex?: number;
}) {
  return (
    <div
      id={id}
      tabIndex={tabIndex}
      role="alert"
      className={cn(
        CARD,
        'flex flex-wrap items-center justify-between gap-3 border-danger px-4 py-2 text-sm text-danger',
        className,
      )}
    >
      <p className="flex min-w-0 items-center gap-2 wrap-anywhere">
        <CircleAlert aria-hidden="true" className="size-4 shrink-0" />
        <span>{children}</span>
      </p>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          {retryLabel}
        </Button>
      ) : null}
    </div>
  );
}

/** A short confirmation line. Renders empty so screen readers keep the live region. */
export function Notice({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    <p role="status" className={cn('text-sm text-success wrap-anywhere empty:hidden', className)}>
      {children}
    </p>
  );
}

/** Label and value pairs in a responsive grid. */
export function Facts({
  items,
  className,
}: {
  items: [ReactNode, ReactNode][];
  className?: string;
}) {
  return (
    <dl className={cn('grid grid-cols-2 gap-4 md:grid-cols-4', className)}>
      {items.map(([term, value], index) => (
        <div key={index} className="flex min-w-0 flex-col gap-1">
          <dt className={META}>{term}</dt>
          <dd className="text-sm text-foreground tabular-nums wrap-anywhere">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

const CALLOUT_TONES = {
  warning: { className: 'border-warning', icon: TriangleAlert, iconClass: 'text-warning' },
  success: { className: 'border-success', icon: CircleCheck, iconClass: 'text-success' },
  info: { className: 'border-border-strong', icon: Info, iconClass: 'text-foreground-muted' },
};

/** A caveat or confirmation beside the data it describes. The text is always the label. */
export function Callout({
  tone = 'info',
  title,
  children,
  role,
  className,
  ...props
}: Omit<React.ComponentProps<'div'>, 'title' | 'role'> & {
  tone?: keyof typeof CALLOUT_TONES;
  title?: ReactNode;
  children?: ReactNode;
  role?: 'status' | 'alert' | 'note';
  className?: string;
}) {
  const { className: toneClass, icon: Icon, iconClass } = CALLOUT_TONES[tone];
  return (
    <div
      {...props}
      role={role}
      className={cn(CARD, 'flex items-start gap-3 px-4 py-3 text-sm', toneClass, className)}
    >
      <span className="flex size-(--icon-lg) shrink-0 items-center justify-center">
        <Icon aria-hidden="true" className={cn('size-4', iconClass)} />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-2 wrap-anywhere">
        {title ? <p className="font-medium text-foreground">{title}</p> : null}
        {children ? (
          <div className="flex flex-col gap-2 text-foreground-muted">{children}</div>
        ) : null}
      </div>
    </div>
  );
}
