import { RetrievalSettingsForm } from '../retrieval/RetrievalSettingsForm';
import { defaultRetrieval, nodeRetrieval, retrievalSummary } from '../retrieval/settings';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ReactFlow, Background, Controls, addEdge, useNodesState, useEdgesState, useUpdateNodeInternals, Position, Handle, type NodeProps, type Node, type Edge, type ReactFlowInstance } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { MessageSquare, Search, TextQuote, Cpu, CheckCheck, ArrowDown, Play, Save } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { listIndexes, type IndexVersion } from '../documents/indexApi';
import { useUnsavedChanges } from '../../app/navigation';
import * as api from './api';

type FlowNode = Node<{ label: string; config: api.ExecutionNode; vertical: boolean }>;
const label = (k: api.Kind) => k === 'llm' ? 'LLM' : k[0].toUpperCase() + k.slice(1);
const errorText = (e: unknown) => e instanceof Error ? e.message : 'Request failed.';
function WorkflowNode({ id, data, selected }: NodeProps<FlowNode>) {
  const updateNodeInternals = useUpdateNodeInternals();
  useEffect(() => { updateNodeInternals(id); }, [id, data.vertical, updateNodeInternals]);
  const c = data.config;
  const Icon = { question: MessageSquare, retriever: Search, prompt: TextQuote, llm: Cpu, answer: CheckCheck }[c.type];
  const detail = c.type === 'retriever' ? `${retrievalSummary(nodeRetrieval(c))} · ${c.index_id ? 'Documents selected' : 'Choose documents'}` : c.type === 'llm' ? c.model || 'Choose a model' : c.type === 'prompt' ? 'Answer with evidence' : c.type === 'question' ? 'User input · single turn' : 'Response + citations';
  return <div className={`workflow-node ${data.vertical ? 'vertical-node' : 'horizontal-node'}${selected ? ' workflow-selected' : ''}`}>
    {c.type !== 'question' && <Handle type="target" position={data.vertical ? Position.Top : Position.Left}/>}
    <Icon className="node-symbol" size={22}/><div className="node-copy"><strong>{data.label}</strong><div className="workflow-node-content">{detail}</div></div>
    {c.type !== 'answer' && <Handle type="source" position={data.vertical ? Position.Bottom : Position.Right}/>}
  </div>;
}
const nodeTypes = { workflow: WorkflowNode };
function flowNode(config: api.ExecutionNode, position: { x: number; y: number }, vertical = true): FlowNode {
  return { id: config.id, ariaLabel: `${label(config.type)} node`, type: 'workflow', position, sourcePosition: Position.Right, targetPosition: Position.Left, data: { label: label(config.type), config, vertical } };
}
export function PipelineEditor({ projectId, pipelineId, versionId = '' }: { projectId: string; pipelineId: string; versionId?: string }) {
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [flow, setFlow] = useState<ReactFlowInstance<FlowNode>>();
  const canvasRef = useRef<HTMLDivElement>(null);
  const flowRef = useRef(flow);
  flowRef.current = flow;
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !flow) return;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => { void flow.fitView({ padding: 0.18, maxZoom: 1 }); });
    });
    observer.observe(canvas);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, [flow]);
  const [opts, setOpts] = useState<api.Options>();
  const [indexes, setIndexes] = useState<IndexVersion[]>([]);
  const [versions, setVersions] = useState<api.Version[]>([]);
  const [saved, setSaved] = useState<api.Version>();
  const [baseline, setBaseline] = useState('');
  const [name, setName] = useState('Untitled pipeline');
  const [selected, setSelected] = useState('retriever');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const execution: api.Execution = { schema_version: 2, nodes: nodes.map(n => n.data.config), edges: edges.map(({ source, target }) => ({ source, target })) };
  const draft: api.Draft = { name, execution, layout: { positions: Object.fromEntries(nodes.map(n => [n.id, n.position])) } };
  const serialized = api.canonical(draft);
  const dirty = (nodes.length > 0 || !!saved) && serialized !== baseline;
  useUnsavedChanges(dirty);
  const errors = api.validate(execution, opts, indexes.map(i => i.id));
  const config = nodes.find(n => n.id === selected)?.data.config;
  function defaults(kind: api.Kind): api.ExecutionNode {
    return { id: kind, type: kind, ...(kind === 'retriever' ? { index_id: '', retrieval: defaultRetrieval() } : kind === 'prompt' ? { template: opts?.template ?? 'Answer concisely.\nQuestion: {question}\nRetrieved context: {context}' } : kind === 'llm' ? { model: opts?.models[0] ?? '', max_tokens: opts?.max_tokens ?? 1024, temperature: 0 } : {}) };
  }
  function template() {
    setNodes(api.order.map((k, i) => ({ ...flowNode(defaults(k), { x: 80, y: i * 116 + 40 }), selected: k === 'retriever' })));
    requestAnimationFrame(() => { void flow?.fitView({ padding: 0.12, maxZoom: 1 }); });
    setEdges(api.order.slice(1).map((k, i) => ({ id: `${api.order[i]}-${k}`, source: api.order[i], target: k })));
    setSelected('retriever');
  }
  const open = useCallback((v: api.Version) => {
    window.history.replaceState(null, '', `#/projects/${v.project_id}/pipelines/${v.pipeline_id}?version=${v.id}`);
    const positions = Object.values(v.layout.positions);
    const vertical = Math.max(...positions.map(p => p.y)) - Math.min(...positions.map(p => p.y)) > Math.max(...positions.map(p => p.x)) - Math.min(...positions.map(p => p.x));
    setName(v.name); setNodes(api.editableExecution(v.execution).nodes.map((n, i) => ({ ...flowNode(n, v.layout.positions[n.id], vertical), selected: i === 0 })));
    const position = v.layout.positions[v.execution.nodes[0].id];
    void flowRef.current?.setCenter(position.x + 160, position.y + 42, { zoom: 0.9 });
    setEdges(v.execution.edges.map((e, i) => ({ ...e, id: `edge-${i}` })));
    setSaved(v); setBaseline(api.canonical({ name: v.name, execution: api.editableExecution(v.execution), layout: v.layout })); setSelected(v.execution.nodes[0].id);
  }, [setNodes, setEdges]);
  useEffect(() => {
    let disposed = false;
    setLoading(true);
    void Promise.all([api.options(projectId), api.allPages(o => listIndexes(projectId, o)), pipelineId === 'new' ? Promise.resolve([]) : api.allPages(o => api.versions(projectId, pipelineId, o))]).then(([o, ix, vs]) => {
      if (disposed) return;
      setOpts(o); setIndexes(ix.filter(i => i.status === 'succeeded')); setError('');
      if (pipelineId !== 'new') { if (!vs.length) throw new Error('No saved versions found.'); setVersions(vs); const linked = new URLSearchParams(window.location.hash.split('?')[1] || '').get('version') || versionId; const target = linked ? vs.find(v => v.id === linked) : vs[0]; if (!target) throw new Error('The linked pipeline version is unavailable. Open this pipeline from the pipeline list.'); open(target); }
      else { const configs = api.order.map(k => ({ id: k, type: k, ...(k === 'retriever' ? { index_id: '', retrieval: defaultRetrieval() } : k === 'prompt' ? { template: o.template } : k === 'llm' ? { model: o.models[0] || '', max_tokens: o.max_tokens, temperature: 0 } : {}) })); setNodes(configs.map((n, i) => flowNode(n, { x: 80, y: i * 116 + 40 }))); setEdges(api.order.slice(1).map((k, i) => ({ id: `${api.order[i]}-${k}`, source: api.order[i], target: k }))); }
    }).catch(e => { if (!disposed) setError(errorText(e)); }).finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [projectId, pipelineId, versionId, refresh, open, setNodes, setEdges]);
  async function action(fn: () => Promise<void>) { setBusy(true); setError(''); try { await fn(); } catch (e) { setError(`${errorText(e)} If a save or run response was interrupted, refresh pipelines or runs before retrying.`); } finally { setBusy(false); } }
  const running = false;
  const saveReasons = loading ? ['Loading the available indexes and models.'] : running ? ['Wait for the current run to finish.'] : busy ? ['Wait for the current request to finish.'] : !nodes.length && !saved ? ['Choose New pipeline to start.'] : [
    ...errors,
    ...(!name.trim() ? ['Enter a pipeline name.'] : []),
    ...(opts?.error ? [opts.error] : []),
    ...(!opts ? ['Server options could not be loaded. Choose Refresh options to retry.'] : []),
    ...(!dirty && saved ? ['Version saved. Test it in Playground.'] : []),
  ];
  function selectNode(id: string, center = true) {
    setInspectorOpen(true); setSelected(id); setNodes(ns => ns.map(n => ({ ...n, selected: n.id === id })));
    const node = nodes.find(n => n.id === id);
    if (center && node) void flow?.setCenter(node.position.x + 160, node.position.y + 42, { zoom: 0.9 });
  }
  function arrangeVertically() {
    setNodes(ns => ns.map(n => ({ ...n, position: { x: 80, y: api.order.indexOf(n.data.config.type) * 116 + 40 }, data: { ...n.data, vertical: true } })));
    requestAnimationFrame(() => { void flow?.fitView({ padding: 0.12, maxZoom: 1 }); });
  }
  function update(values: Partial<api.ExecutionNode>) { setNodes(ns => ns.map(n => n.id === selected ? { ...n, data: { ...n.data, config: { ...n.data.config, ...values } } } : n)); }
  function add(kind: api.Kind, position = { x: 80, y: 80 }) {
    if (nodes.some(n => n.data.config.type === kind)) return;
    setNodes(ns => [...ns.map(n => ({ ...n, selected: false })), { ...flowNode(defaults(kind), position), selected: true }]); setSelected(kind);
    void flow?.setCenter(position.x + 160, position.y + 42, { zoom: 0.9 });
  }
  return <div className="editor-workspace">
    <a className="back-link" href={`#/projects/${projectId}/pipelines`}>All pipelines</a>
    <div className="editor-title"><h1>Pipeline editor</h1><span>Question → grounded answer</span></div>
    {loading && <p role="status">Loading pipeline and server configuration…</p>}
    {error && <p role="alert" className="error-message">{error}</p>}
    {error && <Button variant="outline" onClick={() => setRefresh(r => r + 1)}>Retry loading pipeline</Button>}
    <fieldset className="pipeline-fields" disabled={busy || !!running || loading}>
      <div className="pipeline-toolbar"><label>Pipeline name<input value={name} maxLength={120} onChange={e => setName(e.target.value)}/></label>
        <label>Saved version<select aria-label="Saved version" value={saved?.id ?? ''} disabled={dirty} onChange={e => { const v = versions.find(v => v.id === e.target.value); if (v) open(v); }}><option value="">Not saved</option>{versions.map(v => <option key={v.id} value={v.id}>Version {v.version}</option>)}</select></label>
        <span className={`draft-status ${dirty ? 'is-dirty' : ''}`} role="status">{dirty ? 'Unsaved changes' : saved ? `Saved version ${saved.version}` : 'No saved version'}</span>
        <Button variant={dirty ? 'default' : 'outline'} aria-describedby="save-guidance" disabled={saveReasons.length > 0} onClick={() => void action(async () => { const v = await api.save(projectId, draft, saved?.pipeline_id); window.history.replaceState(null, '', `#/projects/${projectId}/pipelines/${v.pipeline_id}`); open(v); setVersions(await api.allPages(o => api.versions(projectId, v.pipeline_id, o))); })}><Save size={15}/>Save version</Button>
        <Button variant={saved && !dirty ? 'default' : 'outline'} disabled={!saved || dirty || busy} onClick={() => { if (saved) window.location.hash = `/projects/${projectId}/playground?pipeline=${saved.pipeline_id}&version=${saved.id}`; }}><Play size={15}/>Open Playground</Button>
        <Button variant="outline" disabled={!saved || dirty} onClick={() => void action(async () => { const v = await api.save(projectId, { ...draft, name: `${name.slice(0, 113)} (copy)` }); window.history.replaceState(null, '', `#/projects/${projectId}/pipelines/${v.pipeline_id}`); open(v); setVersions([v]); })}>Duplicate pipeline</Button>
        <Button variant="outline" disabled={!dirty} onClick={() => { if (saved) open(saved); else { setNodes([]); setEdges([]); setBaseline(''); } }}>Discard changes</Button>
      </div>
      <section id="save-guidance" className="pipeline-validation" aria-label="Graph validation" aria-live="polite">
        {saveReasons.length ? <><h2>{saved && !dirty && !loading && !busy && !running ? 'Already saved' : 'To enable Save version'}</h2><ul>{saveReasons.map(reason => <li key={reason}>{reason}</li>)}</ul></> : <p>Ready to save: all five nodes are connected and configured.</p>}
        {errors.some(reason => reason.startsWith('Retriever: choose')) && <Button variant="outline" disabled={busy || running || loading} onClick={() => { const retriever = nodes.find(n => n.data.config.type === 'retriever'); if (retriever) { selectNode(retriever.id); requestAnimationFrame(() => { const input = document.querySelector<HTMLSelectElement>('[aria-label="Documents to search"]'); input?.focus(); input?.scrollIntoView({ block: 'center' }); }); } }}>Choose documents to search</Button>}
      </section>
      <div className={`pipeline-editor ${paletteOpen ? 'palette-open' : ''} ${inspectorOpen ? 'inspector-open' : ''}`}>
        <Button className="inspector-toggle" variant="outline" aria-expanded={inspectorOpen} aria-controls="node-settings" onClick={() => setInspectorOpen(v => !v)}>{inspectorOpen ? 'Hide settings' : 'Node settings'}</Button>
        <div className="pipeline-palette"><div className="canvas-tools"><Button variant="outline" aria-expanded={paletteOpen} onClick={() => setPaletteOpen(v => !v)}>{paletteOpen ? 'Hide nodes' : 'Nodes'}</Button><Button variant="outline" onClick={arrangeVertically}><ArrowDown size={14}/>Arrange vertically</Button></div><div hidden={!paletteOpen}><h2>Node palette</h2><p className="field-hint">Add by clicking or dragging. One of each type.</p>{api.order.map(k => <Button key={k} variant="outline" draggable={!nodes.some(n => n.data.config.type === k)} disabled={nodes.some(n => n.data.config.type === k)} onDragStart={e => e.dataTransfer.setData('application/rag-node', k)} onClick={() => add(k)}>Add {label(k)}</Button>)}<Button variant="outline" onClick={template}>Restore template</Button></div></div>
        <div ref={canvasRef} className="pipeline-canvas" aria-label="Pipeline canvas" onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }} onDrop={e => { e.preventDefault(); const k = e.dataTransfer.getData('application/rag-node') as api.Kind; if (api.order.includes(k) && flow) add(k, flow.screenToFlowPosition({ x: e.clientX, y: e.clientY })); }}>
          <ReactFlow fitView fitViewOptions={{ padding: 0.12, maxZoom: 1 }} nodeTypes={nodeTypes} nodes={nodes} edges={edges} onInit={setFlow} onNodesChange={changes => { onNodesChange(changes); const picked = changes.find(c => c.type === 'select' && c.selected); if (picked?.type === 'select') selectNode(picked.id, false); else if (changes.some(c => c.type === 'select' && c.id === selected && !c.selected)) setSelected(''); }} onEdgesChange={onEdgesChange} onConnect={c => setEdges(es => addEdge(c, es))} onNodeClick={(_, n) => selectNode(n.id, false)} defaultViewport={{ x: 24, y: 80, zoom: 0.9 }} minZoom={0.15} nodesDraggable={!busy && !running} nodesConnectable={!busy && !running} deleteKeyCode={busy || running ? null : ['Backspace', 'Delete']}><Background gap={22} size={1.2}/><Controls/></ReactFlow>
        </div>
        <aside id="node-settings" className="pipeline-config" hidden={!inspectorOpen}><h2>{config ? label(config.type) : 'Node settings'}</h2><label>Selected node<select aria-label="Selected node" value={selected} onChange={e => selectNode(e.target.value)}><option value="">Select a node</option>{nodes.map(n => <option key={n.id} value={n.id}>{n.data.label}</option>)}</select></label>
          {config?.type === 'retriever' && <><h3>Inputs</h3><label>Documents to search<select aria-label="Documents to search" value={config.index_id} onChange={e => update({ index_id: e.target.value })}><option value="">Choose a prepared document set</option>{indexes.map(i => <option key={i.id} value={i.id}>Document set · Version {i.version} · {i.chunk_count} passages</option>)}</select></label>{!indexes.length && <p>Prepare a document set in the Knowledge Base to start asking questions.</p>}<RetrievalSettingsForm value={nodeRetrieval(config)} onChange={retrieval => update({ retrieval })}/><p className="field-hint">Search uses this saved document set. Changing it does not change earlier answers.</p></>}
          {config?.type === 'prompt' && <><label>Answer instructions<textarea rows={9} maxLength={8000} value={config.template} onChange={e => update({ template: e.target.value })}/></label><p className="field-hint">Use {'{question}'} and {'{context}'}. These are literal substitutions, with no expressions or code. Context is labeled evidence. Source labels, citation rules and grounding instructions are controlled by the application.</p></>}
          {config?.type === 'llm' && <><label>Chat model<select aria-label="Chat model" value={config.model} onChange={e => update({ model: e.target.value })}><option value="">Select a model</option>{opts?.models.map(m => <option key={m}>{m}</option>)}</select></label><label>Maximum output tokens<input type="number" min={128} max={8192} value={config.max_tokens ?? ''} onChange={e => update({ max_tokens: e.target.valueAsNumber })}/></label><label>Temperature<input type="number" min={0} max={2} step={0.1} value={config.temperature ?? ''} onChange={e => update({ temperature: e.target.valueAsNumber })}/></label><p className="field-hint">Server context budget: {opts?.context_tokens} tokens. Credentials stay on the server.</p></>}
          {config?.type === 'question' && <p>Each question is independent. Enter your question in Playground after saving this pipeline.</p>}{config?.type === 'answer' && <p>Displays the generated answer with checked source references, evidence and usage.</p>}
          {config && <Button variant="outline" onClick={() => { setNodes(ns => ns.filter(n => n.id !== selected)); setEdges(es => es.filter(e => e.source !== selected && e.target !== selected)); setSelected(''); }}>Delete selected node</Button>}
        </aside>
      </div>
    </fieldset>

  </div>;
}
