import { useEffect } from 'react';
import { useUpdateNodeInternals, Position, Handle, type NodeProps, type Node } from '@xyflow/react';
import { MessageSquare, Search, TextQuote, Cpu, CheckCheck } from 'lucide-react';
import { getNodeRetrievalSettings, formatRetrievalSummary } from '../../../lib/retrieval';
import type { PipelineNodeConfig } from '../model';
export type FlowNode = Node<{
  label: string;
  config: PipelineNodeConfig;
  vertical: boolean;
}>;
export function WorkflowNode({ id, data, selected }: NodeProps<FlowNode>) {
  const updateNodeInternals = useUpdateNodeInternals();
  useEffect(() => {
    updateNodeInternals(id);
  }, [id, data.vertical, updateNodeInternals]);
  const c = data.config;
  const Icon = {
    question: MessageSquare,
    retriever: Search,
    prompt: TextQuote,
    llm: Cpu,
    answer: CheckCheck,
  }[c.type];
  const detail =
    c.type === 'retriever'
      ? `${formatRetrievalSummary(getNodeRetrievalSettings(c))} · ${c.index_id ? 'Documents selected' : 'Choose documents'}`
      : c.type === 'llm'
        ? c.model || 'Choose a model'
        : c.type === 'prompt'
          ? 'Answer with evidence'
          : c.type === 'question'
            ? 'User input · single turn'
            : 'Response + citations';
  return (
    <div
      className={`workflow-node w-80 border border-border rounded-[10px] bg-background text-foreground h-21 flex items-center gap-4 shadow-none py-4.5 px-5.5 ${data.vertical ? 'vertical-node' : 'horizontal-node'}${selected ? ' workflow-selected border-primary outline-2 -outline-offset-1 outline-primary shadow-none' : ''}`}
    >
      {c.type !== 'question' && (
        <Handle type="target" position={data.vertical ? Position.Top : Position.Left} />
      )}
      <Icon className="node-symbol shrink-0 text-muted-foreground" size={22} />
      <div className="node-copy min-w-0">
        <strong>{data.label}</strong>
        <div className="workflow-node-content p-0 text-xs wrap-anywhere mt-1 text-muted-foreground whitespace-nowrap overflow-hidden text-ellipsis">
          {detail}
        </div>
      </div>
      {c.type !== 'answer' && (
        <Handle type="source" position={data.vertical ? Position.Bottom : Position.Right} />
      )}
    </div>
  );
}
