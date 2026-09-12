import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Background,
  Controls,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type NodeChange,
  type ReactFlowInstance,
  type XYPosition,
} from '@xyflow/react';
import { ArrowDown } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { getNodeLabel, pipelineNodeOrder, type PipelineNodeKind } from '../model';
import { WorkflowNode, type FlowNode } from './WorkflowNode';

const nodeTypes = { workflow: WorkflowNode };

interface PipelineCanvasProps {
  nodes: FlowNode[];
  edges: Edge[];
  flow?: ReactFlowInstance<FlowNode>;
  busy: boolean;
  inspectorOpen: boolean;
  children: ReactNode;
  onInit: (flow: ReactFlowInstance<FlowNode>) => void;
  onNodesChange: (changes: NodeChange<FlowNode>[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => void;
  onNodeSelect: (nodeId: string) => void;
  onAddNode: (kind: PipelineNodeKind, position?: XYPosition) => void;
  onArrange: () => void;
  onRestoreTemplate: () => void;
  onInspectorOpenChange: (open: boolean) => void;
}

export function PipelineCanvas({
  nodes,
  edges,
  flow,
  busy,
  inspectorOpen,
  children,
  onInit,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodeSelect,
  onAddNode,
  onArrange,
  onRestoreTemplate,
  onInspectorOpenChange,
}: PipelineCanvasProps) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !flow) {
      return;
    }
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        void flow.fitView({ padding: 0.18, maxZoom: 1 });
      });
    });
    observer.observe(canvas);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [flow]);

  return (
    <div
      className={`pipeline-editor grid border border-border bg-background grid-cols-[90px_minmax(280px,_1fr)_260px] ${paletteOpen ? 'palette-open' : ''}  ${inspectorOpen ? 'inspector-open' : ''}`}
    >
      <Button
        className="inspector-toggle absolute right-4 top-3.5 z-5"
        variant="outline"
        aria-expanded={inspectorOpen}
        aria-controls="node-settings"
        onClick={() => onInspectorOpenChange(!inspectorOpen)}
      >
        {inspectorOpen ? 'Hide settings' : 'Node settings'}
      </Button>
      <div className="pipeline-palette block gap-3 p-0 col-auto flex-col flex-nowrap items-stretch border-border absolute top-3.5 left-4 z-5 border-0">
        <div className="canvas-tools">
          <Button
            variant="outline"
            aria-expanded={paletteOpen}
            onClick={() => setPaletteOpen((v) => !v)}
          >
            {paletteOpen ? 'Hide nodes' : 'Nodes'}
          </Button>
          <Button variant="outline" onClick={onArrange}>
            <ArrowDown size={14} />
            Arrange vertically
          </Button>
        </div>
        <div hidden={!paletteOpen}>
          <h2>Node palette</h2>
          <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
            Add by clicking or dragging. One of each type.
          </p>
          {pipelineNodeOrder.map((k) => (
            <Button
              key={k}
              variant="outline"
              draggable={!nodes.some((n) => n.data.config.type === k)}
              disabled={nodes.some((n) => n.data.config.type === k)}
              onDragStart={(e) => e.dataTransfer.setData('application/rag-node', k)}
              onClick={() => onAddNode(k)}
            >
              Add {getNodeLabel(k)}
            </Button>
          ))}
          <Button variant="outline" onClick={onRestoreTemplate}>
            Restore template
          </Button>
        </div>
      </div>
      <div
        ref={canvasRef}
        className="pipeline-canvas h-full min-w-0 min-h-0 col-start-1 row-start-1"
        aria-label="Pipeline canvas"
        onDragOver={(e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = 'move';
        }}
        onDrop={(e) => {
          e.preventDefault();
          const k = e.dataTransfer.getData('application/rag-node') as PipelineNodeKind;
          if (pipelineNodeOrder.includes(k) && flow) {
            onAddNode(k, flow.screenToFlowPosition({ x: e.clientX, y: e.clientY }));
          }
        }}
      >
        <ReactFlow
          fitView
          fitViewOptions={{ padding: 0.12, maxZoom: 1 }}
          nodeTypes={nodeTypes}
          nodes={nodes}
          edges={edges}
          onInit={onInit}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, node) => onNodeSelect(node.id)}
          defaultViewport={{ x: 24, y: 80, zoom: 0.9 }}
          minZoom={0.15}
          nodesDraggable={!busy}
          nodesConnectable={!busy}
          deleteKeyCode={busy ? null : ['Backspace', 'Delete']}
        >
          <Background gap={22} size={1.2} />
          <Controls />
        </ReactFlow>
      </div>
      {children}
    </div>
  );
}
