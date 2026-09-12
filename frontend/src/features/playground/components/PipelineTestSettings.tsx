import { Input } from '../../../components/ui/input';
import { Textarea } from '../../../components/ui/textarea';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { Label } from '../../../components/ui/label';
import { RetrievalSettingsForm } from '../../../components/RetrievalSettingsForm';
import { getNodeRetrievalSettings } from '../../../lib/retrieval';
import { Button } from '../../../components/ui/button';

import { formatIndexOption, type IndexVersion } from '../../documents/model';
import type {
  PipelineDraft,
  PipelineNodeConfig,
  PipelineNodeKind,
  PipelineOptions,
  Pipeline,
  PipelineVersion,
} from '../../pipelines/model';
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
    <div className="pipeline-test-settings">
      <header className="test-settings-header">
        <h2>Pipeline settings</h2>
      </header>
      <div className="test-settings-scroll">
        <fieldset disabled={disabled}>
          <Label>
            Pipeline
            <NativeSelect
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
            <p role="status">Loading pipeline settings…</p>
          ) : (
            <>
              <p className={`test-draft-status ${props.dirty ? 'is-dirty' : ''}`} role="status">
                {props.dirty
                  ? 'Test draft · changes are not saved'
                  : props.pipelineId
                    ? 'Testing the saved version'
                    : 'Custom test · no saved version'}
              </p>
              <h3>Retrieval inputs</h3>
              <Label>
                Documents to search
                <NativeSelect
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
              <RetrievalSettingsForm
                value={getNodeRetrievalSettings(retriever)}
                onChange={(retrieval) => update('retriever', { retrieval })}
              />
              <h3>Answer generation</h3>
              <div className="test-prompt-field">
                <Label htmlFor="playground-prompt">Prompt</Label>
                <Textarea
                  id="playground-prompt"
                  rows={6}
                  maxLength={8000}
                  value={prompt?.template || ''}
                  onChange={(e) => update('prompt', { template: e.target.value })}
                />
              </div>
              <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
                Include {'{question}'} and {'{context}'} where the question and retrieved passages
                belong.
              </p>
              <Label>
                Model
                <NativeSelect
                  value={llm?.model || ''}
                  onChange={(e) => update('llm', { model: e.target.value })}
                >
                  <NativeSelectOption value="">Choose a model</NativeSelectOption>
                  {options?.models.map((model) => (
                    <NativeSelectOption key={model}>{model}</NativeSelectOption>
                  ))}
                </NativeSelect>
              </Label>
              <div className="test-number-settings">
                <Label>
                  Temperature
                  <Input
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
                    type="number"
                    min={128}
                    max={8192}
                    value={Number.isFinite(llm?.max_tokens) ? llm?.max_tokens : ''}
                    onChange={(e) => update('llm', { max_tokens: e.target.valueAsNumber })}
                  />
                </Label>
              </div>
              <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
                Testing records these exact settings with the answer. It does not change saved
                versions.
              </p>
            </>
          )}
        </fieldset>
        {props.errors.length > 0 && (
          <details className="test-validation">
            <summary>
              {props.errors.length} setting{props.errors.length === 1 ? '' : 's'} to check
            </summary>
            <ul>
              {props.errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </details>
        )}
        {options?.error && <p role="alert">{options.error}</p>}
      </div>
      {draft && (
        <fieldset disabled={disabled} className="test-settings-footer">
          <details className="save-test-settings">
            <summary>Save these settings as a version</summary>
            <Label>
              Pipeline name
              <Input
                maxLength={120}
                value={draft.name}
                onChange={(e) => props.onChange({ ...draft, name: e.target.value })}
              />
            </Label>
            <Button
              type="button"
              disabled={
                !!props.errors.length || !draft.name.trim() || (!props.dirty && !!props.pipelineId)
              }
              onClick={props.onSave}
            >
              Save pipeline version
            </Button>
          </details>
          <Button type="button" variant="outline" disabled={!props.dirty} onClick={props.onReset}>
            Reset changes
          </Button>
        </fieldset>
      )}
    </div>
  );
}
