import { History, PanelRightOpen, Search, SlidersHorizontal, Sparkles } from 'lucide-react';
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
  return (
    <>
      <div className="playground-test-modes" role="group" aria-label="Test mode">
        <Button
          variant="ghost"
          className="h-auto justify-start whitespace-normal rounded-[10px] border border-border px-4 py-3 text-left text-muted-foreground aria-pressed:border-primary aria-pressed:bg-sidebar-accent aria-pressed:text-foreground"
          aria-label="Retrieval test"
          aria-pressed={mode === 'retrieval'}
          disabled={disabled}
          onClick={() => onModeChange('retrieval')}
        >
          <Search size={18} />
          <span>
            <strong>Retrieval test</strong>
            <small>Find passages only</small>
          </span>
        </Button>
        <Button
          variant="ghost"
          className="h-auto justify-start whitespace-normal rounded-[10px] border border-border px-4 py-3 text-left text-muted-foreground aria-pressed:border-primary aria-pressed:bg-sidebar-accent aria-pressed:text-foreground"
          aria-label="Pipeline test"
          aria-pressed={mode === 'pipeline'}
          disabled={disabled}
          onClick={() => onModeChange('pipeline')}
        >
          <Sparkles size={18} />
          <span>
            <strong>Pipeline test</strong>
            <small>Find passages + generate an answer</small>
          </span>
        </Button>
      </div>
      <div className="playground-toolbar">
        <span className="playground-context">
          {mode === 'retrieval'
            ? 'Retrieval settings affect document search only'
            : saved
              ? `${saved.name} · Version ${saved.version}${dirty ? ' · Test draft' : ''}`
              : 'Custom pipeline test'}
        </span>
        <Button
          variant="outline"
          aria-expanded={panel === 'settings'}
          aria-controls="playground-settings"
          onClick={() => onTogglePanel('settings')}
        >
          <SlidersHorizontal size={16} />
          {mode === 'retrieval' ? 'Retrieval settings' : 'Pipeline settings'}
        </Button>
        {mode === 'pipeline' && (
          <Button
            variant="outline"
            aria-expanded={panel === 'history'}
            aria-controls="playground-settings"
            onClick={() => onTogglePanel('history')}
          >
            <History size={16} />
            Past questions
          </Button>
        )}
        {mode === 'pipeline' && hasRun && (
          <Button
            variant="outline"
            aria-expanded={panel === 'sources' || panel === 'details'}
            aria-controls="playground-settings"
            onClick={() => onTogglePanel('sources')}
          >
            <PanelRightOpen size={16} />
            Sources & details
          </Button>
        )}
      </div>
    </>
  );
}
