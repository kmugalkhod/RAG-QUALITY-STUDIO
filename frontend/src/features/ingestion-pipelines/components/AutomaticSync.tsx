import { Clock3, X } from 'lucide-react';

import { LIST, LIST_ROW, META } from '../../../components/parts';
import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { Popover, PopoverContent, PopoverTrigger } from '../../../components/ui/popover';
import { cn } from '../../../lib/utils';
import { describeCadence } from '../editorModel';
import type { IngestionPipelineVersion, IngestionSchedule } from '../model';
import { IconAction } from './IngestionToolbar';

function validInterval(schedule: IngestionSchedule) {
  return (
    schedule.cadence.kind !== 'interval' ||
    (schedule.cadence.minutes >= 15 && schedule.cadence.minutes <= 10080)
  );
}

// Schedules for the saved version, in a popover so opening them never pushes the canvas down.
export function AutomaticSync({
  open,
  busy,
  saved,
  schedules,
  scheduleName,
  scheduleMinutes,
  onOpenChange,
  onScheduleNameChange,
  onScheduleMinutesChange,
  onScheduleEdit,
  onCreate,
  onSave,
  onToggle,
  onRun,
}: {
  open: boolean;
  busy: boolean;
  saved: IngestionPipelineVersion;
  schedules: IngestionSchedule[];
  scheduleName: string;
  scheduleMinutes: number;
  onOpenChange: (open: boolean) => void;
  onScheduleNameChange: (name: string) => void;
  onScheduleMinutesChange: (minutes: number) => void;
  onScheduleEdit: (schedule: IngestionSchedule) => void;
  onCreate: () => void;
  onSave: (schedule: IngestionSchedule) => void;
  onToggle: (schedule: IngestionSchedule) => void;
  onRun: (schedule: IngestionSchedule) => void;
}) {
  const active = schedules.some((schedule) => schedule.status === 'enabled');
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <IconAction label={active ? 'Automatic sync · active' : 'Automatic sync'}>
        <PopoverTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            icon
            aria-label="Automatic sync"
            aria-controls="automatic-sync-panel"
            className={cn(active && 'text-accent')}
          >
            <Clock3 aria-hidden="true" />
          </Button>
        </PopoverTrigger>
      </IconAction>
      <PopoverContent
        id="automatic-sync-panel"
        align="end"
        aria-labelledby="automatic-sync-heading"
        className="max-h-(--radix-popover-content-available-height) overflow-y-auto overscroll-contain"
      >
        {/* Popover content renders in a portal, outside the editor's disabled fieldset. */}
        <fieldset className="m-0 flex min-w-0 flex-col gap-4 border-0 p-0" disabled={busy}>
          <div className="flex items-start justify-between gap-2">
            <div className="flex min-w-0 flex-col gap-1">
              <h2 id="automatic-sync-heading" className="text-sm font-semibold text-foreground">
                Automatic sync
              </h2>
              <p className={META}>
                Keep the published index up to date by running saved version {saved.version} on a
                schedule. Unsaved changes are not included.
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              icon
              aria-label="Close automatic sync settings"
              onClick={() => onOpenChange(false)}
            >
              <X aria-hidden="true" />
            </Button>
          </div>
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium text-foreground">Add a schedule</h3>
            <p className={META}>
              The first sync starts after the selected interval. You can run it now or pause it
              anytime.
            </p>
            <Label className="mb-0">
              Schedule name
              <Input
                className="mt-2"
                value={scheduleName}
                maxLength={120}
                onChange={(event) => onScheduleNameChange(event.target.value)}
              />
            </Label>
            <Label className="mb-0">
              Sync frequency
              <NativeSelect
                className="mt-2"
                value={scheduleMinutes}
                onChange={(event) => onScheduleMinutesChange(Number(event.target.value))}
              >
                <NativeSelectOption value={15}>Every 15 minutes</NativeSelectOption>
                <NativeSelectOption value={60}>Every hour</NativeSelectOption>
                <NativeSelectOption value={360}>Every 6 hours</NativeSelectOption>
                <NativeSelectOption value={720}>Every 12 hours</NativeSelectOption>
                <NativeSelectOption value={1440}>Every day</NativeSelectOption>
                <NativeSelectOption value={10080}>Every week</NativeSelectOption>
              </NativeSelect>
            </Label>
            <Button className="self-start" onClick={onCreate} disabled={!scheduleName.trim()}>
              Start automatic sync
            </Button>
          </div>

          {schedules.length > 0 && (
            <div className="flex flex-col gap-2 border-t border-border pt-4">
              <h3 className="text-sm font-medium text-foreground">Saved schedules</h3>
              <ul aria-label="Automatic sync schedules" className={LIST}>
                {schedules.map((schedule) => (
                  <li key={schedule.id} className={cn(LIST_ROW, 'flex flex-col gap-2 p-4')}>
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="flex min-w-0 flex-col gap-1">
                        <strong className="text-sm font-medium text-foreground wrap-anywhere">
                          {schedule.name}
                        </strong>
                        <span className={META}>{describeCadence(schedule)}</span>
                      </div>
                      <StatusBadge
                        status={schedule.status === 'enabled' ? 'succeeded' : 'cancelled'}
                      >
                        {schedule.status === 'enabled' ? 'Active' : 'Paused'}
                      </StatusBadge>
                    </div>
                    <Label className="mb-0">
                      Schedule name
                      <Input
                        className="mt-2"
                        value={schedule.name}
                        onChange={(event) =>
                          onScheduleEdit({ ...schedule, name: event.target.value })
                        }
                      />
                    </Label>
                    {schedule.cadence.kind === 'interval' && (
                      <Label className="mb-0">
                        Interval (minutes)
                        <Input
                          className="mt-2"
                          type="number"
                          min={15}
                          max={10080}
                          value={schedule.cadence.minutes}
                          onChange={(event) =>
                            onScheduleEdit({
                              ...schedule,
                              cadence: { kind: 'interval', minutes: Number(event.target.value) },
                            })
                          }
                        />
                      </Label>
                    )}
                    <p className={META}>
                      {schedule.next_run_at
                        ? `Next sync ${new Date(schedule.next_run_at).toLocaleString()}`
                        : 'No automatic runs while paused'}
                      {' · '}
                      Last result: {schedule.last_outcome ?? 'Not run yet'}
                    </p>
                    {schedule.last_error && (
                      <p className="text-sm text-danger wrap-anywhere">{schedule.last_error}</p>
                    )}
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onSave(schedule)}
                        disabled={!schedule.name.trim() || !validInterval(schedule)}
                      >
                        Save changes
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => onToggle(schedule)}>
                        {schedule.status === 'enabled' ? 'Pause sync' : 'Resume sync'}
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => onRun(schedule)}>
                        Run now
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </fieldset>
      </PopoverContent>
    </Popover>
  );
}
