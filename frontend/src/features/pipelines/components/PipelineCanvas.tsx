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
import { ArrowDown, Plus, SlidersHorizontal } from 'lucide-react';
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
      data-testid="pipeline-editor"
      className="flex flex-col border-t border-border desktop:h-(--editor-canvas) desktop:flex-row"
    >
      <div
        data-slot="flow-canvas"
        className="relative h-(--canvas-compact) min-w-0 bg-background desktop:h-auto desktop:flex-1"
      >
        {/* One wrapping row, so the tools never overlap on narrow screens. The row itself lets
            pointer events through to the canvas; only its controls take them. */}
        <div className="pointer-events-none absolute inset-x-4 top-4 z-10 flex flex-wrap items-start justify-between gap-2 *:pointer-events-auto">
          <div className="flex flex-col items-start gap-2">
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                aria-expanded={paletteOpen}
                aria-controls="node-palette"
                onClick={() => setPaletteOpen((v) => !v)}
              >
                <Plus aria-hidden="true" />
                {paletteOpen ? 'Hide nodes' : 'Nodes'}
              </Button>
              <Button variant="outline" size="sm" onClick={onArrange}>
                <ArrowDown aria-hidden="true" />
                Arrange vertically
              </Button>
            </div>
            <div
              id="node-palette"
              hidden={!paletteOpen}
              className="w-sidebar rounded-card border border-border bg-surface-raised p-4 shadow-popover"
            >
              <h2 className="text-sm font-semibold text-foreground">Node palette</h2>
              <p className="mt-2 text-xs text-foreground-muted">
                Add by clicking or dragging. One of each type.
              </p>
              <div className="mt-4 flex flex-col gap-2">
                {pipelineNodeOrder.map((k) => (
                  <Button
                    key={k}
                    variant="outline"
                    size="sm"
                    className="w-full justify-start"
                    draggable={!nodes.some((n) => n.data.config.type === k)}
                    disabled={nodes.some((n) => n.data.config.type === k)}
                    onDragStart={(e) => e.dataTransfer.setData('application/rag-node', k)}
                    onClick={() => onAddNode(k)}
                  >
                    Add {getNodeLabel(k)}
                  </Button>
                ))}
                <Button variant="ghost" size="sm" className="w-full" onClick={onRestoreTemplate}>
                  Restore template
                </Button>
              </div>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            aria-expanded={inspectorOpen}
            aria-controls="node-settings"
            onClick={() => onInspectorOpenChange(!inspectorOpen)}
          >
            <SlidersHorizontal aria-hidden="true" />
            {inspectorOpen ? 'Hide settings' : 'Node settings'}
          </Button>
        </div>
        <div
          ref={canvasRef}
          data-testid="pipeline-canvas"
          className="size-full"
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
            zoomOnScroll={false}
            preventScrolling={false}
            deleteKeyCode={busy ? null : ['Backspace', 'Delete']}
          >
            <Background gap={24} size={1} />
            <Controls />
          </ReactFlow>
        </div>
      </div>
      {children}
    </div>
  );
}
