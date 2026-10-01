import type { ReactNode } from 'react';
import { X } from 'lucide-react';
import { Button } from '../../../components/ui/button';

// Settings, history and evidence share one 320px panel on desktop; below 1152px it stacks under
// the conversation at full width (spec 0002 layout rules). Each view scrolls inside the panel.
export function PlaygroundSidePanel({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <aside
      id="playground-settings"
      className="flex min-w-0 flex-col overflow-hidden rounded-card border border-border bg-surface desktop:min-h-0 desktop:w-panel desktop:shrink-0"
      hidden={!open}
      aria-labelledby="playground-panel-title"
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          onClose();
        }
      }}
    >
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border py-1 pr-1 pl-4">
        <h2
          id="playground-panel-title"
          className="min-w-0 truncate text-base font-semibold text-foreground"
        >
          {title}
        </h2>
        <Button variant="ghost" size="md" icon aria-label="Close side panel" onClick={onClose}>
          <X aria-hidden="true" />
        </Button>
      </div>
      <div
        data-panel-body=""
        className="flex min-h-0 flex-1 flex-col desktop:overflow-y-auto desktop:overscroll-contain"
      >
        {children}
      </div>
    </aside>
  );
}
