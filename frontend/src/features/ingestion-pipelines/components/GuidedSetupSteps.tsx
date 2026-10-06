import { useId, useState, type ReactNode } from 'react';
import {
  AlignLeft,
  Copy,
  Database,
  Eraser,
  Globe,
  Plus,
  Scissors,
  X,
  type LucideIcon,
} from 'lucide-react';
import { StatusBadge } from '../../../components/StatusBadge';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { Progress } from '../../../components/ui/progress';
import { RadioGroup, RadioGroupItem } from '../../../components/ui/radio-group';
import { Slider } from '../../../components/ui/slider';
import { cn } from '../../../lib/utils';
import { branchChain, indexLayout, maxWebsiteRunPages, maxWebsiteSources } from '../editorModel';
import {
  checkSiteUrl,
  chunkLimit,
  chunkSettings,
  customStages,
  guidedSites,
  overlapLimit,
  pageLimit,
  pageTotal,
  siteHost,
  siteScope,
  tokensPerPageEstimate,
  type GuidedDraft,
} from '../guidedModel';
import type {
  ExtractionCapabilities,
  IngestionNode,
  IngestionRun,
  IngestionRunGroup,
} from '../model';
import { sharedStage, sourceRunStatus } from '../sourcesView';

export const ROW =
  'flex min-h-row flex-wrap items-center gap-x-6 gap-y-2 rounded-control border border-border bg-surface-raised px-4 py-2';
const HINT = 'text-xs text-foreground-muted';
const VALUE = 'w-20 shrink-0 text-right font-mono text-xs text-foreground-muted tabular-nums';

const format = (value: number) => value.toLocaleString('en-US');

function RowName({
  Icon,
  title,
  hint,
  htmlFor,
  children,
}: {
  Icon?: LucideIcon;
  title: ReactNode;
  hint?: ReactNode;
  htmlFor?: string;
  children?: ReactNode;
}) {
  const Title = htmlFor ? 'label' : 'span';
  return (
    <span className="flex min-w-0 flex-1 basis-sidebar flex-wrap items-center gap-x-3 gap-y-1">
      {Icon && <Icon aria-hidden="true" className="size-4 shrink-0 text-accent" />}
      <Title htmlFor={htmlFor} className="min-w-0 text-md font-semibold wrap-anywhere">
        {title}
      </Title>
      {hint && <span className={HINT}>{hint}</span>}
      {children}
    </span>
  );
}

function RangeRow({
  Icon,
  title,
  hint,
  label,
  value,
  limit,
  unit,
  onChange,
  children,
}: {
  Icon: LucideIcon;
  title: ReactNode;
  hint?: ReactNode;
  label: string;
  value: number;
  limit: { min: number; max: number; step: number };
  unit: string;
  onChange: (value: number) => void;
  children?: ReactNode;
}) {
  return (
    <div className={ROW}>
      <RowName Icon={Icon} title={title} hint={hint} />
      <span className="flex min-w-0 flex-1 basis-sidebar items-center gap-3 md:max-w-(--guided-control)">
        <Slider
          aria-label={label}
          min={limit.min}
          max={limit.max}
          step={limit.step}
          ticks={11}
          value={[value]}
          onValueChange={([next]) => onChange(next)}
        />
        <span className={VALUE}>
          {format(value)} {unit}
        </span>
      </span>
      {children}
    </div>
  );
}

export type PreviewState =
  | { status: 'running' }
  | { status: 'succeeded'; included: number }
  | { status: 'failed'; message: string };

export function SourcesStep({
  guided,
  previews,
  busy,
  onAdd,
  onRemove,
  onPages,
  onPreview,
}: {
  guided: GuidedDraft;
  previews: Record<string, PreviewState | undefined>;
  busy: boolean;
  onAdd: (url: string) => void;
  onRemove: (sourceId: string) => void;
  onPages: (sourceId: string, pages: number) => void;
  onPreview: (sourceId: string) => void;
}) {
  const [address, setAddress] = useState('');
  const [error, setError] = useState('');
  const inputId = useId();
  const sites = guidedSites(guided.draft);
  const full = sites.length >= maxWebsiteSources;

  function add() {
    const checked = checkSiteUrl(guided.draft, address);
    if ('error' in checked) {
      setError(checked.error);
      return;
    }
    setError('');
    setAddress('');
    onAdd(checked.url);
  }

  return (
    <>
      <ul className="flex flex-col gap-2" aria-label="Websites">
        {sites.map((site) => {
          const host = siteHost(site);
          const preview = previews[site.id];
          return (
            <li key={site.id} className={ROW}>
              <RowName Icon={Globe} title={host} hint={siteScope(site.config)}>
                {preview?.status === 'running' ? (
                  <StatusBadge status="running">Previewing…</StatusBadge>
                ) : preview?.status === 'succeeded' ? (
                  <StatusBadge status="succeeded">
                    Preview OK · {format(preview.included)} pages
                  </StatusBadge>
                ) : preview?.status === 'failed' ? (
                  <StatusBadge status="failed" title={preview.message}>
                    Preview failed
                  </StatusBadge>
                ) : (
                  <StatusBadge status="uploaded">Not previewed</StatusBadge>
                )}
              </RowName>
              <span className="flex min-w-0 flex-1 basis-sidebar items-center gap-3 md:max-w-(--guided-control)">
                <Slider
                  aria-label={`Maximum pages for ${host}`}
                  min={pageLimit.min}
                  max={pageLimit.max}
                  step={pageLimit.step}
                  ticks={11}
                  value={[site.config.max_pages]}
                  onValueChange={([pages]) => onPages(site.id, pages)}
                />
                <span className={VALUE}>{format(site.config.max_pages)} pages</span>
              </span>
              <span className="flex shrink-0 items-center gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy || preview?.status === 'running'}
                  onClick={() => onPreview(site.id)}
                >
                  Preview<span className="sr-only"> {host}</span>
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  icon
                  aria-label={`Remove ${host}`}
                  title={`Remove ${host}`}
                  onClick={() => onRemove(site.id)}
                >
                  <X aria-hidden="true" />
                </Button>
              </span>
            </li>
          );
        })}
      </ul>
      <form
        className={cn(ROW, 'border-dashed bg-transparent')}
        onSubmit={(event) => {
          event.preventDefault();
          add();
        }}
      >
        <label
          htmlFor={inputId}
          className="flex shrink-0 items-center gap-3 text-sm font-medium text-foreground-muted"
        >
          <Plus aria-hidden="true" className="size-4" />
          Add a website
        </label>
        <Input
          id={inputId}
          value={address}
          placeholder="https://www.example.com/"
          autoComplete="url"
          inputMode="url"
          disabled={full}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${inputId}-error` : undefined}
          className="min-w-0 flex-1 basis-sidebar"
          onChange={(event) => setAddress(event.target.value)}
        />
        <Button type="submit" variant="outline" size="sm" disabled={full || !address.trim()}>
          Add website
        </Button>
        {error && (
          <p id={`${inputId}-error`} role="alert" className="w-full text-xs text-danger">
            {error}
          </p>
        )}
      </form>
      <p className={HINT}>
        You have added {sites.length} of {maxWebsiteSources} websites, up to{' '}
        {format(pageTotal(guided.draft))} pages per run (limit {format(maxWebsiteRunPages)}). A
        start address ending in .xml is read as a sitemap; any other address is crawled from that
        page. Path filters, crawl depth and speed can be changed in the editor afterwards.
      </p>
    </>
  );
}

function indexNames(guided: GuidedDraft) {
  const sites = guidedSites(guided.draft);
  if (indexLayout(guided.draft) !== 'per_source') {
    const publish = guided.draft.execution.nodes.find((node) => node.type === 'publish_index');
    return publish?.type === 'publish_index'
      ? [{ id: 'shared', name: publish.knowledge_set_name }]
      : [];
  }
  return sites.map((site) => {
    const publish = branchChain(guided.draft, site.id).find(
      (node) => node.type === 'publish_index',
    );
    return {
      id: site.id,
      host: siteHost(site),
      name: publish?.type === 'publish_index' ? publish.knowledge_set_name : '',
    };
  });
}

export function OutputStep({
  guided,
  onName,
  onLayout,
}: {
  guided: GuidedDraft;
  onName: (name: string) => void;
  onLayout: (layout: 'merged' | 'per_source') => void;
}) {
  const nameId = useId();
  const count = guidedSites(guided.draft).length;
  const layout = indexLayout(guided.draft);
  const choice = (value: 'merged' | 'per_source', title: string, hint: string, figure: string) => (
    <label
      className={cn(ROW, 'cursor-pointer', layout === value && 'border-accent bg-surface-active')}
    >
      <span className="flex min-w-0 flex-1 basis-node items-start gap-3">
        <RadioGroupItem value={value} className="mt-1" aria-describedby={`${nameId}-${value}`} />
        <span className="flex min-w-0 flex-col gap-1">
          <span className="text-md font-semibold">{title}</span>
          <span id={`${nameId}-${value}`} className={HINT}>
            {hint}
          </span>
        </span>
      </span>
      <span className="font-mono text-xs text-foreground-muted">{figure}</span>
    </label>
  );
  return (
    <>
      <div className={ROW}>
        <RowName
          Icon={Database}
          title="Name"
          hint="Names the pipeline and its indexes"
          htmlFor={nameId}
        />
        <Input
          id={nameId}
          value={guided.draft.name}
          maxLength={200}
          className="min-w-0 flex-1 basis-sidebar md:max-w-(--guided-control)"
          onChange={(event) => onName(event.target.value)}
        />
      </div>
      <RadioGroup
        aria-label="Indexes"
        value={layout}
        onValueChange={(value) => onLayout(value as 'merged' | 'per_source')}
      >
        {choice(
          'merged',
          'One combined index',
          'Ask one question across every site. Pages found on two sites are indexed once.',
          `${count} ${count === 1 ? 'site' : 'sites'} → 1 index`,
        )}
        {choice(
          'per_source',
          'One index per source',
          'Keep each site separate, for example to compare them. Any stage can differ per site.',
          `${count} ${count === 1 ? 'site' : 'sites'} → ${count} ${count === 1 ? 'index' : 'indexes'}`,
        )}
      </RadioGroup>
      <ul className="flex flex-col gap-2" aria-label="Index names">
        {indexNames(guided).map((entry) => (
          <li key={entry.id} className={ROW}>
            <RowName
              Icon={Database}
              title={entry.name || 'Unnamed index'}
              hint={'host' in entry ? `Pages from ${entry.host}` : 'Pages from every site'}
            />
          </li>
        ))}
      </ul>
      <p className={HINT}>
        You can change this later in the editor. Indexes you already published stay available.
      </p>
    </>
  );
}

type ExtractNode = Extract<IngestionNode, { type: 'extract' }>;
type CleanNode = Extract<IngestionNode, { type: 'clean' }>;

const extractLabels = {
  auto: 'Auto · page-level fallback',
  native: 'Native text',
  layout_aware: 'Layout-aware',
} as const;

export function ProcessingStep({
  guided,
  capabilities,
  onExtract,
  onClean,
  onChunk,
  onUseShared,
}: {
  guided: GuidedDraft;
  capabilities?: ExtractionCapabilities;
  onExtract: (strategy: 'auto' | 'native' | 'layout_aware') => void;
  onClean: (structureAware: boolean) => void;
  onChunk: (size: number, overlap: number, sourceId?: string) => void;
  onUseShared: (sourceId: string) => void;
}) {
  const extractId = useId();
  const cleanId = useId();
  const [editing, setEditing] = useState<string>();
  const extract = sharedStage(guided.draft, 'extract', guided.customized).node as
    | ExtractNode
    | undefined;
  const clean = sharedStage(guided.draft, 'clean', guided.customized).node as CleanNode | undefined;
  const embed = sharedStage(guided.draft, 'embed', guided.customized).node;
  const chunk = chunkSettings(guided);
  const structure = capabilities?.cleaning_profiles?.[0];
  const perSource = indexLayout(guided.draft) === 'per_source';
  const sites = guidedSites(guided.draft);
  return (
    <>
      <div className={ROW}>
        <RowName
          Icon={AlignLeft}
          title="Extract"
          hint="How text is read from each page"
          htmlFor={extractId}
        />
        <span className="min-w-0 flex-1 basis-sidebar md:max-w-(--guided-control)">
          <NativeSelect
            id={extractId}
            value={extract?.strategy ?? 'auto'}
            onChange={(event) => onExtract(event.target.value as keyof typeof extractLabels)}
          >
            {(Object.keys(extractLabels) as (keyof typeof extractLabels)[]).map((id) => {
              const profile = capabilities?.profiles.find((entry) => entry.id === id);
              return (
                <NativeSelectOption
                  key={id}
                  value={id}
                  disabled={profile ? !profile.available : false}
                >
                  {extractLabels[id]}
                  {profile && !profile.available ? ' (unavailable)' : ''}
                </NativeSelectOption>
              );
            })}
          </NativeSelect>
        </span>
      </div>
      <div className={ROW}>
        <RowName
          Icon={Eraser}
          title="Clean"
          hint="Removes menus and repeated page chrome"
          htmlFor={cleanId}
        />
        <span className="min-w-0 flex-1 basis-sidebar md:max-w-(--guided-control)">
          <NativeSelect
            id={cleanId}
            value={clean?.profile === 'structure-aware-v1' ? 'structure' : 'standard'}
            onChange={(event) => onClean(event.target.value === 'structure')}
          >
            <NativeSelectOption value="structure" disabled={!structure}>
              {structure
                ? `${structure.name} · ${structure.steps.length} steps`
                : 'Structure-aware (unavailable)'}
            </NativeSelectOption>
            <NativeSelectOption value="standard">Compatibility cleaner</NativeSelectOption>
          </NativeSelect>
        </span>
      </div>
      {chunk ? (
        <>
          <RangeRow
            Icon={Scissors}
            title="Chunk size"
            hint="Section-aware target, in tokens"
            label="Chunk size in tokens"
            value={chunk.size}
            limit={chunkLimit}
            unit="tokens"
            onChange={(size) => onChunk(size, chunk.overlap)}
          />
          <RangeRow
            Icon={Copy}
            title="Overlap"
            hint="Text repeated between neighbouring chunks"
            label="Overlap in tokens"
            value={chunk.overlap}
            limit={overlapLimit}
            unit="tokens"
            onChange={(overlap) => onChunk(chunk.size, overlap)}
          />
        </>
      ) : (
        <div className={ROW}>
          <RowName
            Icon={Scissors}
            title="Chunking"
            hint="This draft uses a chunking method the guided setup cannot edit; change it in the editor."
          />
        </div>
      )}
      <div className={ROW}>
        <RowName Icon={Database} title="Embed" hint="Model used to search the index" />
        <span className="min-w-0 flex-1 basis-sidebar text-sm wrap-anywhere md:max-w-(--guided-control)">
          {embed?.type === 'embed'
            ? `${embed.model} · ${embed.dimensions} dimensions`
            : 'Not configured'}
        </span>
      </div>
      {perSource &&
        sites.map((site) => {
          const host = siteHost(site);
          const custom = customStages(guided, site.id);
          const own = chunkSettings(guided, site.id);
          if (!custom.length && editing !== site.id) {
            return (
              <div key={site.id} className={ROW}>
                <RowName Icon={Globe} title={host} hint="Uses the shared settings" />
                <Button variant="outline" size="sm" onClick={() => setEditing(site.id)}>
                  Add override<span className="sr-only"> for {host}</span>
                </Button>
              </div>
            );
          }
          return (
            <div key={site.id} className={cn(ROW, custom.length && 'border-warning')}>
              <RowName
                title={host}
                hint={
                  custom.length
                    ? `Uses its own ${custom.join(', ')} settings`
                    : 'Change a setting to give this site its own value'
                }
              >
                {custom.length > 0 && <StatusBadge status="queued">Custom</StatusBadge>}
              </RowName>
              {custom.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    onUseShared(site.id);
                    setEditing(undefined);
                  }}
                >
                  Use shared settings<span className="sr-only"> for {host}</span>
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                aria-expanded={editing === site.id}
                onClick={() => setEditing(editing === site.id ? undefined : site.id)}
              >
                {editing === site.id ? 'Done' : 'Edit override'}
                <span className="sr-only"> for {host}</span>
              </Button>
              {editing === site.id && own && (
                <div className="flex w-full flex-col gap-2">
                  <RangeRow
                    Icon={Scissors}
                    title="Chunk size"
                    hint={`Only ${host}`}
                    label={`Chunk size in tokens for ${host}`}
                    value={own.size}
                    limit={chunkLimit}
                    unit="tokens"
                    onChange={(size) => onChunk(size, own.overlap, site.id)}
                  />
                  <RangeRow
                    Icon={Copy}
                    title="Overlap"
                    hint={`Only ${host}`}
                    label={`Overlap in tokens for ${host}`}
                    value={own.overlap}
                    limit={overlapLimit}
                    unit="tokens"
                    onChange={(overlap) => onChunk(own.size, overlap, site.id)}
                  />
                </div>
              )}
            </div>
          );
        })}
      <p className={HINT}>
        {perSource
          ? 'Shared by every site unless a site has its own override.'
          : 'These settings apply to every site.'}{' '}
        The hard maximum chunk size is a third above the target. Est. chunks assumes about{' '}
        {format(tokensPerPageEstimate)} tokens of text per page and every page limit being reached;
        it is an estimate, not a measurement.
      </p>
    </>
  );
}

export type ReviewEntry = { key: string; value: string; step: number };

export function ReviewStep({
  entries,
  onEdit,
}: {
  entries: ReviewEntry[];
  /** Absent once the pipeline is saved, because later edits would not be saved. */
  onEdit?: (step: number) => void;
}) {
  return (
    <>
      <dl className="flex flex-col gap-2">
        {entries.map((entry) => (
          <div key={entry.key} className={ROW}>
            <dt className="w-(--guided-key) shrink-0 text-sm text-foreground-muted">{entry.key}</dt>
            <dd className="min-w-0 flex-1 basis-sidebar text-sm font-medium wrap-anywhere">
              {entry.value}
            </dd>
            {onEdit && (
              <Button variant="ghost" size="sm" onClick={() => onEdit(entry.step)}>
                Edit<span className="sr-only"> {entry.key}</span>
              </Button>
            )}
          </div>
        ))}
      </dl>
      <p className={HINT}>
        Nothing is collected until you choose Save and publish. Saving creates version 1 of a new
        pipeline; the run records exactly which version it used.
      </p>
    </>
  );
}

export function RunStep({
  guided,
  run,
  group,
}: {
  guided: GuidedDraft;
  run?: IngestionRun;
  group?: IngestionRunGroup;
}) {
  const sites = guidedSites(guided.draft);
  return (
    <>
      <ul className="flex flex-col gap-2" aria-label="Run progress">
        {sites.map((site) => {
          const host = siteHost(site);
          const status = sourceRunStatus(site.id, run, group);
          const branch = group?.runs.find((entry) => entry.branch_source_node_id === site.id);
          const progress = (group ? branch : run)?.progress ?? 0;
          return (
            <li key={site.id} className={ROW}>
              <RowName Icon={Globe} title={host} hint={status?.detail ?? 'Waiting to start'} />
              <Progress
                aria-label={`Progress for ${host}`}
                value={progress}
                className="h-1 min-w-0 flex-1 basis-sidebar bg-track md:max-w-(--guided-control)"
              />
              <StatusBadge status={status?.tone ?? 'queued'}>
                {status?.label ?? 'Queued'}
              </StatusBadge>
            </li>
          );
        })}
      </ul>
      <p className={HINT}>
        The run keeps going if you leave this page. Results, refreshes and schedules are in the
        pipeline editor.
      </p>
    </>
  );
}
