import { clerkElements } from '../../src/app/clerkAppearance';

// Clerk's unlayered styles outrank Tailwind utilities, and it colors links with colorPrimary
// (--accent-fill), which fails text contrast in the dark theme (spec 0002, AC-2 and AC-8).
describe('clerkElements', () => {
  it('uses style objects, never utility classes that Clerk would override', () => {
    for (const value of Object.values(clerkElements)) {
      expect(typeof value).toBe('object');
    }
  });

  it('gives every text link the text accent', () => {
    for (const key of [
      'footerActionLink',
      'formFieldAction',
      'formResendCodeLink',
      'identityPreviewEditButton',
      'headerBackLink',
      'backLink',
    ] as const) {
      expect(clerkElements[key]).toEqual({ color: 'var(--accent)' });
    }
  });

  it('outlines cards and popovers with the hairline border and popover shadow', () => {
    for (const box of [clerkElements.cardBox, clerkElements.popoverBox]) {
      expect(box).toEqual({
        border: '1px solid var(--border)',
        boxShadow: 'var(--shadow-popover)',
      });
    }
  });
});
