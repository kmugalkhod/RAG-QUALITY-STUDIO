import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react';
import {
  ArrowUpToLine,
  Ban,
  CircleCheck,
  CircleX,
  Clock3,
  Database,
  Globe,
  LoaderCircle,
  RefreshCw,
  ScanText,
  Scissors,
  Sparkles,
} from 'lucide-react';
import type { RefObject } from 'react';

import { StatusBadge } from '../../../components/StatusBadge';
import { Tooltip, TooltipContent, TooltipTrigger } from '../../../components/ui/tooltip';
import { cn } from '../../../lib/utils';

import type { IngestionNodeExecutionStatus } from '../executionState';
import type { IngestionNode, IngestionPipelineDraft } from '../model';

type FlowData = {
  label: string;
  detail: string;
  first: boolean;
  last: boolean;
  stage: IngestionNode['type'];
  executionStatus?: IngestionNodeExecutionStatus;
  executionWasStarted?: boolean;
};

export type IngestionFlowNode = Node<FlowData, 'ingestion'>;

export const stageIcons = {
  source: Globe,
  extract: ScanText,
  clean: Sparkles,
  chunk: Scissors,
  embed: Database,
  publish_index: ArrowUpToLine,
};

export const executionStatusPresentation = {
  queued: { label: 'Queued', icon: Clock3 },
  running: { label: 'Running now', icon: LoaderCircle },
  succeeded: { label: 'Complete', icon: CircleCheck },
  failed: { label: 'Failed', icon: CircleX },
  cancelled: { label: 'Cancelled', icon: Ban },
} satisfies Record<IngestionNodeExecutionStatus, { label: string; icon: typeof Clock3 }>;

function FlowNode({ data, selected }: NodeProps<IngestionFlowNode>) {
  const Icon = stageIcons[data.stage];
  const reused = data.executionStatus === 'succeeded' && data.executionWasStarted === false;
  const execution = reused
    ? { label: 'Reused', icon: RefreshCw }
    : data.executionStatus
      ? executionStatusPresentation[data.executionStatus]
      : undefined;
  const StatusIcon = execution?.icon;

  return (
    <div
      data-testid="ingestion-node"
      data-selected={selected ? 'true' : 'false'}
      data-execution-status={data.executionStatus}
      data-execution-reused={reused || undefined}
      aria-label={`${data.label}${execution ? `: ${execution.label}` : ''}`}
      className={cn(
        'relative flex h-node-h w-node items-center gap-3 rounded-control border border-border bg-surface p-4 text-foreground transition-colors duration-(--transition-fast)',
        (data.executionStatus === 'queued' || reused) && 'border-dashed border-border-strong',
        data.executionStatus === 'running' && 'border-accent',
        data.executionStatus === 'succeeded' && !reused && 'border-success',
        data.executionStatus === 'failed' && 'border-danger',
        data.executionStatus === 'cancelled' && 'border-dashed border-warning',
        selected && 'outline-2 -outline-offset-1 outline-accent',
      )}
    >
      {!data.first && <Handle type="target" position={Position.Top} />}
      <Icon
        aria-hidden="true"
        className={cn(
          'size-(--icon-lg) shrink-0',
          selected || data.executionStatus === 'running' ? 'text-accent' : 'text-foreground-muted',
        )}
      />
      <div className="flex min-w-0 flex-col gap-1">
        <strong className="truncate text-base font-medium">{data.label}</strong>
        <Tooltip>
          <TooltipTrigger asChild>
            <p className="truncate text-xs text-foreground-muted">{data.detail}</p>
          </TooltipTrigger>
          <TooltipContent>{data.detail}</TooltipContent>
        </Tooltip>
      </div>
      {execution && StatusIcon && (
        <StatusBadge
          status={reused ? 'succeeded' : (data.executionStatus ?? 'queued')}
          className="absolute -top-3 right-4"
        >
          <StatusIcon
            aria-hidden="true"
            className={cn(data.executionStatus === 'running' && 'motion-safe:animate-spin')}
          />
          {execution.label}
        </StatusBadge>
      )}
      {!data.last && <Handle type="source" position={Position.Bottom} />}
    </div>
  );
}

const nodeTypes = { ingestion: FlowNode };

export function IngestionPipelineCanvas({
  canvasRef,
  nodes,
  edges,
  onInit,
  onNodesChange,
  onSelectNode,
}: {
  canvasRef: RefObject<HTMLDivElement | null>;
  nodes: IngestionFlowNode[];
  edges: IngestionPipelineDraft['execution']['edges'];
  onInit: (instance: ReactFlowInstance<IngestionFlowNode, Edge>) => void;
  onNodesChange: (changes: NodeChange<IngestionFlowNode>[]) => void;
  onSelectNode: (nodeId: string) => void;
}) {
  return (
    <div
      ref={canvasRef}
      data-testid="pipeline-canvas"
      className="size-full"
      aria-label="Ingestion pipeline canvas"
    >
      <ReactFlow<IngestionFlowNode, Edge>
        nodes={nodes}
        edges={edges.map((edge) => ({ ...edge, id: `${edge.source}-${edge.target}` }))}
        nodeTypes={nodeTypes}
        onInit={onInit}
        onNodesChange={onNodesChange}
        onNodeClick={(_, node) => onSelectNode(node.id)}
        nodesConnectable={false}
        zoomOnScroll={false}
        preventScrolling={false}
        deleteKeyCode={null}
        fitView
        fitViewOptions={{ padding: 0.12, maxZoom: 1 }}
      >
        <Background gap={24} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
