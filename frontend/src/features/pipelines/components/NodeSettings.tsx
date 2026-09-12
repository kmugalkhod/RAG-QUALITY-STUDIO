import { Input } from '../../../components/ui/input';
import { Textarea } from '../../../components/ui/textarea';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { Label } from '../../../components/ui/label';
import { Button } from '../../../components/ui/button';
import { RetrievalSettingsForm } from '../../../components/RetrievalSettingsForm';
import { getNodeRetrievalSettings } from '../../../lib/retrieval';

import { type IndexVersion } from '../../documents/model';
import type { PipelineNodeConfig, PipelineOptions } from '../model';
import type { FlowNode } from './WorkflowNode';
import { getNodeLabel } from '../model';
interface Props {
  open: boolean;
  config?: PipelineNodeConfig;
  selected: string;
  nodes: FlowNode[];
  indexes: IndexVersion[];
  options?: PipelineOptions;
  onSelect: (id: string) => void;
  onUpdate: (patch: Partial<PipelineNodeConfig>) => void;
  onDelete: () => void;
}
export function NodeSettings({
  open,
  config,
  selected,
  nodes,
  indexes,
  options,
  onSelect,
  onUpdate,
  onDelete,
}: Props) {
  return (
    <aside
      id="node-settings"
      className="pipeline-config border-l col-start-2 row-start-1 overflow-auto bg-background border-border pt-16 px-6 pb-6"
      hidden={!open}
    >
      <h2>{config ? getNodeLabel(config.type) : 'Node settings'}</h2>
      <Label>
        Selected node
        <NativeSelect
          aria-label="Selected node"
          value={selected}
          onChange={(e) => onSelect(e.target.value)}
        >
          <NativeSelectOption value="">Select a node</NativeSelectOption>
          {nodes.map((n) => (
            <NativeSelectOption key={n.id} value={n.id}>
              {n.data.label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </Label>
      {config?.type === 'retriever' && (
        <>
          <h3>Inputs</h3>
          <Label>
            Documents to search
            <NativeSelect
              aria-label="Documents to search"
              value={config.index_id}
              onChange={(e) => onUpdate({ index_id: e.target.value })}
            >
              <NativeSelectOption value="">Choose a prepared document set</NativeSelectOption>
              {indexes.map((i) => (
                <NativeSelectOption key={i.id} value={i.id}>
                  Document set · Version {i.version} · {i.chunk_count} passages
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Label>
          {!indexes.length && (
            <p>Prepare a document set in the Knowledge Base to start asking questions.</p>
          )}
          <RetrievalSettingsForm
            value={getNodeRetrievalSettings(config)}
            onChange={(retrieval) => onUpdate({ retrieval })}
          />
          <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
            Search uses this saved document set. Changing it does not change earlier answers.
          </p>
        </>
      )}
      {config?.type === 'prompt' && (
        <>
          <Label>
            Answer instructions
            <Textarea
              rows={9}
              maxLength={8000}
              value={config.template}
              onChange={(e) => onUpdate({ template: e.target.value })}
            />
          </Label>
          <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
            Use {'{question}'} and {'{context}'}. These are literal substitutions, with no
            expressions or code. Context is labeled evidence. Source labels, citation rules and
            grounding instructions are controlled by the application.
          </p>
        </>
      )}
      {config?.type === 'llm' && (
        <>
          <Label>
            Chat model
            <NativeSelect
              aria-label="Chat model"
              value={config.model}
              onChange={(e) => onUpdate({ model: e.target.value })}
            >
              <NativeSelectOption value="">Select a model</NativeSelectOption>
              {options?.models.map((m) => (
                <NativeSelectOption key={m}>{m}</NativeSelectOption>
              ))}
            </NativeSelect>
          </Label>
          <Label>
            Maximum output tokens
            <Input
              type="number"
              min={128}
              max={8192}
              value={Number.isFinite(config.max_tokens) ? config.max_tokens : ''}
              onChange={(e) => onUpdate({ max_tokens: e.target.valueAsNumber })}
            />
          </Label>
          <Label>
            Temperature
            <Input
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={Number.isFinite(config.temperature) ? config.temperature : ''}
              onChange={(e) => onUpdate({ temperature: e.target.valueAsNumber })}
            />
          </Label>
          <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
            Server context budget: {options?.context_tokens} tokens. Credentials stay on the server.
          </p>
        </>
      )}
      {config?.type === 'question' && (
        <p>
          Each question is independent. Enter your question in Playground after saving this
          pipeline.
        </p>
      )}
      {config?.type === 'answer' && (
        <p>Displays the generated answer with checked source references, evidence and usage.</p>
      )}
      {config && (
        <Button variant="outline" onClick={onDelete}>
          Delete selected node
        </Button>
      )}
    </aside>
  );
}
