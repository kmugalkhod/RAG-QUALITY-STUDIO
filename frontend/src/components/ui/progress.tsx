'use client';

import * as React from 'react';
import { cn } from '../../lib/utils';
import { Progress as ProgressPrimitive } from 'radix-ui';

function Progress({
  className,
  value,
  ...props
}: React.ComponentProps<typeof ProgressPrimitive.Root>) {
  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      className={cn('relative h-2 w-full overflow-hidden rounded-full bg-surface-hover', className)}
      value={value}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        className="h-full w-(--progress) bg-accent-fill transition-[width] duration-(--transition-fast)"
        style={{ '--progress': `${value ?? 0}%` } as React.CSSProperties}
      />
    </ProgressPrimitive.Root>
  );
}

export { Progress };
