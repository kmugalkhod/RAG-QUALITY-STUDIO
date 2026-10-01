import { useEffect, useRef, useState, type ComponentProps, type ReactNode } from 'react';
import {
  Background,
  Controls,
  ReactFlow,
  useNodesInitialized,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type NodeChange,
  type ReactFlowInstance,
  type XYPosition,
} from '@xyflow/react';
import { ArrowDownUp, Maximize, PanelRight, PanelRightClose, Plus, X } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '../../../components/ui/tooltip';
import { getNodeLabel, pipelineNodeOrder, type PipelineNodeKind } from '../model';
import { WorkflowNode, type FlowNode } from './WorkflowNode';

const nodeTypes = { workflow: WorkflowNode };
export const FIT_VIEW = { padding: 0.15, maxZoom: 1 };

interface PipelineCanvasProps {
  nodes: FlowNode[];
  edges: Edge[];
  flow?: ReactFlowInstance<FlowNode>;
  // Changes when a version, template or arrangement replaces the layout; each change refits.
  layoutKey: string;
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

// React Flow's fitView prop runs once at mount, before the editor has loaded any nodes. Fit
// here instead, once the current layout's nodes are measured.
function FitOnLayout({ layoutKey }: { layoutKey: string }) {
  const initialized = useNodesInitialized();
  const { fitView } = useReactFlow();
  const fitted = useRef('');
  useEffect(() => {
    if (!initialized || fitted.current === layoutKey) {
      return;
    }
    fitted.current = layoutKey;
    const frame = requestAnimationFrame(() => void fitView(FIT_VIEW));
    return () => cancelAnimationFrame(frame);
  }, [initialized, layoutKey, fitView]);
  return null;
}

function RailButton({
  label,
  hint,
  children,
  ...props
}: { label: string; hint?: string; children: ReactNode } & ComponentProps<typeof Button>) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="sm" icon aria-label={label} {...props}>
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="right">{hint ? `${label} · ${hint}` : label}</TooltipContent>
    </Tooltip>
  );
}

export function PipelineCanvas({
  nodes,
  edges,
  flow,
  layoutKey,
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
  // Refit when the canvas itself resizes, for example when the settings panel opens or closes.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !flow) {
      return;
    }
    let frame = 0;
    let first = true;
    const observer = new ResizeObserver(() => {
      // The first callback reports the initial size; FitOnLayout owns the initial fit.
      if (first) {
        first = false;
        return;
      }
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => void flow.fitView(FIT_VIEW));
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
        {/* Canvas tools in one slim rail, so nothing covers the node cards. The palette opens
            beside the rail. */}
        <div className="pointer-events-none absolute top-4 left-4 z-10 flex items-start gap-2 *:pointer-events-auto">
          <div
            role="toolbar"
            aria-label="Canvas tools"
            aria-orientation="vertical"
            className="flex flex-col gap-1 rounded-card border border-border bg-surface p-1 shadow-popover"
          >
            <RailButton
              label={paletteOpen ? 'Hide nodes' : 'Nodes'}
              aria-expanded={paletteOpen}
              aria-controls="node-palette"
              onClick={() => setPaletteOpen((v) => !v)}
            >
              {paletteOpen ? <X aria-hidden="true" /> : <Plus aria-hidden="true" />}
            </RailButton>
            <RailButton label="Arrange vertically" onClick={onArrange}>
              <ArrowDownUp aria-hidden="true" />
            </RailButton>
            <RailButton
              label="Fit view"
              hint="Ctrl or ⌘ + scroll zooms"
              onClick={() => void flow?.fitView(FIT_VIEW)}
            >
              <Maximize aria-hidden="true" />
            </RailButton>
            <div className="mx-1 border-t border-border" />
            <RailButton
              label={inspectorOpen ? 'Hide settings' : 'Node settings'}
              aria-expanded={inspectorOpen}
              aria-controls="node-settings"
              onClick={() => onInspectorOpenChange(!inspectorOpen)}
            >
              {inspectorOpen ? (
                <PanelRightClose aria-hidden="true" />
              ) : (
                <PanelRight aria-hidden="true" />
              )}
            </RailButton>
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
            nodeTypes={nodeTypes}
            nodes={nodes}
            edges={edges}
            onInit={onInit}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, node) => onNodeSelect(node.id)}
            minZoom={0.15}
            maxZoom={1.5}
            nodesDraggable={!busy}
            nodesConnectable={!busy}
            // Plain scrolling keeps scrolling the page; Ctrl or Cmd with scroll zooms.
            zoomOnScroll={false}
            preventScrolling={false}
            deleteKeyCode={busy ? null : ['Backspace', 'Delete']}
          >
            <FitOnLayout layoutKey={layoutKey} />
            <Background gap={24} size={1} />
            {/* The rail already offers Fit view, so the zoom controls omit it. */}
            <Controls position="bottom-left" orientation="horizontal" showFitView={false} />
          </ReactFlow>
        </div>
      </div>
      {children}
    </div>
  );
}
