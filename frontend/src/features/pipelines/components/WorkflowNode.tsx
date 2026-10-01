import { useEffect } from 'react';
import { useUpdateNodeInternals, Position, Handle, type NodeProps, type Node } from '@xyflow/react';
import { MessageSquare, Search, TextQuote, Cpu, CheckCheck, TriangleAlert } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '../../../components/ui/tooltip';
import { cn } from '../../../lib/utils';
import type { PipelineNodeConfig } from '../model';
import { summarizeNodeConfig } from './summarizeNodeConfig';

export type FlowNode = Node<{
  label: string;
  config: PipelineNodeConfig;
  vertical: boolean;
  // Display only: the first validation message for this node. Never saved.
  issue?: string;
}>;

const icons = {
  question: MessageSquare,
  retriever: Search,
  prompt: TextQuote,
  llm: Cpu,
  answer: CheckCheck,
};

// Node card (spec 0002, AC-9): 288 by 80 in a vertical layout, 220px wide in a saved
// horizontal layout. The selected outline sits inside the border, so nothing shifts.
export function WorkflowNode({ id, data, selected }: NodeProps<FlowNode>) {
  const updateNodeInternals = useUpdateNodeInternals();
  useEffect(() => {
    updateNodeInternals(id);
  }, [id, data.vertical, updateNodeInternals]);
  const config = data.config;
  const Icon = icons[config.type];
  const summary = summarizeNodeConfig(config.type, config);
  return (
    <div
      data-testid="node-card"
      data-selected={selected ? 'true' : 'false'}
      className={cn(
        'flex h-node-h items-center gap-3 rounded-control border border-border bg-surface p-4 text-foreground',
        data.vertical ? 'w-node' : 'w-node-legacy',
        selected && 'outline-2 -outline-offset-1 outline-accent',
      )}
    >
      {config.type !== 'question' && (
        <Handle type="target" position={data.vertical ? Position.Top : Position.Left} />
      )}
      <Icon
        aria-hidden="true"
        className={cn(
          'size-(--icon-lg) shrink-0',
          selected ? 'text-accent' : 'text-foreground-muted',
        )}
      />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <strong className="truncate text-base font-medium">{data.label}</strong>
        <Tooltip>
          <TooltipTrigger asChild>
            <p className="truncate text-xs text-foreground-muted">{summary}</p>
          </TooltipTrigger>
          <TooltipContent>{summary}</TooltipContent>
        </Tooltip>
      </div>
      {data.issue && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span data-testid="node-issue" className="shrink-0 text-warning">
              <TriangleAlert aria-hidden="true" className="size-4" />
              <span className="sr-only">Needs attention: {data.issue}</span>
            </span>
          </TooltipTrigger>
          <TooltipContent>{data.issue}</TooltipContent>
        </Tooltip>
      )}
      {config.type !== 'answer' && (
        <Handle type="source" position={data.vertical ? Position.Bottom : Position.Right} />
      )}
    </div>
  );
}
