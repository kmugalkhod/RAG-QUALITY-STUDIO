import * as React from 'react';
import { Popover as PopoverPrimitive } from 'radix-ui';

import { cn } from '../../lib/utils';

// Generated with `npx --yes shadcn@4.21.0 add popover`, then normalized to the spec 0002
// tokens: no enter or exit animation, a raised surface with a hairline border and the card
// radius. Unused header, title and description helpers were removed.
function Popover({ ...props }: React.ComponentProps<typeof PopoverPrimitive.Root>) {
  return <PopoverPrimitive.Root data-slot="popover" {...props} />;
}

function PopoverTrigger({ ...props }: React.ComponentProps<typeof PopoverPrimitive.Trigger>) {
  return <PopoverPrimitive.Trigger data-slot="popover-trigger" {...props} />;
}

function PopoverContent({
  className,
  align = 'center',
  sideOffset = 4,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        data-slot="popover-content"
        align={align}
        sideOffset={sideOffset}
        className={cn(
          'z-50 w-panel rounded-card border border-border bg-surface-raised p-4 text-foreground shadow-popover outline-hidden',
          className,
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
}

export { Popover, PopoverTrigger, PopoverContent };
