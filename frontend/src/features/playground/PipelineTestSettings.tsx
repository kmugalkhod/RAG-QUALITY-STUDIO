import { RetrievalSettingsForm } from '../retrieval/RetrievalSettingsForm';
import { nodeRetrieval } from '../retrieval/settings';
import { Button } from '../../components/ui/button';
import type { IndexVersion } from '../documents/indexApi';
import type { Draft, ExecutionNode, Kind, Options, Pipeline, Version } from '../pipelines/api';

interface Props {
  pipelines: Pipeline[];
  versions: Version[];
  indexes: IndexVersion[];
  options?: Options;
  pipelineId: string;
  versionId: string;
  draft?: Draft;
  dirty: boolean;
  disabled: boolean;
  errors: string[];
  onPipeline: (id: string) => void;
  onVersion: (id: string) => void;
  onChange: (draft: Draft) => void;
  onSave: () => void;
  onReset: () => void;
}

export function PipelineTestSettings(props: Props) {
  const { draft, options, disabled } = props;
  const retriever = draft?.execution.nodes.find(n => n.type === 'retriever');
  const prompt = draft?.execution.nodes.find(n => n.type === 'prompt');
  const llm = draft?.execution.nodes.find(n => n.type === 'llm');
  function update(kind: Kind, patch: Partial<ExecutionNode>) {
    if (!draft) return;
    props.onChange({ ...draft, execution: { ...draft.execution, nodes: draft.execution.nodes.map(n => n.type === kind ? { ...n, ...patch } : n) } });
  }
  return <div className="pipeline-test-settings">
    <header className="test-settings-header"><h2>Pipeline settings</h2></header>
    <div className="test-settings-scroll">
    <fieldset disabled={disabled}>
      <label>Pipeline
        <select value={props.pipelineId} onChange={e => props.onPipeline(e.target.value)}>
          <option value="">Choose a saved pipeline (optional)</option>
          {props.pipelines.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>
      {props.pipelineId && <label>Pipeline version
        <select value={props.versionId} onChange={e => props.onVersion(e.target.value)}>
          <option value="">Choose a version</option>
          {props.versions.map(v => <option key={v.id} value={v.id}>Version {v.version}</option>)}
        </select>
      </label>}
      {!draft ? <p role="status">Loading pipeline settings…</p> : <>
        <p className={`test-draft-status ${props.dirty ? 'is-dirty' : ''}`} role="status">
          {props.dirty ? 'Test draft · changes are not saved' : props.pipelineId ? 'Testing the saved version' : 'Custom test · no saved version'}
        </p>
        <h3>Retrieval inputs</h3>
        <label>Documents to search
          <select value={retriever?.index_id || ''} onChange={e => update('retriever', { index_id: e.target.value })}>
            <option value="">Choose prepared documents</option>
            {props.indexes.map(i => <option key={i.id} value={i.id}>Document set · Version {i.version} · {i.chunk_count} passages</option>)}
          </select>
        </label>
        <RetrievalSettingsForm value={nodeRetrieval(retriever)} onChange={retrieval => update('retriever', { retrieval })}/>
        <h3>Answer generation</h3>
        <div className="test-prompt-field"><label htmlFor="playground-prompt">Prompt</label>
          <textarea id="playground-prompt" rows={6} maxLength={8000} value={prompt?.template || ''} onChange={e => update('prompt', { template: e.target.value })}/>
        </div>
        <p className="field-hint">Include {'{question}'} and {'{context}'} where the question and retrieved passages belong.</p>
        <label>Model
          <select value={llm?.model || ''} onChange={e => update('llm', { model: e.target.value })}>
            <option value="">Choose a model</option>
            {options?.models.map(model => <option key={model}>{model}</option>)}
          </select>
        </label>
        <div className="test-number-settings">
          <label>Temperature<input type="number" min={0} max={2} step={0.1} value={llm?.temperature ?? ''} onChange={e => update('llm', { temperature: e.target.valueAsNumber })}/></label>
          <label>Max output tokens<input type="number" min={128} max={8192} value={llm?.max_tokens ?? ''} onChange={e => update('llm', { max_tokens: e.target.valueAsNumber })}/></label>
        </div>
        <p className="field-hint">Testing records these exact settings with the answer. It does not change saved versions.</p>

      </>}
    </fieldset>
    {props.errors.length > 0 && <details className="test-validation"><summary>{props.errors.length} setting{props.errors.length === 1 ? '' : 's'} to check</summary><ul>{props.errors.map(error => <li key={error}>{error}</li>)}</ul></details>}
    {options?.error && <p role="alert">{options.error}</p>}
    </div>
    {draft && <fieldset disabled={disabled} className="test-settings-footer">
        <details className="save-test-settings">
          <summary>Save these settings as a version</summary>
          <label>Pipeline name<input maxLength={120} value={draft.name} onChange={e => props.onChange({ ...draft, name: e.target.value })}/></label>
          <Button type="button" disabled={!!props.errors.length || !draft.name.trim() || (!props.dirty && !!props.pipelineId)} onClick={props.onSave}>Save pipeline version</Button>
        </details>
        <Button type="button" variant="outline" disabled={!props.dirty} onClick={props.onReset}>Reset changes</Button>
    </fieldset>}
  </div>;
}
