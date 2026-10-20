import { createCn } from 'cn/config';

// Teach the class merger the approved design keys (specs 0002 and 0003), so a call site's
// `h-control-lg` replaces a primitive's `h-control-md` instead of both applying.
export const cn = createCn({
  extend: {
    theme: {
      spacing: [
        'control-sm',
        'control-md',
        'control-lg',
        'row-header',
        'row',
        'tabbar',
        'node-h',
        'node-legacy',
        'sidebar',
        'node',
        'panel',
      ],
      radius: ['control', 'card', 'shell'],
      shadow: ['popover'],
    },
  },
});

/** A count with its noun in the singular for one: `1 chunk`, `2 chunks` (spec 0015 U5). */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count.toLocaleString('en-US')} ${count === 1 ? one : many}`;
}
