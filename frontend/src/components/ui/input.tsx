import * as React from 'react';
import { cn } from '../../lib/utils';

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        // 16px text on phones keeps iOS from zooming the page on focus.
        'h-control-md w-full min-w-0 rounded-control border border-border-strong bg-surface px-2 text-base text-foreground outline-none pointer-coarse:h-control-lg md:text-sm',
        'file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-foreground-muted disabled:cursor-not-allowed disabled:opacity-(--disabled-opacity)',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent aria-invalid:border-danger',
        className,
      )}
      {...props}
    />
  );
}

export { Input };
