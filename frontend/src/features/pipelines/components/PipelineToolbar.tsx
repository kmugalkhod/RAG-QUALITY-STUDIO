import type { ReactNode } from 'react';
import { ArrowLeft, CircleHelp, Copy, Play, Save } from 'lucide-react';
import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { Tooltip, TooltipContent, TooltipTrigger } from '../../../components/ui/tooltip';
import { docsHref } from '../../../lib/docs';
import type { PipelineVersion } from '../model';

interface PipelineToolbarProps {
  backHref: string;
  name: string;
  saved?: PipelineVersion;
  versions: PipelineVersion[];
  dirty: boolean;
  busy: boolean;
  canSave: boolean;
  // Id of the validation strip that explains why Save is disabled, when it is shown.
  guidanceId?: string;
  onNameChange: (name: string) => void;
  onVersionSelect: (version: PipelineVersion) => void;
  onSave: () => void;
  onDuplicate: () => void;
  onDiscard: () => void;
  onOpenPlayground: () => void;
}

function IconAction({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

// One compact row (spec 0002 mirrored groups): identity on the left, actions on the right with
// the one primary action at the right end. Field labels are accessible names rather than
// visible captions, so the canvas keeps the height. On phones the groups stack.
export function PipelineToolbar({
  backHref,
  name,
  saved,
  versions,
  dirty,
  busy,
  canSave,
  guidanceId,
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
    <div className="flex flex-col gap-2 desktop:flex-row desktop:items-center desktop:justify-between">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <div className="flex w-full min-w-0 items-center gap-2 md:w-auto">
          <IconAction label="All pipelines">
            <Button variant="ghost" icon aria-label="All pipelines" asChild>
              <a href={backHref}>
                <ArrowLeft aria-hidden="true" />
              </a>
            </Button>
          </IconAction>
          <Input
            className="min-w-0 flex-1 md:w-sidebar md:flex-none"
            aria-label="Pipeline name"
            value={name}
            maxLength={120}
            onChange={(e) => onNameChange(e.target.value)}
          />
        </div>
        <div className="w-auto">
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
        </div>
        <p role="status" className="flex items-center">
          <StatusBadge status={dirty ? 'running' : saved ? 'succeeded' : 'uploaded'}>
            {dirty
              ? 'Unsaved changes'
              : saved
                ? `Saved version ${saved.version}`
                : 'No saved version'}
          </StatusBadge>
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2 desktop:justify-end">
        {dirty && (
          <Button variant="ghost" onClick={onDiscard}>
            Discard changes
          </Button>
        )}
        <IconAction label="Duplicate pipeline">
          <Button
            variant="ghost"
            icon
            aria-label="Duplicate pipeline"
            disabled={!saved || dirty}
            onClick={onDuplicate}
          >
            <Copy aria-hidden="true" />
          </Button>
        </IconAction>
        <IconAction label="Answer pipeline setup and validation">
          <Button variant="ghost" icon asChild>
            <a
              href={docsHref('answers/pipelines')}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Answer pipeline setup and validation"
            >
              <CircleHelp aria-hidden="true" />
            </a>
          </Button>
        </IconAction>
        <Button
          className="flex-1 desktop:flex-none"
          variant={playgroundReady ? 'primary' : 'outline'}
          disabled={!saved || dirty || busy}
          onClick={onOpenPlayground}
        >
          <Play aria-hidden="true" />
          Open Playground
        </Button>
        <Button
          className="flex-1 desktop:flex-none"
          variant={playgroundReady ? 'outline' : 'primary'}
          aria-describedby={guidanceId}
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
