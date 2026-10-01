import { BookOpenCheck, History, PanelRightOpen, Search, SlidersHorizontal } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import type { PipelineVersion } from '../../pipelines/model';
import type { PlaygroundMode, PlaygroundPanel } from '../model';

interface PlaygroundToolbarProps {
  mode: PlaygroundMode;
  panel: PlaygroundPanel;
  disabled: boolean;
  saved?: PipelineVersion;
  dirty: boolean;
  hasRun: boolean;
  onModeChange: (mode: PlaygroundMode) => void;
  onTogglePanel: (panel: 'settings' | 'history' | 'sources') => void;
}

const MODES = [
  { value: 'retrieval', label: 'Retrieval test', icon: Search },
  { value: 'pipeline', label: 'Pipeline test', icon: BookOpenCheck },
] as const;

const TOGGLE = 'text-foreground-muted aria-expanded:bg-surface-hover aria-expanded:text-foreground';

// A centered control cluster: the test mode on the left mirrors the panel toggles on the right,
// with the exact configuration under test between them (spec 0002 layout rules).
export function PlaygroundToolbar({
  mode,
  panel,
  disabled,
  saved,
  dirty,
  hasRun,
  onModeChange,
  onTogglePanel,
}: PlaygroundToolbarProps) {
  const context =
    mode === 'retrieval'
      ? 'Retrieval settings affect document search only'
      : saved
        ? `${saved.name} · Version ${saved.version}${dirty ? ' · Test draft' : ''}`
        : 'Custom pipeline test';
  return (
    // `playground-toolbar` is a marker, not a style: closing the side panel returns focus to
    // the toggle found under it.
    <div className="playground-toolbar flex flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-center md:gap-4">
      <div
        className="grid grid-cols-2 gap-1 rounded-control border border-border bg-surface p-1 md:shrink-0"
        role="group"
        aria-label="Test mode"
      >
        {MODES.map(({ value, label, icon: Icon }) => (
          <Button
            key={value}
            variant="ghost"
            size="sm"
            className="text-foreground-muted aria-pressed:bg-surface-hover aria-pressed:text-foreground"
            aria-pressed={mode === value}
            disabled={disabled}
            onClick={() => onModeChange(value)}
          >
            <Icon aria-hidden="true" />
            {label}
          </Button>
        ))}
      </div>
      <p
        data-testid="playground-context"
        title={context}
        className="min-w-0 truncate text-sm text-foreground-muted md:flex-1 md:text-center"
      >
        {context}
      </p>
      <div className="flex flex-wrap items-center gap-2 md:shrink-0 md:justify-end">
        <Button
          variant="ghost"
          size="sm"
          className={TOGGLE}
          aria-expanded={panel === 'settings'}
          aria-controls="playground-settings"
          onClick={() => onTogglePanel('settings')}
        >
          <SlidersHorizontal aria-hidden="true" />
          {mode === 'retrieval' ? 'Retrieval settings' : 'Pipeline settings'}
        </Button>
        {mode === 'pipeline' && (
          <Button
            variant="ghost"
            size="sm"
            className={TOGGLE}
            aria-expanded={panel === 'history'}
            aria-controls="playground-settings"
            onClick={() => onTogglePanel('history')}
          >
            <History aria-hidden="true" />
            Past questions
          </Button>
        )}
        {mode === 'pipeline' && hasRun && (
          <Button
            variant="ghost"
            size="sm"
            className={TOGGLE}
            aria-expanded={panel === 'sources' || panel === 'details'}
            aria-controls="playground-settings"
            onClick={() => onTogglePanel('sources')}
          >
            <PanelRightOpen aria-hidden="true" />
            Sources & details
          </Button>
        )}
      </div>
    </div>
  );
}
