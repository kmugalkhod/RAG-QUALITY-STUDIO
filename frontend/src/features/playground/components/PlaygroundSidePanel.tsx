import type { ReactNode } from 'react';
import { X } from 'lucide-react';
import { Button } from '../../../components/ui/button';

export function PlaygroundSidePanel({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <aside
      id="playground-settings"
      className="playground-settings"
      hidden={!open}
      aria-label="Playground side panel"
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          onClose();
        }
      }}
    >
      <Button
        variant="ghost"
        className="inspector-close icon-button p-1.25 border-0 bg-transparent inline-flex items-center justify-center text-muted-foreground rounded-sm min-w-7.5 min-h-7.5"
        aria-label="Close side panel"
        onClick={onClose}
      >
        <X size={18} />
      </Button>
      {children}
    </aside>
  );
}
