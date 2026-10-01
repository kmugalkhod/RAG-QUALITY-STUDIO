import * as React from 'react';
import { cn } from '../../lib/utils';

function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        'flex field-sizing-content min-h-16 w-full rounded-control border border-border-strong bg-surface px-2 py-2 text-base text-foreground outline-none placeholder:text-foreground-muted disabled:cursor-not-allowed disabled:opacity-(--disabled-opacity) md:text-sm',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent aria-invalid:border-danger',
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
