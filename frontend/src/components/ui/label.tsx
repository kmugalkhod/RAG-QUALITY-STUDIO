import * as React from 'react';
import { cn } from '../../lib/utils';
import { Label as LabelPrimitive } from 'radix-ui';

function Label({ className, ...props }: React.ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn(
        'mb-2 block text-xs font-medium text-foreground-muted select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-(--disabled-opacity) peer-disabled:cursor-not-allowed peer-disabled:opacity-(--disabled-opacity)',
        className,
      )}
      {...props}
    />
  );
}

export { Label };
