import { useMemo } from 'react';
import { useTheme } from './useTheme';

// Clerk renders its own components, so it gets the theme through appearance variables built
// from the live tokens (spec 0002, AC-8). Rebuilt whenever the theme changes.
export function clerkVariables() {
  const styles = getComputedStyle(document.documentElement);
  const token = (name: string) => styles.getPropertyValue(name).trim() || undefined;
  // Every color Clerk's shadcn theme reads, so it needs no shadcn variable names of its own.
  return {
    colorPrimary: token('--accent-fill'),
    colorPrimaryForeground: token('--accent-foreground'),
    colorBackground: token('--surface'),
    colorForeground: token('--foreground'),
    colorNeutral: token('--foreground'),
    colorBorder: token('--border-strong'),
    colorInput: token('--surface'),
    colorInputForeground: token('--foreground'),
    colorMuted: token('--surface-hover'),
    colorMutedForeground: token('--foreground-muted'),
    colorDanger: token('--danger'),
    colorRing: token('--accent'),
    colorModalBackdrop: token('--overlay'),
  };
}

// Clerk's styles are unlayered, so they outrank Tailwind's layered utilities; overrides are
// style objects on the live tokens instead of classes.
const surfaceBox = { border: '1px solid var(--border)', boxShadow: 'var(--shadow-popover)' };
// Clerk paints text links with colorPrimary, a fill that fails text contrast in the dark
// theme, so links take the text accent.
const link = { color: 'var(--accent)' };

export const clerkElements = {
  cardBox: surfaceBox,
  popoverBox: surfaceBox,
  footerActionLink: link,
  formFieldAction: link,
  formResendCodeLink: link,
  identityPreviewEditButton: link,
  headerBackLink: link,
  backLink: link,
  // The switcher trigger defaults to Clerk's 13px; the app's control text is 14px.
  organizationPreviewMainIdentifier__organizationSwitcherTrigger: {
    fontSize: 'var(--text-sm)',
    lineHeight: 'var(--text-sm--line-height)',
  },
  // Generated organization logos are violet, which the palette never uses.
  organizationPreviewAvatarBox: { filter: 'grayscale(1)' },
};

export function useClerkVariables() {
  const { theme } = useTheme();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- the theme changes the tokens read here
  return useMemo(() => clerkVariables(), [theme]);
}
