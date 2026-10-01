import { Play, Save } from 'lucide-react';
import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import type { PipelineVersion } from '../model';

interface PipelineToolbarProps {
  name: string;
  saved?: PipelineVersion;
  versions: PipelineVersion[];
  dirty: boolean;
  busy: boolean;
  canSave: boolean;
  onNameChange: (name: string) => void;
  onVersionSelect: (version: PipelineVersion) => void;
  onSave: () => void;
  onDuplicate: () => void;
  onDiscard: () => void;
  onOpenPlayground: () => void;
}

// Mirrored groups (spec 0002 layout rules): identity on the left, actions on the right with
// the one primary action at the right end. On phones the actions stack at full width.
export function PipelineToolbar({
  name,
  saved,
  versions,
  dirty,
  busy,
  canSave,
  onNameChange,
  onVersionSelect,
  onSave,
  onDuplicate,
  onDiscard,
  onOpenPlayground,
}: PipelineToolbarProps) {
  // Save leads while there are changes; a clean saved version leads to the Playground.
  const playgroundReady = !!saved && !dirty;
  return (
    <div className="flex flex-col gap-4 desktop:flex-row desktop:items-end desktop:justify-between">
      <div className="flex min-w-0 flex-col gap-4 md:flex-row md:items-end">
        <Label className="mb-0 min-w-0 md:w-panel">
          Pipeline name
          <Input
            className="mt-2"
            value={name}
            maxLength={120}
            onChange={(e) => onNameChange(e.target.value)}
          />
        </Label>
        <Label className="mb-0 md:w-sidebar">
          Saved version
          <NativeSelect
            className="mt-2"
            aria-label="Saved version"
            value={saved?.id ?? ''}
            disabled={dirty}
            onChange={(e) => {
              const v = versions.find((v) => v.id === e.target.value);
              if (v) {
                onVersionSelect(v);
              }
            }}
          >
            <NativeSelectOption value="">Not saved</NativeSelectOption>
            {versions.map((v) => (
              <NativeSelectOption key={v.id} value={v.id}>
                Version {v.version}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Label>
        <p role="status" className="flex h-control-md items-center pointer-coarse:h-control-lg">
          <StatusBadge status={dirty ? 'running' : saved ? 'succeeded' : 'uploaded'}>
            {dirty
              ? 'Unsaved changes'
              : saved
                ? `Saved version ${saved.version}`
                : 'No saved version'}
          </StatusBadge>
        </p>
      </div>
      <div className="flex flex-col gap-2 md:flex-row md:flex-wrap md:items-center md:justify-end">
        <Button variant="ghost" disabled={!dirty} onClick={onDiscard}>
          Discard changes
        </Button>
        <Button variant="outline" disabled={!saved || dirty} onClick={onDuplicate}>
          Duplicate pipeline
        </Button>
        <Button
          variant={playgroundReady ? 'primary' : 'outline'}
          disabled={!saved || dirty || busy}
          onClick={onOpenPlayground}
        >
          <Play aria-hidden="true" />
          Open Playground
        </Button>
        <Button
          variant={playgroundReady ? 'outline' : 'primary'}
          aria-describedby="save-guidance"
          disabled={!canSave}
          onClick={onSave}
        >
          <Save aria-hidden="true" />
          Save version
        </Button>
      </div>
    </div>
  );
}
