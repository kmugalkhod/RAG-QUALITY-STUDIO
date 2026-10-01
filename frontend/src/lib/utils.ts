import { createCn } from 'cn/config';

// Teach the class merger the approved design keys (spec 0002), so a call site's
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
      radius: ['control', 'card'],
      shadow: ['popover'],
    },
  },
});
