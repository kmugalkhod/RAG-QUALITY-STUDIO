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
      className={`workflow-node ingestion-flow-node vertical-node relative w-80 border border-border rounded-[10px] bg-background text-foreground h-21 flex items-center gap-4 py-4.5 px-5.5 ${selected ? 'workflow-selected outline-2 outline-offset-2 outline-primary' : ''}`}
      data-execution-status={data.executionStatus}
      data-execution-reused={reused || undefined}
      aria-label={`${data.label}${execution ? `: ${execution.label}` : ''}`}
    >
      {!data.first && <Handle type="target" position={Position.Top} />}
      <Icon className="node-symbol shrink-0 text-muted-foreground" size={20} />
      <div className="node-copy min-w-0">
        <strong>{data.label}</strong>
        <div className="workflow-node-content p-0 text-xs wrap-anywhere mt-1 text-muted-foreground whitespace-nowrap overflow-hidden text-ellipsis">
          {data.detail}
        </div>
      </div>
      {execution && StatusIcon && (
        <span className="ingestion-node-status" aria-label={`Execution status: ${execution.label}`}>
          <StatusIcon
            className={data.executionStatus === 'running' ? 'ingestion-status-spinner' : ''}
            size={13}
            aria-hidden="true"
          />
          {execution.label}
        </span>
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
    <div ref={canvasRef} className="pipeline-canvas" aria-label="Ingestion pipeline canvas">
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
        <Background gap={22} size={1.2} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
