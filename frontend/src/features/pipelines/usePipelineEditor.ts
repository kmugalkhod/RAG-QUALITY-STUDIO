import { useCallback, useEffect, useRef, useState } from 'react';
import {
  addEdge,
  Position,
  useEdgesState,
  useNodesState,
  type Edge,
  type NodeChange,
  type ReactFlowInstance,
} from '@xyflow/react';
import { useUnsavedChanges } from '../../app/navigation';
import { allPages } from '../../lib/pagination';
import { listIndexes } from '../documents/indexApi';
import type { IndexVersion } from '../documents/model';
import * as api from './api';
import type { FlowNode } from './components/WorkflowNode';
import {
  canonical,
  createEditableExecution,
  getNodeLabel,
  pipelineNodeOrder,
  validatePipelineExecution,
  type PipelineDraft,
  type PipelineExecution,
  type PipelineNodeConfig,
  type PipelineNodeKind,
  type PipelineOptions,
  type PipelineVersion,
} from './model';
import { createNode, createPipelineDraft } from './pipelineTemplate';

const errorText = (cause: unknown) => (cause instanceof Error ? cause.message : 'Request failed.');
function flowNode(
  config: PipelineNodeConfig,
  position: { x: number; y: number },
  vertical = true,
): FlowNode {
  return {
    id: config.id,
    ariaLabel: `${getNodeLabel(config.type)} node`,
    type: 'workflow',
    position,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { label: getNodeLabel(config.type), config, vertical },
  };
}

export function usePipelineEditor(projectId: string, pipelineId: string, versionId: string) {
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [flow, setFlow] = useState<ReactFlowInstance<FlowNode>>();
  const flowRef = useRef(flow);
  flowRef.current = flow;
  const [options, setOptions] = useState<PipelineOptions>();
  const [indexes, setIndexes] = useState<IndexVersion[]>([]);
  const [versions, setVersions] = useState<PipelineVersion[]>([]);
  const [saved, setSaved] = useState<PipelineVersion>();
  const [baseline, setBaseline] = useState('');
  const [name, setName] = useState('Untitled pipeline');
  const [selected, setSelected] = useState('retriever');
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const execution: PipelineExecution = {
    schema_version: 2,
    nodes: nodes.map((node) => node.data.config),
    edges: edges.map(({ source, target }) => ({ source, target })),
  };
  const draft: PipelineDraft = {
    name,
    execution,
    layout: { positions: Object.fromEntries(nodes.map((node) => [node.id, node.position])) },
  };
  const dirty = (nodes.length > 0 || !!saved) && canonical(draft) !== baseline;
  const errors = validatePipelineExecution(
    execution,
    options,
    indexes.map((index) => index.id),
  );
  const config = nodes.find((node) => node.id === selected)?.data.config;
  useUnsavedChanges(dirty);

  const open = useCallback(
    (version: PipelineVersion) => {
      window.history.replaceState(
        null,
        '',
        `#/projects/${version.project_id}/pipelines/${version.pipeline_id}?version=${version.id}`,
      );
      const positions = Object.values(version.layout.positions);
      const vertical =
        Math.max(...positions.map((position) => position.y)) -
          Math.min(...positions.map((position) => position.y)) >
        Math.max(...positions.map((position) => position.x)) -
          Math.min(...positions.map((position) => position.x));
      setName(version.name);
      setNodes(
        createEditableExecution(version.execution).nodes.map((node, index) => ({
          ...flowNode(node, version.layout.positions[node.id], vertical),
          selected: index === 0,
        })),
      );
      const position = version.layout.positions[version.execution.nodes[0].id];
      void flowRef.current?.setCenter(position.x + 160, position.y + 42, { zoom: 0.9 });
      setEdges(version.execution.edges.map((edge, index) => ({ ...edge, id: `edge-${index}` })));
      setSaved(version);
      setBaseline(
        canonical({
          name: version.name,
          execution: createEditableExecution(version.execution),
          layout: version.layout,
        }),
      );
      setSelected(version.execution.nodes[0].id);
    },
    [setNodes, setEdges],
  );

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    void Promise.all([
      api.getPipelineOptions(projectId),
      allPages((offset) => listIndexes(projectId, offset)),
      pipelineId === 'new'
        ? Promise.resolve([])
        : allPages((offset) => api.listPipelineVersions(projectId, pipelineId, offset)),
    ])
      .then(([serverOptions, indexVersions, pipelineVersions]) => {
        if (disposed) {
          return;
        }
        setOptions(serverOptions);
        setIndexes(indexVersions.filter((index) => index.status === 'succeeded'));
        setError('');
        if (pipelineId === 'new') {
          const template = createPipelineDraft(serverOptions, 'Untitled pipeline');
          setNodes(
            template.execution.nodes.map((node) =>
              flowNode(node, template.layout.positions[node.id]),
            ),
          );
          setEdges(
            template.execution.edges.map((edge) => ({
              ...edge,
              id: `${edge.source}-${edge.target}`,
            })),
          );
          return;
        }
        if (!pipelineVersions.length) {
          throw new Error('No saved versions found.');
        }
        setVersions(pipelineVersions);
        const linked =
          new URLSearchParams(window.location.hash.split('?')[1] || '').get('version') || versionId;
        const target = linked
          ? pipelineVersions.find((version) => version.id === linked)
          : pipelineVersions[0];
        if (!target) {
          throw new Error(
            'The linked pipeline version is unavailable. Open it from the pipeline list.',
          );
        }
        open(target);
      })
      .catch((cause) => {
        if (!disposed) {
          setError(errorText(cause));
        }
      })
      .finally(() => {
        if (!disposed) {
          setLoading(false);
        }
      });
    return () => {
      disposed = true;
    };
  }, [projectId, pipelineId, versionId, refresh, open, setNodes, setEdges]);

  async function action(work: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await work();
    } catch (cause) {
      setError(
        `${errorText(cause)} Refresh saved pipelines before retrying an interrupted request.`,
      );
    } finally {
      setBusy(false);
    }
  }
  function selectNode(id: string, center = true) {
    setInspectorOpen(true);
    setSelected(id);
    setNodes((current) => current.map((node) => ({ ...node, selected: node.id === id })));
    const node = nodes.find((value) => value.id === id);
    if (center && node) {
      void flow?.setCenter(node.position.x + 160, node.position.y + 42, { zoom: 0.9 });
    }
  }
  function updateNode(values: Partial<PipelineNodeConfig>) {
    setNodes((current) =>
      current.map((node) =>
        node.id === selected
          ? { ...node, data: { ...node.data, config: { ...node.data.config, ...values } } }
          : node,
      ),
    );
  }
  function addNode(kind: PipelineNodeKind, position = { x: 80, y: 80 }) {
    if (nodes.some((node) => node.data.config.type === kind)) {
      return;
    }
    setNodes((current) => [
      ...current.map((node) => ({ ...node, selected: false })),
      { ...flowNode(createNode(kind, options), position), selected: true },
    ]);
    setSelected(kind);
    void flow?.setCenter(position.x + 160, position.y + 42, { zoom: 0.9 });
  }
  function changeNodes(changes: NodeChange<FlowNode>[]) {
    onNodesChange(changes);
    const picked = changes.find((change) => change.type === 'select' && change.selected);
    if (picked?.type === 'select') {
      selectNode(picked.id, false);
    } else if (
      changes.some(
        (change) => change.type === 'select' && change.id === selected && !change.selected,
      )
    ) {
      setSelected('');
    }
  }
  function arrange() {
    setNodes((current) =>
      current.map((node) => ({
        ...node,
        position: { x: 80, y: pipelineNodeOrder.indexOf(node.data.config.type) * 116 + 40 },
        data: { ...node.data, vertical: true },
      })),
    );
    requestAnimationFrame(() => void flow?.fitView({ padding: 0.12, maxZoom: 1 }));
  }
  function restoreTemplate() {
    const template = createPipelineDraft(options, name);
    setNodes(
      template.execution.nodes.map((node) => ({
        ...flowNode(node, template.layout.positions[node.id]),
        selected: node.type === 'retriever',
      })),
    );
    setEdges(
      template.execution.edges.map((edge) => ({ ...edge, id: `${edge.source}-${edge.target}` })),
    );
    setSelected('retriever');
    requestAnimationFrame(() => void flow?.fitView({ padding: 0.12, maxZoom: 1 }));
  }
  function save() {
    void action(async () => {
      const version = saved
        ? await api.createPipelineVersion(projectId, saved.pipeline_id, draft)
        : await api.createPipeline(projectId, draft);
      open(version);
      setVersions(
        await allPages((offset) =>
          api.listPipelineVersions(projectId, version.pipeline_id, offset),
        ),
      );
    });
  }
  function duplicate() {
    void action(async () => {
      const version = await api.createPipeline(projectId, {
        ...draft,
        name: `${name.slice(0, 113)} (copy)`,
      });
      open(version);
      setVersions([version]);
    });
  }
  function discard() {
    if (saved) {
      open(saved);
    } else {
      setNodes([]);
      setEdges([]);
      setBaseline('');
    }
  }
  function removeNode() {
    setNodes((current) => current.filter((node) => node.id !== selected));
    setEdges((current) =>
      current.filter((edge) => edge.source !== selected && edge.target !== selected),
    );
    setSelected('');
  }
  function openPlayground() {
    if (saved) {
      window.location.hash = `/projects/${projectId}/playground?pipeline=${saved.pipeline_id}&version=${saved.id}`;
    }
  }
  function chooseDocuments() {
    const retriever = nodes.find((node) => node.data.config.type === 'retriever');
    if (!retriever) {
      return;
    }
    selectNode(retriever.id);
    requestAnimationFrame(() =>
      document.querySelector<HTMLSelectElement>('[aria-label="Documents to search"]')?.focus(),
    );
  }

  const saveReasons = loading
    ? ['Loading the available indexes and models.']
    : busy
      ? ['Wait for the current request to finish.']
      : !nodes.length && !saved
        ? ['Choose New pipeline to start.']
        : [
            ...errors,
            ...(!name.trim() ? ['Enter a pipeline name.'] : []),
            ...(options?.error ? [options.error] : []),
            ...(!options
              ? ['Server options could not be loaded. Choose Refresh options to retry.']
              : []),
            ...(!dirty && saved ? ['Version saved. Test it in Playground.'] : []),
          ];
  return {
    nodes,
    edges,
    flow,
    options,
    indexes,
    versions,
    saved,
    name,
    selected,
    inspectorOpen,
    busy,
    loading,
    error,
    dirty,
    errors,
    config,
    saveReasons,
    setName,
    setFlow,
    setInspectorOpen,
    onEdgesChange,
    connect: (connection: Parameters<typeof addEdge>[0]) =>
      setEdges((current) => addEdge(connection, current)),
    changeNodes,
    selectNode,
    updateNode,
    addNode,
    arrange,
    restoreTemplate,
    save,
    duplicate,
    discard,
    removeNode,
    openPlayground,
    chooseDocuments,
    open,
    retry: () => setRefresh((value) => value + 1),
  };
}
