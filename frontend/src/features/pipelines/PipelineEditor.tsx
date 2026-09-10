import { useEffect, useState } from 'react';
import { ReactFlow, Background, Controls, addEdge, useNodesState, useEdgesState, Position, Handle, type NodeProps, type Node, type Edge, type ReactFlowInstance } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Button } from '../../components/ui/button';
import { listIndexes, type IndexVersion } from '../documents/indexApi';
import { RunResult } from '../playground/Playground';
import { listRuns, type QueryRun } from '../playground/api';
import * as api from './api';

type FlowNode = Node<{ label: string; config: api.ExecutionNode }>;
const label = (k: api.Kind) => k === 'llm' ? 'LLM' : k[0].toUpperCase() + k.slice(1);
const errorText = (e: unknown) => e instanceof Error ? e.message : 'Request failed.';
const descriptions: Record<api.Kind, string> = { question: 'Independent user input', retriever: 'Dense vector retrieval', prompt: 'Grounded answer instructions', llm: 'OpenRouter generation', answer: 'Citations and evidence' };
function WorkflowNode({ data, selected }: NodeProps<FlowNode>) {
  const c = data.config;
  const detail = c.type === 'retriever' ? `Top k ${c.top_k} · ${c.index_id ? 'Index selected' : 'Choose an index'}` : c.type === 'llm' ? c.model || 'Choose a model' : c.type === 'prompt' ? 'Question + retrieved context' : c.type === 'question' ? 'Text → retrieval' : 'Answer → source inspection';
  return <div className={`workflow-node${selected ? ' workflow-selected' : ''}`}>
    {c.type !== 'question' && <Handle type="target" position={Position.Left}/>}
    <header><strong>{data.label}</strong><span>{descriptions[c.type]}</span></header>
    <div className="workflow-node-content">{detail}</div>
    <footer>{c.type === 'llm' ? `${c.max_tokens} output tokens · Temperature ${c.temperature}` : 'Select to configure'}</footer>
    {c.type !== 'answer' && <Handle type="source" position={Position.Right}/>}
  </div>;
}
const nodeTypes = { workflow: WorkflowNode };
function flowNode(config: api.ExecutionNode, position: { x: number; y: number }): FlowNode {
  return { id: config.id, ariaLabel: `${label(config.type)} node`, type: 'workflow', position, sourcePosition: Position.Right, targetPosition: Position.Left, data: { label: label(config.type), config } };
}
export function PipelineEditor({ projectId }: { projectId: string }) {
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [flow, setFlow] = useState<ReactFlowInstance<FlowNode>>();
  const [opts, setOpts] = useState<api.Options>();
  const [indexes, setIndexes] = useState<IndexVersion[]>([]);
  const [pipelines, setPipelines] = useState<api.Pipeline[]>([]);
  const [versions, setVersions] = useState<api.Version[]>([]);
  const [saved, setSaved] = useState<api.Version>();
  const [baseline, setBaseline] = useState('');
  const [name, setName] = useState('Untitled pipeline');
  const [selected, setSelected] = useState('retriever');
  const [question, setQuestion] = useState('');
  const [run, setRun] = useState<QueryRun>();
  const [history, setHistory] = useState<QueryRun[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const execution: api.Execution = { schema_version: 1, nodes: nodes.map(n => n.data.config), edges: edges.map(({ source, target }) => ({ source, target })) };
  const draft: api.Draft = { name, execution, layout: { positions: Object.fromEntries(nodes.map(n => [n.id, n.position])) } };
  const serialized = api.canonical(draft);
  const dirty = (nodes.length > 0 || !!saved) && serialized !== baseline;
  const errors = api.validate(execution, opts, indexes.map(i => i.id));
  const config = nodes.find(n => n.id === selected)?.data.config;
  function defaults(kind: api.Kind): api.ExecutionNode {
    return { id: kind, type: kind, ...(kind === 'retriever' ? { index_id: '', top_k: 5 } : kind === 'prompt' ? { template: opts?.template ?? 'Answer concisely.\nQuestion: {question}\nRetrieved context: {context}' } : kind === 'llm' ? { model: opts?.models[0] ?? '', max_tokens: opts?.max_tokens ?? 1024, temperature: 0 } : {}) };
  }
  function template() {
    setNodes(api.order.map((k, i) => ({ ...flowNode(defaults(k), { x: i * 260, y: i % 2 * 100 + 40 }), selected: k === 'retriever' })));
    void flow?.setCenter(370, 210, { zoom: 0.9 });
    setEdges(api.order.slice(1).map((k, i) => ({ id: `${api.order[i]}-${k}`, source: api.order[i], target: k })));
    setSelected('retriever');
  }
  useEffect(() => {
    let disposed = false;
    setLoading(true);
    void Promise.all([api.options(projectId), api.allPages(o => listIndexes(projectId, o)), api.allPages(o => api.list(projectId, o))]).then(([o, ix, ps]) => {
      if (disposed) return;
      setOpts(o); setIndexes(ix.filter(i => i.status === 'succeeded')); setPipelines(ps); setError('');
    }).catch(e => { if (!disposed) setError(errorText(e)); }).finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [projectId, refresh]);
  useEffect(() => {
    const protect = (e: BeforeUnloadEvent) => { if (dirty && nodes.length) { e.preventDefault(); } };
    window.addEventListener('beforeunload', protect); return () => window.removeEventListener('beforeunload', protect);
  }, [dirty, nodes.length]);
  useEffect(() => {
    if (!run || run.status !== 'running') return;
    let disposed = false;
    const timer = setInterval(() => { void api.readRun(projectId, run.id).then(r => { if (!disposed) { setRun(r); setError(''); } }).catch(e => { if (!disposed) setError(errorText(e)); }); }, 1000);
    return () => { disposed = true; clearInterval(timer); };
  }, [projectId, run]);
  function open(v: api.Version) {
    setHistory([]);
    setName(v.name); setNodes(v.execution.nodes.map((n, i) => ({ ...flowNode(n, v.layout.positions[n.id]), selected: i === 0 })));
    const position = v.layout.positions[v.execution.nodes[0].id];
    void flow?.setCenter(position.x + 110, position.y + 70, { zoom: 0.9 });
    setEdges(v.execution.edges.map((e, i) => ({ ...e, id: `edge-${i}` })));
    setSaved(v); setBaseline(api.canonical({ name: v.name, execution: v.execution, layout: v.layout })); setSelected(v.execution.nodes[0].id); setRun(undefined);
  }
  async function action(fn: () => Promise<void>) { setBusy(true); setError(''); try { await fn(); } catch (e) { setError(`${errorText(e)} If a save or run response was interrupted, refresh pipelines or runs before retrying.`); } finally { setBusy(false); } }
  const running = run?.status === 'running';
  const saveReasons = loading ? ['Loading the available indexes and models.'] : running ? ['Wait for the current run to finish.'] : busy ? ['Wait for the current request to finish.'] : !nodes.length && !saved ? ['Choose New pipeline to start.'] : [
    ...errors,
    ...(!name.trim() ? ['Enter a pipeline name.'] : []),
    ...(opts?.error ? [opts.error] : []),
    ...(!opts ? ['Server options could not be loaded. Choose Refresh options to retry.'] : []),
    ...(!dirty && saved ? ['This version is already saved. Entering a question does not require a new version; use Run pipeline.'] : []),
  ];
  function selectNode(id: string, center = true) {
    setSelected(id); setNodes(ns => ns.map(n => ({ ...n, selected: n.id === id })));
    const node = nodes.find(n => n.id === id);
    if (center && node) void flow?.setCenter(node.position.x + 110, node.position.y + 70, { zoom: 0.9 });
  }
  function update(values: Partial<api.ExecutionNode>) { setNodes(ns => ns.map(n => n.id === selected ? { ...n, data: { ...n.data, config: { ...n.data.config, ...values } } } : n)); }
  function add(kind: api.Kind, position = { x: 80, y: 80 }) {
    if (nodes.some(n => n.data.config.type === kind)) return;
    setNodes(ns => [...ns.map(n => ({ ...n, selected: false })), { ...flowNode(defaults(kind), position), selected: true }]); setSelected(kind);
    void flow?.setCenter(position.x + 110, position.y + 70, { zoom: 0.9 });
  }
  return <>
    <a className="back-link" href={`#/projects/${projectId}`}>Back to Knowledge Base</a>
    <div className="page-heading"><div><h1>Pipeline editor</h1><p>Configure a grounded answer, save a version, then inspect its evidence.</p></div></div>
    {loading && <p role="status">Loading pipelines and server configuration…</p>}
    {error && <p role="alert" className="error-message">{error}</p>}
    <div className="pipeline-toolbar">
      <Button disabled={loading || busy || running || (dirty && nodes.length > 0)} onClick={() => { setSaved(undefined); setVersions([]); setName('Untitled pipeline'); template(); }}>New pipeline</Button>
      <label>Open pipeline<select aria-label="Open pipeline" disabled={loading || busy || running || (dirty && nodes.length > 0)} value={saved?.pipeline_id ?? ''} onChange={e => { const id = e.target.value; if (id) void action(async () => { const vs = await api.allPages(o => api.versions(projectId, id, o)); setVersions(vs); open(vs[0]); }); }}><option value="">Select a pipeline</option>{pipelines.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <Button variant="outline" disabled={busy || running} onClick={() => setRefresh(r => r + 1)}>Refresh options</Button>
    </div>
    {!nodes.length && !saved && <p>Choose New pipeline for the supported five-node template, or reopen a saved pipeline.</p>}
    <section className="create-panel"><h2>Ask a question</h2><p>{saved ? `Execution selection: version ${saved.version} of ${saved.name}.` : 'Save a valid pipeline to enable execution.'} {dirty && 'Save or discard changes before running.'}</p>
      <form onSubmit={e => { e.preventDefault(); if (saved) void action(async () => setRun(await api.run(projectId, saved, question.trim()))); }}>
        <label htmlFor="pipeline-question">Question</label><textarea id="pipeline-question" placeholder="What would you like to know about your documents?" rows={2} maxLength={8000} value={question} onChange={e => setQuestion(e.target.value)} disabled={busy || running}/>
        <Button type="submit" disabled={busy || running || dirty || !saved || !question.trim()}>Run pipeline</Button>
      </form>
      {busy && <p role="status">Saving or submitting request…</p>}
      {running && <p role="status">Backend status: running. Polling the saved query run…</p>}
    </section>
    {run && <RunResult run={run}/>}
    <fieldset className="pipeline-fields" disabled={busy || !!running || loading}>
      <div className="pipeline-toolbar"><label>Pipeline name<input value={name} maxLength={120} onChange={e => setName(e.target.value)}/></label>
        <label>Saved version<select aria-label="Saved version" value={saved?.id ?? ''} disabled={dirty} onChange={e => { const v = versions.find(v => v.id === e.target.value); if (v) open(v); }}><option value="">Not saved</option>{versions.map(v => <option key={v.id} value={v.id}>Version {v.version}</option>)}</select></label>
        <span role="status">{dirty ? 'Unsaved changes' : saved ? `Saved version ${saved.version}` : 'No saved version'}</span>
        <Button aria-describedby="save-guidance" disabled={saveReasons.length > 0} onClick={() => void action(async () => { const v = await api.save(projectId, draft, saved?.pipeline_id); open(v); setVersions(await api.allPages(o => api.versions(projectId, v.pipeline_id, o))); setPipelines(await api.allPages(o => api.list(projectId, o))); })}>Save version</Button>
        <Button variant="outline" disabled={!saved || dirty} onClick={() => void action(async () => { const v = await api.save(projectId, { ...draft, name: `${name.slice(0, 113)} (copy)` }); open(v); setVersions([v]); setPipelines(await api.allPages(o => api.list(projectId, o))); })}>Duplicate pipeline</Button>
        <Button variant="outline" disabled={!dirty} onClick={() => { if (saved) open(saved); else { setNodes([]); setEdges([]); setBaseline(''); } }}>Discard changes</Button>
      </div>
      <section id="save-guidance" className="pipeline-validation" aria-label="Graph validation" aria-live="polite">
        {saveReasons.length ? <><h2>{saved && !dirty && !loading && !busy && !running ? 'Already saved' : 'To enable Save version'}</h2><ul>{saveReasons.map(reason => <li key={reason}>{reason}</li>)}</ul></> : <p>Ready to save: all five nodes are connected and configured.</p>}
        {errors.some(reason => reason.startsWith('Retriever: choose')) && <Button variant="outline" disabled={busy || running || loading} onClick={() => { const retriever = nodes.find(n => n.data.config.type === 'retriever'); if (retriever) { selectNode(retriever.id); requestAnimationFrame(() => { const input = document.querySelector<HTMLSelectElement>('[aria-label="Ready index"]'); input?.focus(); input?.scrollIntoView({ block: 'center' }); }); } }}>Choose ready index</Button>}
      </section>
      <div className="pipeline-editor">
        <div className="pipeline-palette"><h2>Nodes</h2><p className="field-hint">Add by clicking or dragging. One of each type.</p>{api.order.map(k => <Button key={k} variant="outline" draggable={!nodes.some(n => n.data.config.type === k)} disabled={nodes.some(n => n.data.config.type === k)} onDragStart={e => e.dataTransfer.setData('application/rag-node', k)} onClick={() => add(k)}>Add {label(k)}</Button>)}<Button variant="outline" onClick={template}>Restore template</Button></div>
        <div className="pipeline-canvas" aria-label="Pipeline canvas" onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }} onDrop={e => { e.preventDefault(); const k = e.dataTransfer.getData('application/rag-node') as api.Kind; if (api.order.includes(k) && flow) add(k, flow.screenToFlowPosition({ x: e.clientX, y: e.clientY })); }}>
          <ReactFlow nodeTypes={nodeTypes} nodes={nodes} edges={edges} onInit={setFlow} onNodesChange={changes => { onNodesChange(changes); const picked = changes.find(c => c.type === 'select' && c.selected); if (picked?.type === 'select') selectNode(picked.id, false); else if (changes.some(c => c.type === 'select' && c.id === selected && !c.selected)) setSelected(''); }} onEdgesChange={onEdgesChange} onConnect={c => setEdges(es => addEdge(c, es))} onNodeClick={(_, n) => selectNode(n.id, false)} defaultViewport={{ x: 24, y: 80, zoom: 0.9 }} minZoom={0.15} nodesDraggable={!busy && !running} nodesConnectable={!busy && !running} deleteKeyCode={busy || running ? null : ['Backspace', 'Delete']}><Background/><Controls/></ReactFlow>
        </div>
        <aside className="pipeline-config"><h2>Node settings</h2><label>Selected node<select aria-label="Selected node" value={selected} onChange={e => selectNode(e.target.value)}><option value="">Select a node</option>{nodes.map(n => <option key={n.id} value={n.id}>{n.data.label}</option>)}</select></label>
          {config?.type === 'retriever' && <><label>Ready index<select aria-label="Ready index" value={config.index_id} onChange={e => update({ index_id: e.target.value })}><option value="">Select a ready index</option>{indexes.map(i => <option key={i.id} value={i.id}>Index {i.version} · {i.chunk_count} chunks</option>)}</select></label>{!indexes.length && <p>No ready indexes. Build one in the Knowledge Base.</p>}<label>Top k<input type="number" min={1} max={50} value={config.top_k ?? ''} onChange={e => update({ top_k: e.target.valueAsNumber })}/></label><p className="field-hint">Query embeddings reuse the selected index’s existing embedding configuration.</p></>}
          {config?.type === 'prompt' && <><label>Answer instructions<textarea rows={9} maxLength={8000} value={config.template} onChange={e => update({ template: e.target.value })}/></label><p className="field-hint">Use {'{question}'} and {'{context}'}. These are literal substitutions, with no expressions or code. Context is labeled evidence. Source labels, citation rules and grounding instructions are controlled by the application.</p></>}
          {config?.type === 'llm' && <><label>Chat model<select aria-label="Chat model" value={config.model} onChange={e => update({ model: e.target.value })}><option value="">Select a model</option>{opts?.models.map(m => <option key={m}>{m}</option>)}</select></label><label>Maximum output tokens<input type="number" min={128} max={8192} value={config.max_tokens ?? ''} onChange={e => update({ max_tokens: e.target.valueAsNumber })}/></label><label>Temperature<input type="number" min={0} max={2} step={0.1} value={config.temperature ?? ''} onChange={e => update({ temperature: e.target.valueAsNumber })}/></label><p className="field-hint">Server context budget: {opts?.context_tokens} tokens. Credentials stay on the server.</p></>}
          {config?.type === 'question' && <><p>The question entered above is used for this run. Each question is independent.</p><label htmlFor="node-question">Question for this run</label><textarea id="node-question" rows={3} maxLength={8000} value={question} onChange={e => setQuestion(e.target.value)} disabled={busy || running}/></>}{config?.type === 'answer' && <p>Displays the generated answer with checked source references, evidence and usage.</p>}
          {config && <Button variant="outline" onClick={() => { setNodes(ns => ns.filter(n => n.id !== selected)); setEdges(es => es.filter(e => e.source !== selected && e.target !== selected)); setSelected(''); }}>Delete selected node</Button>}
        </aside>
      </div>
    </fieldset>

    <section className="project-section"><div className="section-heading"><h2>Pipeline run history</h2><Button variant="outline" disabled={busy || running || !saved} onClick={() => void action(async () => setHistory((await api.allPages(o => listRuns(projectId, o))).filter(r => r.snapshot.pipeline_execution && r.snapshot.pipeline_execution.nodes && versions.some(v => v.id === r.pipeline_version_id))))}>Refresh runs</Button></div><ul className="document-list">{history.map(r => <li key={r.id}><button className="document-name" onClick={() => setRun(r)}>{r.question} · version {r.snapshot.pipeline_version} · {r.status}</button></li>)}</ul></section>
  </>;
}
