'use client';

import * as React from 'react';
import { cn } from '../../lib/utils';
import { CheckIcon } from 'lucide-react';
import { Checkbox as CheckboxPrimitive } from 'radix-ui';

function Checkbox({ className, ...props }: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        // The 16px box gets a 40px hit area, 48px on touch, through an invisible ::after.
        'peer relative size-4 shrink-0 rounded-control border border-border-strong bg-surface outline-none after:absolute after:-inset-3 pointer-coarse:after:-inset-4 disabled:cursor-not-allowed disabled:opacity-(--disabled-opacity) data-[state=checked]:border-accent-fill data-[state=checked]:bg-accent-fill data-[state=checked]:text-accent-foreground',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent aria-invalid:border-danger',
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="grid place-content-center text-current transition-none"
      >
        <CheckIcon className="size-3" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export { Checkbox };
