import { Input } from '../../../components/ui/input';
import { Textarea } from '../../../components/ui/textarea';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { Label } from '../../../components/ui/label';
import { RetrievalSettingsForm } from '../../../components/RetrievalSettingsForm';
import { getNodeRetrievalSettings } from '../../../lib/retrieval';
import { Button } from '../../../components/ui/button';
import { Callout, InlineError, SUMMARY } from '../../../components/parts';
import { LoadingState } from '../../../components/states/LoadingState';
import { cn } from '../../../lib/utils';
import { ChevronRight, CircleCheck, CircleDot, TriangleAlert } from 'lucide-react';

import { formatIndexOption, type IndexVersion } from '../../documents/model';
import type {
  PipelineDraft,
  PipelineNodeConfig,
  PipelineNodeKind,
  PipelineOptions,
  Pipeline,
  PipelineVersion,
} from '../../pipelines/model';
const SUBHEADING = 'border-t border-border pt-4 text-sm font-semibold text-foreground';
const HINT = 'text-xs text-foreground-muted';

interface Props {
  pipelines: Pipeline[];
  versions: PipelineVersion[];
  indexes: IndexVersion[];
  options?: PipelineOptions;
  pipelineId: string;
  versionId: string;
  draft?: PipelineDraft;
  dirty: boolean;
  disabled: boolean;
  errors: string[];
  onPipeline: (id: string) => void;
  onVersion: (id: string) => void;
  onChange: (draft: PipelineDraft) => void;
  onSave: () => void;
  onReset: () => void;
}
export function PipelineTestSettings(props: Props) {
  const { draft, options, disabled } = props;
  const retriever = draft?.execution.nodes.find((n) => n.type === 'retriever');
  const prompt = draft?.execution.nodes.find((n) => n.type === 'prompt');
  const llm = draft?.execution.nodes.find((n) => n.type === 'llm');
  const selectedIndex = props.indexes.find((index) => index.id === retriever?.index_id);
  const currentIndex = selectedIndex
    ? props.indexes.find(
        (index) =>
          index.knowledge_set_id === selectedIndex.knowledge_set_id &&
          index.is_current &&
          index.id !== selectedIndex.id,
      )
    : undefined;
  function update(kind: PipelineNodeKind, patch: Partial<PipelineNodeConfig>) {
    if (!draft) {
      return;
    }
    props.onChange({
      ...draft,
      execution: {
        ...draft.execution,
        nodes: draft.execution.nodes.map((n) => (n.type === kind ? { ...n, ...patch } : n)),
      },
    });
  }
  return (
    <>
      <div className="flex flex-col gap-4 p-4">
        <fieldset disabled={disabled} className="flex min-w-0 flex-col gap-3">
          <Label>
            Pipeline
            <NativeSelect
              className="mt-2"
              value={props.pipelineId}
              onChange={(e) => props.onPipeline(e.target.value)}
            >
              <NativeSelectOption value="">Choose a saved pipeline (optional)</NativeSelectOption>
              {props.pipelines.map((p) => (
                <NativeSelectOption key={p.id} value={p.id}>
                  {p.name}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Label>
          {props.pipelineId && (
            <Label>
              Pipeline version
              <NativeSelect
                className="mt-2"
                value={props.versionId}
                onChange={(e) => props.onVersion(e.target.value)}
              >
                <NativeSelectOption value="">Choose a version</NativeSelectOption>
                {props.versions.map((v) => (
                  <NativeSelectOption key={v.id} value={v.id}>
                    Version {v.version}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Label>
          )}
          {!draft ? (
            <LoadingState label="Loading pipeline settings…" rows={2} />
          ) : (
            <>
              <p
                className={cn(
                  'flex items-center gap-2 text-xs',
                  props.dirty ? 'text-warning' : 'text-foreground-muted',
                )}
                role="status"
              >
                {props.dirty && <CircleDot aria-hidden="true" className="size-3" />}
                {props.dirty
                  ? 'Test draft · changes are not saved'
                  : props.pipelineId
                    ? 'Testing the saved version'
                    : 'Custom test · no saved version'}
              </p>
              <h3 className={SUBHEADING}>Retrieval inputs</h3>
              <Label>
                Documents to search
                <NativeSelect
                  className="mt-2"
                  value={retriever?.index_id || ''}
                  onChange={(e) => update('retriever', { index_id: e.target.value })}
                >
                  <NativeSelectOption value="">Choose prepared documents</NativeSelectOption>
                  {props.indexes.map((i) => (
                    <NativeSelectOption key={i.id} value={i.id}>
                      {formatIndexOption(i)}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </Label>
              {currentIndex && selectedIndex && (
                <Callout tone="warning" role="status" title="Your pipeline is searching old data">
                  <p>
                    Saved version {selectedIndex.version} has{' '}
                    {selectedIndex.chunk_count.toLocaleString()} passages; current version{' '}
                    {currentIndex.version} has {currentIndex.chunk_count.toLocaleString()}.
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="self-start"
                    onClick={() => update('retriever', { index_id: currentIndex.id })}
                  >
                    Test with current version {currentIndex.version}
                  </Button>
                </Callout>
              )}
              {selectedIndex && !currentIndex && (
                <p className="flex items-center gap-2 text-xs text-foreground-muted">
                  <CircleCheck aria-hidden="true" className="size-3 text-success" />
                  Current index · {selectedIndex.chunk_count.toLocaleString()} passages
                </p>
              )}
              <RetrievalSettingsForm
                value={getNodeRetrievalSettings(retriever)}
                onChange={(retrieval) => update('retriever', { retrieval })}
              />
              <h3 className={SUBHEADING}>Answer generation</h3>
              <div className="flex flex-col">
                <Label htmlFor="playground-prompt">Prompt</Label>
                <Textarea
                  id="playground-prompt"
                  rows={6}
                  maxLength={8000}
                  className="resize-y"
                  value={prompt?.template || ''}
                  onChange={(e) => update('prompt', { template: e.target.value })}
                />
              </div>
              <p className={HINT}>
                Include {'{question}'} and {'{context}'} where the question and retrieved passages
                belong.
              </p>
              <Label>
                Model
                <NativeSelect
                  className="mt-2"
                  value={llm?.model || ''}
                  onChange={(e) => update('llm', { model: e.target.value })}
                >
                  <NativeSelectOption value="">Choose a model</NativeSelectOption>
                  {options?.models.map((model) => (
                    <NativeSelectOption key={model}>{model}</NativeSelectOption>
                  ))}
                </NativeSelect>
              </Label>
              <div className="grid grid-cols-2 gap-3">
                <Label>
                  Temperature
                  <Input
                    className="mt-2"
                    type="number"
                    min={0}
                    max={2}
                    step={0.1}
                    value={Number.isFinite(llm?.temperature) ? llm?.temperature : ''}
                    onChange={(e) => update('llm', { temperature: e.target.valueAsNumber })}
                  />
                </Label>
                <Label>
                  Max output tokens
                  <Input
                    className="mt-2"
                    type="number"
                    min={128}
                    max={8192}
                    value={Number.isFinite(llm?.max_tokens) ? llm?.max_tokens : ''}
                    onChange={(e) => update('llm', { max_tokens: e.target.valueAsNumber })}
                  />
                </Label>
              </div>
              <p className={HINT}>
                Testing records these exact settings with the answer. It does not change saved
                versions.
              </p>
            </>
          )}
        </fieldset>
        {props.errors.length > 0 && (
          <details className="rounded-control border border-warning px-3">
            <summary className={cn(SUMMARY, 'text-warning [&_svg]:text-warning')}>
              <TriangleAlert aria-hidden="true" />
              {props.errors.length} setting{props.errors.length === 1 ? '' : 's'} to check
            </summary>
            <ul className="flex list-disc flex-col gap-1 pb-3 pl-4 text-xs text-foreground">
              {props.errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </details>
        )}
        {options?.error && <InlineError>{options.error}</InlineError>}
      </div>
      {draft && (
        // Pinned to the bottom of the panel on desktop, where the panel scrolls on its own.
        <fieldset
          disabled={disabled}
          className="mt-auto flex flex-col gap-3 border-t border-border bg-surface p-4 desktop:sticky desktop:bottom-0"
        >
          <details className="group">
            <summary className={SUMMARY}>
              <ChevronRight
                aria-hidden="true"
                className="transition-transform duration-(--transition-fast) group-open:rotate-90"
              />
              Save these settings as a version
            </summary>
            <div className="flex flex-col gap-3 pt-2">
              <Label>
                Pipeline name
                <Input
                  className="mt-2"
                  maxLength={120}
                  value={draft.name}
                  onChange={(e) => props.onChange({ ...draft, name: e.target.value })}
                />
              </Label>
              <Button
                type="button"
                variant="secondary"
                disabled={
                  !!props.errors.length ||
                  !draft.name.trim() ||
                  (!props.dirty && !!props.pipelineId)
                }
                onClick={props.onSave}
              >
                Save pipeline version
              </Button>
            </div>
          </details>
          <Button type="button" variant="outline" disabled={!props.dirty} onClick={props.onReset}>
            Reset changes
          </Button>
        </fieldset>
      )}
    </>
  );
}
