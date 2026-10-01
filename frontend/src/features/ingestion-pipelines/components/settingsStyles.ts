export { CHECK_ROW } from '../../../components/parts';

// Stage settings building blocks on the spec 0002 tokens and grid, shared by the source,
// clean and stage settings forms inside the ingestion settings panel.

/** The settings body: every Label stacks its text over its control with an 8px gap. */
export const FORM =
  'flex flex-col gap-6 [&_label[data-slot=label]]:mb-0 [&_label[data-slot=label]]:flex [&_label[data-slot=label]]:flex-col [&_label[data-slot=label]]:gap-2';
export const STACK = 'flex flex-col gap-4';
export const HINT = 'text-sm text-foreground-muted';
/** Two short fields side by side, one column on phones. */
export const FIELD_GRID = 'grid gap-4 md:grid-cols-2';
/** A bordered choice with a checkbox, a title and one line of detail. */
export const OPTION =
  'flex cursor-pointer items-start gap-3 rounded-control border border-border bg-background p-4 text-sm text-foreground has-data-[state=checked]:border-accent [&>[data-slot=checkbox]]:mt-1 [&>span]:flex [&>span]:min-w-0 [&>span]:flex-col [&>span]:gap-1 [&>span]:wrap-anywhere [&_small]:text-xs [&_small]:text-foreground-muted';
export const FACTS =
  'flex flex-col gap-1 text-sm text-foreground [&_dd]:mb-2 [&_dd]:wrap-anywhere [&_dt]:text-foreground-muted';
export const FIELDSET =
  'm-0 flex min-w-0 flex-col gap-2 rounded-card border border-border p-4 [&>legend]:px-1 [&>legend]:text-xs [&>legend]:font-medium [&>legend]:text-foreground-muted';
export const FIELD_ERROR = 'text-xs text-danger';
/** A disclosure section below a hairline. */
export const DETAILS = 'flex flex-col border-t border-border pt-4 [&[open]>summary]:mb-4';
