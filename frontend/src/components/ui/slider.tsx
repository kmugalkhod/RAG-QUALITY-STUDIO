import * as React from 'react';
import { Slider as SliderPrimitive } from 'radix-ui';

import { cn } from '../../lib/utils';

// Generated with `npx --yes shadcn@4.21.0 add slider`, then normalized to the spec 0003
// tokens: a 4px track, an accent range, a 12px thumb with a 40px hit area (48px on touch)
// and the shared focus ring. `ticks` draws evenly spaced dots under the thumb. The
// accessible name goes on the thumb, the element that has the slider role.
function Slider({
  className,
  defaultValue,
  value,
  min = 0,
  max = 100,
  ticks = 0,
  'aria-label': label,
  ...props
}: React.ComponentProps<typeof SliderPrimitive.Root> & { ticks?: number }) {
  const values = React.useMemo(
    () => (Array.isArray(value) ? value : Array.isArray(defaultValue) ? defaultValue : [min]),
    [value, defaultValue, min],
  );

  return (
    <SliderPrimitive.Root
      data-slot="slider"
      defaultValue={defaultValue}
      value={value}
      min={min}
      max={max}
      className={cn(
        'relative flex h-control-sm w-full touch-none items-center select-none pointer-coarse:h-control-lg data-[disabled]:opacity-(--disabled-opacity)',
        className,
      )}
      {...props}
    >
      <SliderPrimitive.Track
        data-slot="slider-track"
        className="relative h-1 w-full grow overflow-hidden rounded-full bg-track"
      >
        <SliderPrimitive.Range data-slot="slider-range" className="absolute h-full bg-accent" />
      </SliderPrimitive.Track>
      {ticks > 1 && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-1 flex justify-between"
        >
          {Array.from({ length: ticks }, (_, index) => (
            <span key={index} className="size-(--slider-tick) rounded-full bg-foreground-subtle" />
          ))}
        </span>
      )}
      {values.map((_, index) => (
        <SliderPrimitive.Thumb
          data-slot="slider-thumb"
          key={index}
          aria-label={label}
          className="relative z-10 block size-3 shrink-0 rounded-full border-2 border-accent bg-surface outline-none after:absolute after:-inset-3 pointer-coarse:after:-inset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        />
      ))}
    </SliderPrimitive.Root>
  );
}

export { Slider };
