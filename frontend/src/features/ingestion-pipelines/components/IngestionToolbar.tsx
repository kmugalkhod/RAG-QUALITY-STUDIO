import { useState, type ReactNode } from 'react';
import { ArrowLeft, Database, Ellipsis, ExternalLink, Play, Save, Undo2 } from 'lucide-react';

import { LINK } from '../../../components/parts';
import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { Popover, PopoverContent, PopoverTrigger } from '../../../components/ui/popover';
import { Tooltip, TooltipContent, TooltipTrigger } from '../../../components/ui/tooltip';
import type { SourceSnapshot } from '../../documents/model';
import type { IngestionPipelineVersion } from '../model';

export function IconAction({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

interface IngestionToolbarProps {
  backHref: string;
  name: string;
  saved?: IngestionPipelineVersion;
  versions: IngestionPipelineVersion[];
  dirty: boolean;
  legacy: boolean;
  runLabel: string;
  canPreview: boolean;
  // A draft preview is still running, so a run would describe a different job.
  runBlocked?: boolean;
  canSave: boolean;
  // Automatic sync control, present once a version is saved.
  sync?: ReactNode;
  // Secondary actions that need extra input, such as reprocessing a saved snapshot.
  more?: ReactNode;
  onNameChange: (name: string) => void;
  onVersionSelect: (version: IngestionPipelineVersion) => void;
  onDiscard: () => void;
  onPreview: () => void;
  onSave: () => void;
  onRun: () => void;
}

// One compact row, mirroring the answer pipeline toolbar: identity on the left, actions on the
// right with the one primary action at the right end. Field labels are accessible names rather
// than visible captions, so the canvas keeps the height. The name field gives up width before
// the actions wrap to a second row; on phones the groups stack.
export function IngestionToolbar({
  backHref,
  name,
  saved,
  versions,
  dirty,
  legacy,
  runLabel,
  canPreview,
  runBlocked = false,
  canSave,
  sync,
  more,
  onNameChange,
  onVersionSelect,
  onDiscard,
  onPreview,
  onSave,
  onRun,
}: IngestionToolbarProps) {
  // Save leads while there are changes; a clean saved version leads to the run.
  const runReady = !!saved && !dirty;
  const run = (className: string, label: ReactNode, ariaLabel?: string) => (
    <Button
      className={className}
      variant={runReady ? 'primary' : 'outline'}
      disabled={!runReady || runBlocked}
      aria-label={ariaLabel}
      onClick={onRun}
    >
      <Play aria-hidden="true" />
      {label}
    </Button>
  );
  // Phones (spec 0015 U2): one line holds the name, version and the run; the status, sync
  // and the "…" menu (which then also holds Preview, Save and Discard) share a second line,
  // so the canvas starts within the first 40% of the screen. The identity group dissolves
  // into the toolbar there and `order` moves the status after the line break, so it renders
  // once. Desktop is unchanged.
  return (
    <div className="flex flex-wrap items-center gap-x-2 md:gap-x-4 md:gap-y-2">
      <div className="flex min-w-0 items-center gap-2 max-md:contents md:min-w-auto md:flex-1 md:flex-nowrap">
        <div className="flex min-w-0 flex-1 items-center gap-2 md:w-auto md:max-w-(--spacing-node) md:min-w-auto md:flex-1">
          <IconAction label="All ingestion pipelines">
            <Button variant="ghost" icon aria-label="All ingestion pipelines" asChild>
              <a href={backHref}>
                <ArrowLeft aria-hidden="true" />
              </a>
            </Button>
          </IconAction>
          <Input
            className="min-w-0 flex-1 md:min-w-(--toolbar-name-min)"
            aria-label="Pipeline name"
            value={name}
            maxLength={120}
            onChange={(event) => onNameChange(event.target.value)}
          />
        </div>
        <div className="w-auto shrink-0">
          <NativeSelect
            aria-label="Saved ingestion version"
            value={saved?.id ?? ''}
            disabled={dirty}
            onChange={(event) => {
              const version = versions.find((item) => item.id === event.target.value);
              if (version) {
                onVersionSelect(version);
              }
            }}
          >
            <NativeSelectOption value="">Not saved</NativeSelectOption>
            {versions.map((version) => (
              <NativeSelectOption key={version.id} value={version.id}>
                Version {version.version}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
        <p
          role="status"
          className="flex shrink-0 items-center gap-2 max-md:order-2 max-md:mt-2 max-md:min-w-0 max-md:flex-1"
        >
          <StatusBadge status={dirty ? 'running' : saved ? 'succeeded' : 'uploaded'}>
            {dirty ? 'Unsaved changes' : saved ? `Saved version ${saved.version}` : 'Not saved'}
          </StatusBadge>
          {legacy && <StatusBadge status="uploaded">Legacy character extraction</StatusBadge>}
        </p>
        {run(
          'shrink-0 md:hidden',
          'Run',
          runLabel === 'Run ingestion' ? undefined : `Run: ${runLabel}`,
        )}
      </div>
      <span aria-hidden="true" className="order-1 basis-full md:hidden" />
      <div className="flex items-center gap-2 max-md:order-2 max-md:mt-2 md:ml-auto md:flex-wrap md:justify-end">
        {saved && dirty && (
          <span className="max-md:hidden">
            <IconAction label="Discard changes">
              <Button
                variant="ghost"
                size="sm"
                icon
                aria-label="Discard changes"
                onClick={onDiscard}
              >
                <Undo2 aria-hidden="true" />
              </Button>
            </IconAction>
          </span>
        )}
        {sync}
        {more}
        <Button
          className="max-md:hidden"
          variant="outline"
          disabled={!canPreview}
          onClick={onPreview}
        >
          Preview processing
        </Button>
        <Button
          className="max-md:hidden"
          variant={runReady ? 'outline' : 'primary'}
          disabled={!canSave}
          onClick={onSave}
        >
          <Save aria-hidden="true" />
          Save version
        </Button>
        {run('max-md:hidden', runLabel)}
      </div>
    </div>
  );
}

/** The phone-only items at the top of the "…" menu; each closes the menu first. */
export function PhoneMenuItems({
  actions,
  onDone,
}: {
  actions: PhoneMenuActions;
  onDone: () => void;
}) {
  const act = (action: () => void) => () => {
    onDone();
    action();
  };
  return (
    <div className="flex flex-col gap-2 md:hidden">
      <Button variant="outline" disabled={!actions.canPreview} onClick={act(actions.onPreview)}>
        Preview processing
      </Button>
      <Button variant="outline" disabled={!actions.canSave} onClick={act(actions.onSave)}>
        <Save aria-hidden="true" />
        Save version
      </Button>
      {actions.canDiscard && (
        <Button variant="ghost" onClick={act(actions.onDiscard)}>
          <Undo2 aria-hidden="true" />
          Discard changes
        </Button>
      )}
    </div>
  );
}

/** The toolbar actions that move into the "…" menu on phones (spec 0015 U2). */
export type PhoneMenuActions = {
  canPreview: boolean;
  canSave: boolean;
  canDiscard: boolean;
  onPreview: () => void;
  onSave: () => void;
  onDiscard: () => void;
};

// Actions that need more than one click stay one step away instead of widening the toolbar.
export function IngestionMoreActions({
  busy,
  guideHref,
  guideLabel,
  websiteSource,
  legacy,
  canReprocess,
  snapshots,
  snapshotId,
  onSnapshotChange,
  onReprocess,
  onUpgrade,
  phone,
}: {
  busy: boolean;
  guideHref: string;
  guideLabel: string;
  websiteSource: boolean;
  legacy: boolean;
  canReprocess: boolean;
  snapshots: SourceSnapshot[];
  snapshotId: string;
  onSnapshotChange: (id: string) => void;
  onReprocess: () => void;
  onUpgrade: () => void;
  phone?: PhoneMenuActions;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <IconAction label="More actions">
        <PopoverTrigger asChild>
          <Button variant="ghost" size="sm" icon aria-label="More actions">
            <Ellipsis aria-hidden="true" />
          </Button>
        </PopoverTrigger>
      </IconAction>
      <PopoverContent align="end" aria-label="More actions">
        {/* Popover content renders in a portal, outside the editor's disabled fieldset. */}
        <fieldset className="m-0 flex min-w-0 flex-col gap-4 border-0 p-0" disabled={busy}>
          {phone && <PhoneMenuItems actions={phone} onDone={() => setOpen(false)} />}
          {websiteSource && (
            <div className="flex flex-col gap-2">
              <h2 className="text-sm font-semibold text-foreground">Reprocess saved source</h2>
              <p className="text-xs text-foreground-muted">
                Rebuild the index from a ready snapshot with the saved version, without fetching the
                website again.
              </p>
              <Label className="mb-0">
                Ready source snapshot
                <NativeSelect
                  className="mt-2"
                  value={snapshotId}
                  onChange={(event) => onSnapshotChange(event.target.value)}
                >
                  <NativeSelectOption value="">Choose a snapshot</NativeSelectOption>
                  {snapshots.map((snapshot) => (
                    <NativeSelectOption key={snapshot.id} value={snapshot.id}>
                      Snapshot {snapshot.snapshot_number} ·{' '}
                      {snapshot.source_identity.origins?.join(', ') || 'Website'}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </Label>
              <Button variant="outline" onClick={onReprocess} disabled={!canReprocess}>
                <Database aria-hidden="true" />
                Reprocess saved source
              </Button>
            </div>
          )}
          {legacy && (
            <div className="flex flex-col gap-2">
              <h2 className="text-sm font-semibold text-foreground">Upgrade legacy pipeline</h2>
              <p className="text-xs text-foreground-muted">
                Upgrade mapping: current source extraction becomes native-text-v1, saved Clean
                values move to standard-v1, and character windows become character-window-v1. The
                saved legacy version is not changed.
              </p>
              <Button variant="outline" onClick={onUpgrade}>
                Upgrade as draft
              </Button>
            </div>
          )}
          <a className={LINK} href={guideHref} target="_blank" rel="noopener noreferrer">
            {guideLabel}
            <ExternalLink aria-hidden="true" className="ml-1 size-4" />
          </a>
        </fieldset>
      </PopoverContent>
    </Popover>
  );
}
