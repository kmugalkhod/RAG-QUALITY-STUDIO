import { Button } from '../../../components/ui/button';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { cn } from '../../../lib/utils';
import { HINT } from './settingsStyles';

export type StageScopeMode =
  /** Editing the shared settings. */
  | { kind: 'shared'; customized: { id: string; name: string }[] }
  /** One source that follows the shared settings. */
  | { kind: 'inherit'; sourceName: string; sharedSummary: string }
  /** One source with its own settings. */
  | { kind: 'custom'; sourceName: string }
  /** One source's index, which is always its own. */
  | { kind: 'index' };

/**
 * Which sources an edit to a stage applies to, in a one-index-per-source pipeline: every
 * source that shares the stage, or one source with its own settings.
 */
export function StageScope({
  stageNoun,
  value,
  options,
  mode,
  onChange,
  onCustomize,
  onUseShared,
}: {
  /** "chunking", "extraction" and so on. */
  stageNoun: string;
  value: string;
  options: { value: string; label: string }[];
  mode: StageScopeMode;
  onChange: (value: string) => void;
  onCustomize: () => void;
  onUseShared: () => void;
}) {
  const NOTE = 'flex flex-col gap-2 rounded-card border p-4 text-sm';
  return (
    <div className="flex flex-col gap-4">
      <Label>
        {mode.kind === 'index' ? 'Source' : 'Applies to'}
        <NativeSelect value={value} onChange={(event) => onChange(event.target.value)}>
          {options.map((option) => (
            <NativeSelectOption key={option.value} value={option.value}>
              {option.label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </Label>
      {mode.kind === 'shared' && mode.customized.length > 0 && (
        <div className={cn(NOTE, 'border-border')}>
          <strong className="font-medium text-foreground">
            {mode.customized.length === 1
              ? 'One source uses its own settings'
              : `${mode.customized.length} sources use their own settings`}
          </strong>
          <p className={HINT}>
            {mode.customized.map((source) => source.name).join(', ')}{' '}
            {mode.customized.length === 1 ? 'does' : 'do'} not follow changes to the shared{' '}
            {stageNoun} settings.
          </p>
          <div className="flex flex-wrap gap-2">
            {mode.customized.map((source) => (
              <Button
                key={source.id}
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => onChange(source.id)}
              >
                Show settings for {source.name}
              </Button>
            ))}
          </div>
        </div>
      )}
      {mode.kind === 'inherit' && (
        <div className={cn(NOTE, 'border-border')}>
          <strong className="font-medium text-foreground">
            Uses the shared {stageNoun} settings
          </strong>
          <p className={HINT}>
            {mode.sourceName} follows the shared settings: {mode.sharedSummary}.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="self-start"
            onClick={onCustomize}
          >
            Customize {stageNoun} for this source
          </Button>
        </div>
      )}
      {mode.kind === 'custom' && (
        <div className={cn(NOTE, 'border-warning')}>
          <strong className="font-medium text-foreground">
            {mode.sourceName} uses its own {stageNoun} settings
          </strong>
          <p className={HINT}>
            Changes here apply only to this source. The other sources keep the shared settings.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="self-start"
            onClick={onUseShared}
          >
            Use shared settings
          </Button>
        </div>
      )}
    </div>
  );
}
