import { Play, Save } from 'lucide-react';
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
  return (
    <div className="pipeline-toolbar flex flex-wrap m-0 gap-2.5 items-end border-b border-border py-3.5 px-5.5">
      <Label>
        Pipeline name
        <Input value={name} maxLength={120} onChange={(e) => onNameChange(e.target.value)} />
      </Label>
      <Label>
        Saved version
        <NativeSelect
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
      <span
        className={`draft-status text-[10px] text-muted-foreground [align-self:center] py-0 px-2 ${dirty ? 'is-dirty' : ''}`}
        role="status"
      >
        {dirty ? 'Unsaved changes' : saved ? `Saved version ${saved.version}` : 'No saved version'}
      </span>
      <Button
        variant={dirty ? 'default' : 'outline'}
        aria-describedby="save-guidance"
        disabled={!canSave}
        onClick={onSave}
      >
        <Save size={15} />
        Save version
      </Button>
      <Button
        variant={saved && !dirty ? 'default' : 'outline'}
        disabled={!saved || dirty || busy}
        onClick={onOpenPlayground}
      >
        <Play size={15} />
        Open Playground
      </Button>
      <Button variant="outline" disabled={!saved || dirty} onClick={onDuplicate}>
        Duplicate pipeline
      </Button>
      <Button variant="outline" disabled={!dirty} onClick={onDiscard}>
        Discard changes
      </Button>
    </div>
  );
}
