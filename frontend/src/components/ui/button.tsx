import * as React from 'react';
import { cva } from 'class-variance-authority';
import { Loader2 } from 'lucide-react';
import { Slot } from 'radix-ui';

import { cn } from '../../lib/utils';

// Spec 0002, AC-3 and AC-4. Disabled buttons use aria-disabled and stay focusable;
// pressed is CSS :active; touch sizing is CSS (pointer: coarse), never JavaScript.
const buttonVariants = cva(
  "relative inline-flex shrink-0 items-center justify-center rounded-control text-sm font-medium whitespace-nowrap select-none transition-[background-color,border-color,color,transform] duration-(--transition-press) outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent aria-disabled:cursor-default aria-disabled:opacity-(--disabled-opacity) aria-busy:cursor-progress motion-safe:not-aria-disabled:not-aria-busy:active:translate-y-px aria-invalid:border-danger [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        primary:
          'bg-accent-fill text-accent-foreground not-aria-disabled:hover:bg-accent-fill-hover not-aria-disabled:active:bg-accent-fill-pressed',
        secondary:
          'bg-surface-hover text-foreground not-aria-disabled:hover:bg-(--surface-hover-fill-hover) not-aria-disabled:active:bg-(--surface-hover-fill-pressed)',
        outline:
          'border border-border-strong bg-surface text-foreground not-aria-disabled:hover:bg-(--surface-fill-hover) not-aria-disabled:active:bg-(--surface-fill-pressed)',
        ghost:
          'bg-transparent text-foreground not-aria-disabled:hover:bg-surface-hover not-aria-disabled:active:bg-(--surface-hover-fill-hover)',
        destructive:
          'bg-danger-fill text-accent-foreground not-aria-disabled:hover:bg-(--danger-fill-hover) not-aria-disabled:active:bg-(--danger-fill-pressed)',
        link: 'text-accent underline-offset-4 not-aria-disabled:hover:underline',
      },
      size: {
        sm: 'h-control-sm gap-1 px-2 pointer-coarse:h-control-lg',
        md: 'h-control-md gap-2 px-4 pointer-coarse:h-control-lg',
        lg: "h-control-lg gap-2 px-6 [&_svg:not([class*='size-'])]:size-(--icon-lg)",
      },
      icon: {
        true: 'px-0',
        false: '',
      },
    },
    compoundVariants: [
      { icon: true, size: 'sm', className: 'w-control-sm pointer-coarse:w-control-lg' },
      { icon: true, size: 'md', className: 'w-control-md pointer-coarse:w-control-lg' },
      { icon: true, size: 'lg', className: 'w-control-lg' },
    ],
    defaultVariants: {
      variant: 'primary',
      size: 'md',
      icon: false,
    },
  },
);

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'destructive' | 'link';
type ButtonSize = 'sm' | 'md' | 'lg';
type ButtonProps = React.ComponentProps<'button'> & {
  variant?: ButtonVariant | null;
  size?: ButtonSize | null;
  /** Square at the size height. */
  icon?: boolean;
  /** Blocks clicks, keeps the width and shows a centered spinner. */
  loading?: boolean;
  asChild?: boolean;
};

// A short haptic tick for primary and destructive presses on touch screens (AC-4).
// Browsers ignore it before the first user activation, so the first tap may be silent.
function vibrateOnPress() {
  try {
    if (typeof navigator.vibrate === 'function' && window.matchMedia('(pointer: coarse)').matches) {
      navigator.vibrate(10);
    }
  } catch {
    // Vibration is a nicety; an unsupported or blocked call changes nothing.
  }
}

function Button({
  className,
  variant: variantProp,
  size: sizeProp,
  icon = false,
  loading = false,
  asChild = false,
  disabled = false,
  type,
  children,
  onClick,
  onPointerDown,
  ...props
}: ButtonProps) {
  const variant: ButtonVariant = variantProp ?? 'primary';
  const size: ButtonSize = sizeProp ?? 'md';
  const blocked = disabled || loading;

  function handleClick(event: React.MouseEvent<HTMLButtonElement>) {
    if (blocked) {
      // Stops navigation and form submission, including Enter in a field of the form.
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    onClick?.(event);
  }

  function handlePointerDown(event: React.PointerEvent<HTMLButtonElement>) {
    if (!blocked && (variant === 'primary' || variant === 'destructive')) {
      vibrateOnPress();
    }
    onPointerDown?.(event);
  }

  let content = children;
  if (asChild && disabled && React.isValidElement<Record<string, unknown>>(children)) {
    // A disabled link keeps focus but loses its destination and its own click handler.
    content = React.cloneElement(children, {
      href: undefined,
      onClick: undefined,
      role: 'link',
      tabIndex: 0,
    });
  } else if (loading && !asChild) {
    content = (
      <>
        <span aria-hidden="true" className="invisible inline-flex items-center [gap:inherit]">
          {children}
        </span>
        <span className="sr-only">{children}</span>
        <span aria-hidden="true" className="absolute inset-0 flex items-center justify-center">
          <Loader2 className="animate-spin motion-reduce:animate-none" />
        </span>
      </>
    );
  }

  const Comp = asChild ? Slot.Root : 'button';
  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, icon }), className)}
      type={asChild ? undefined : (type ?? 'button')}
      aria-disabled={disabled || undefined}
      aria-busy={loading || undefined}
      onClick={handleClick}
      onPointerDown={handlePointerDown}
      {...props}
    >
      {content}
    </Comp>
  );
}

export { Button, buttonVariants };
export type { ButtonProps };
