import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  useNodesState,
  type Node,
  type NodeChange,
  type NodeProps,
  type ReactFlowInstance,
  type Edge,
} from '@xyflow/react';
import { Check, FileText, Play, Save, Square, X } from 'lucide-react';

import { useUnsavedChanges } from '../../app/navigation';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../components/ui/native-select';
import { allPages } from '../../lib/pagination';
import { listDocuments } from '../documents/api';
import { getEmbeddingSettings, listKnowledgeSets } from '../documents/indexApi';
import type { Document, EmbeddingConfig, KnowledgeSet } from '../documents/model';
import * as api from './api';
import {
  canonicalIngestion,
  type ExistingFilesConfig,
  type IngestionNode,
  type IngestionPipelineDraft,
  type IngestionPipelineVersion,
  type IngestionPreview,
  type IngestionRun,
  type IngestionRunItem,
} from './model';

type FlowData = { label: string; detail: string; first: boolean; last: boolean };
type FlowNode = Node<FlowData, 'ingestion'>;
const terminal = new Set(['succeeded', 'failed', 'cancelled']);
const labels: Record<IngestionNode['type'], string> = {
  source: 'Existing files',
  extract: 'Extract',
  clean: 'Clean',
  chunk: 'Chunk',
  embed: 'Embed',
  publish_index: 'Publish index',
};

function IngestionFlowNode({ data, selected }: NodeProps<FlowNode>) {
  return (
    <div
      className={`workflow-node vertical-node w-80 border border-border rounded-[10px] bg-background text-foreground h-21 flex items-center gap-4 shadow-none py-4.5 px-5.5 ${selected ? 'workflow-selected border-primary outline-2 -outline-offset-1 outline-primary' : ''}`}
    >
      {!data.first && <Handle type="target" position={Position.Top} />}
      <FileText className="node-symbol shrink-0 text-muted-foreground" size={20} />
      <div className="node-copy min-w-0">
        <strong>{data.label}</strong>
        <div className="workflow-node-content p-0 text-xs wrap-anywhere mt-1 text-muted-foreground whitespace-nowrap overflow-hidden text-ellipsis">
          {data.detail}
        </div>
      </div>
      {!data.last && <Handle type="source" position={Position.Bottom} />}
    </div>
  );
}

const nodeTypes = { ingestion: IngestionFlowNode };

function defaultDraft(embedding: EmbeddingConfig, documentIds: string[]): IngestionPipelineDraft {
  const nodes: IngestionNode[] = [
    { id: 'source', type: 'source', config: { kind: 'existing_files', document_ids: documentIds } },
    { id: 'extract', type: 'extract', strategy: 'media_type_registry', config_version: '1' },
    {
      id: 'clean',
      type: 'clean',
      normalize_whitespace: true,
      repeated_boilerplate: [],
      minimum_text_chars: 1,
      maximum_text_chars: 2_000_000,
      exact_content_deduplication: true,
    },
    {
      id: 'chunk',
      type: 'chunk',
      algorithm: 'character_window',
      unit: 'characters',
      size: 1000,
      overlap: 100,
      config_version: '1',
    },
    {
      id: 'embed',
      type: 'embed',
      provider: embedding.provider,
      model: embedding.model,
      dimensions: embedding.dimensions,
      config_version: embedding.revision,
    },
    { id: 'publish', type: 'publish_index', knowledge_set_name: 'Ingested knowledge' },
  ];
  return {
    kind: 'ingestion',
    name: 'Untitled ingestion pipeline',
    execution: {
      schema_version: 1,
      nodes,
      edges: nodes.slice(1).map((node, index) => ({ source: nodes[index].id, target: node.id })),
    },
    layout: {
      positions: Object.fromEntries(
        nodes.map((node, index) => [node.id, { x: 90, y: 40 + index * 116 }]),
      ),
    },
  };
}

function detail(node: IngestionNode, documents: Document[]) {
  if (node.type === 'source' && node.config.kind === 'existing_files') {
    return `${node.config.document_ids.length} selected document${node.config.document_ids.length === 1 ? '' : 's'}`;
  }
  if (node.type === 'chunk') {
    return `${node.size} characters · ${node.overlap} overlap`;
  }
  if (node.type === 'embed') {
    return `${node.provider} · ${node.model}`;
  }
  if (node.type === 'publish_index') {
    return node.knowledge_set_name;
  }
  if (node.type === 'extract') {
    return 'Text-based PDF and TXT';
  }
  if (node.type === 'clean') {
    return 'Normalize and deduplicate';
  }
  return documents.length ? 'Configured' : 'Waiting';
}

const message = (cause: unknown) => (cause instanceof Error ? cause.message : 'Request failed.');

function editableVersion(version: IngestionPipelineVersion): IngestionPipelineDraft {
  return {
    kind: 'ingestion',
    name: version.name,
    execution: structuredClone(version.execution),
    layout: structuredClone(version.layout),
  };
}

export function IngestionPipelineEditor({
  projectId,
  pipelineId,
  versionId = '',
}: {
  projectId: string;
  pipelineId: string;
  versionId?: string;
}) {
  const [draft, setDraft] = useState<IngestionPipelineDraft>();
  const [baseline, setBaseline] = useState('');
  const [versions, setVersions] = useState<IngestionPipelineVersion[]>([]);
  const [saved, setSaved] = useState<IngestionPipelineVersion>();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [knowledgeSets, setKnowledgeSets] = useState<KnowledgeSet[]>([]);
  const [selectedNode, setSelectedNode] = useState('source');
  const [preview, setPreview] = useState<IngestionPreview>();
  const [run, setRun] = useState<IngestionRun>();
  const [items, setItems] = useState<IngestionRunItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const pollRef = useRef<number | undefined>(undefined);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [flow, setFlow] = useState<ReactFlowInstance<FlowNode, Edge>>();
  const [flowNodes, setFlowNodes, onFlowNodesChange] = useNodesState<FlowNode>([]);
  const dirty = !!draft && canonicalIngestion(draft) !== baseline;
  useUnsavedChanges(dirty);

  const open = useCallback(
    (version: IngestionPipelineVersion) => {
      const editable = editableVersion(version);
      setDraft(editable);
      setSaved(version);
      setBaseline(canonicalIngestion(editable));
      setPreview(undefined);
      setRun(undefined);
      setItems([]);
      window.history.replaceState(
        null,
        '',
        `#/projects/${projectId}/pipelines/${version.pipeline_id}?kind=ingestion&version=${version.id}`,
      );
    },
    [projectId],
  );

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    void Promise.all([
      allPages((offset) => listDocuments(projectId, offset)),
      allPages((offset) => listKnowledgeSets(projectId, offset)),
      getEmbeddingSettings(projectId),
      pipelineId === 'new'
        ? Promise.resolve([] as IngestionPipelineVersion[])
        : allPages((offset) => api.listIngestionPipelineVersions(projectId, pipelineId, offset)),
    ])
      .then(([docs, sets, embedding, savedVersions]) => {
        if (disposed) {
          return;
        }
        setDocuments(docs);
        setKnowledgeSets(sets);
        setVersions(savedVersions);
        if (!embedding.configured || !embedding.config) {
          throw new Error(
            embedding.error ||
              'Configure an embedding provider before creating ingestion pipelines.',
          );
        }
        if (pipelineId === 'new') {
          setDraft(defaultDraft(embedding.config, []));
          setBaseline('');
        } else {
          const target =
            savedVersions.find((version) => version.id === versionId) ?? savedVersions[0];
          if (!target) {
            throw new Error('No saved ingestion pipeline version was found.');
          }
          open(target);
        }
        setError('');
      })
      .catch((cause) => !disposed && setError(message(cause)))
      .finally(() => !disposed && setLoading(false));
    return () => {
      disposed = true;
    };
  }, [projectId, pipelineId, versionId, open]);

  useEffect(() => {
    if (!draft) {
      return;
    }
    const nodes = draft.execution.nodes.map((node, index) => ({
      id: node.id,
      type: 'ingestion' as const,
      position: draft.layout.positions[node.id],
      selected: node.id === selectedNode,
      data: {
        label: labels[node.type],
        detail: detail(node, documents),
        first: index === 0,
        last: index === draft.execution.nodes.length - 1,
      },
    }));
    setFlowNodes(nodes);
  }, [draft, documents, selectedNode, setFlowNodes]);

  useEffect(() => {
    if (!run || terminal.has(run.status)) {
      return;
    }
    pollRef.current = window.setTimeout(() => {
      void api
        .getIngestionRun(projectId, run.id)
        .then(async (next) => {
          setRun(next);
          if (terminal.has(next.status)) {
            setItems(
              await allPages((offset) => api.listIngestionRunItems(projectId, next.id, offset)),
            );
          }
        })
        .catch((cause) => setError(message(cause)));
    }, 1200);
    return () => window.clearTimeout(pollRef.current);
  }, [projectId, run]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !flow) {
      return;
    }
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        void flow.fitView({ padding: 0.14, maxZoom: 1 });
      });
    });
    observer.observe(canvas);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [flow]);

  const selected = draft?.execution.nodes.find((node) => node.id === selectedNode);
  const source = draft?.execution.nodes.find((node) => node.type === 'source');
  const validation = useMemo(() => {
    if (!draft) {
      return ['Loading configuration.'];
    }
    const reasons: string[] = [];
    if (!draft.name.trim()) {
      reasons.push('Enter a pipeline name.');
    }
    if (
      source?.type === 'source' &&
      source.config.kind === 'existing_files' &&
      source.config.document_ids.length === 0
    ) {
      reasons.push('Select at least one processed document.');
    }
    const chunk = draft.execution.nodes.find((node) => node.type === 'chunk');
    if (
      chunk?.type === 'chunk' &&
      (chunk.size < 100 || chunk.size > 10000 || chunk.overlap < 0 || chunk.overlap >= chunk.size)
    ) {
      reasons.push('Chunk size must be 100–10,000 and overlap must be smaller.');
    }
    return reasons;
  }, [draft, source]);

  function updateNode(id: string, update: (node: IngestionNode) => IngestionNode) {
    setDraft((current) =>
      current
        ? {
            ...current,
            execution: {
              ...current.execution,
              nodes: current.execution.nodes.map((node) => (node.id === id ? update(node) : node)),
            },
          }
        : current,
    );
    setPreview(undefined);
  }

  function changeFlowNodes(changes: NodeChange<FlowNode>[]) {
    onFlowNodesChange(changes);
    const selectedChange = changes.find((change) => change.type === 'select' && change.selected);
    if (selectedChange?.type === 'select') {
      setSelectedNode(selectedChange.id);
    }
    const positions = changes.flatMap((change) =>
      change.type === 'position' && change.position
        ? [{ id: change.id, position: change.position }]
        : [],
    );
    if (positions.length) {
      setDraft((current) =>
        current
          ? {
              ...current,
              layout: {
                positions: {
                  ...current.layout.positions,
                  ...Object.fromEntries(positions.map((change) => [change.id, change.position])),
                },
              },
            }
          : current,
      );
    }
  }

  async function perform(work: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await work();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  function save() {
    if (!draft) {
      return;
    }
    void perform(async () => {
      const version = saved
        ? await api.createIngestionPipelineVersion(projectId, saved.pipeline_id, draft)
        : await api.createIngestionPipeline(projectId, draft);
      open(version);
      setVersions(
        await allPages((offset) =>
          api.listIngestionPipelineVersions(projectId, version.pipeline_id, offset),
        ),
      );
    });
  }

  function runPreview() {
    if (!draft) {
      return;
    }
    void perform(async () => setPreview(await api.previewIngestion(projectId, draft.execution)));
  }

  function startRun() {
    if (!saved || dirty) {
      return;
    }
    void perform(async () => {
      setItems([]);
      setRun(await api.startIngestionRun(projectId, saved.pipeline_id, saved.id));
    });
  }

  if (loading || !draft) {
    return <p role="status">Loading ingestion pipeline…</p>;
  }

  return (
    <div className="editor-workspace ingestion-editor">
      <a className="back-link" href={`#/projects/${projectId}/pipelines?kind=ingestion`}>
        All ingestion pipelines
      </a>
      <div className="editor-title">
        <h1>Ingestion editor</h1>
        <span>Existing files → ready index</span>
      </div>
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      <fieldset className="pipeline-fields" disabled={busy}>
        <div className="pipeline-toolbar flex flex-wrap m-0 gap-2.5 items-end border-b border-border py-3.5 px-5.5">
          <Label>
            Pipeline name
            <Input
              value={draft.name}
              maxLength={120}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
            />
          </Label>
          <Label>
            Saved version
            <NativeSelect
              aria-label="Saved ingestion version"
              value={saved?.id ?? ''}
              disabled={dirty}
              onChange={(event) => {
                const version = versions.find((item) => item.id === event.target.value);
                if (version) {
                  open(version);
                }
              }}
            >
              <NativeSelectOption value="">Not saved</NativeSelectOption>
              {versions.map((version) => (
                <NativeSelectOption key={version.id} value={version.id}>
                  Version {version.version}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Label>
          <span className={`draft-status ${dirty ? 'is-dirty' : ''}`} role="status">
            {dirty ? 'Unsaved changes' : saved ? `Saved version ${saved.version}` : 'Not saved'}
          </span>
          <Button onClick={save} disabled={validation.length > 0 || !dirty}>
            <Save size={15} />
            Save version
          </Button>
          <Button variant="outline" onClick={runPreview} disabled={validation.length > 0}>
            Preview source
          </Button>
          <Button onClick={startRun} disabled={!saved || dirty}>
            <Play size={15} />
            Run saved version
          </Button>
        </div>
        {validation.length > 0 && (
          <div
            className="pipeline-validation border-b border-border bg-background py-2 px-5"
            role="status"
          >
            <strong>Complete the configuration</strong>
            <ul>
              {validation.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="pipeline-editor ingestion-editor-grid">
          <div ref={canvasRef} className="pipeline-canvas" aria-label="Ingestion pipeline canvas">
            <ReactFlow<FlowNode, Edge>
              nodes={flowNodes}
              edges={draft.execution.edges.map((edge) => ({
                ...edge,
                id: `${edge.source}-${edge.target}`,
              }))}
              nodeTypes={nodeTypes}
              onInit={setFlow}
              onNodesChange={changeFlowNodes}
              onNodeClick={(_, node) => setSelectedNode(node.id)}
              nodesConnectable={false}
              deleteKeyCode={null}
              fitView
              fitViewOptions={{ padding: 0.12, maxZoom: 1 }}
            >
              <Background gap={22} size={1.2} />
              <Controls />
            </ReactFlow>
          </div>
          <aside id="node-settings" className="node-settings">
            <h2>{selected ? `${labels[selected.type]} settings` : 'Node settings'}</h2>
            {selected?.type === 'source' && selected.config.kind === 'existing_files' && (
              <div className="field-stack">
                <p className="field-hint">
                  Choose explicit project files. Only successfully processed files can run.
                </p>
                {documents.map((document) => {
                  const sourceConfig = selected.config as ExistingFilesConfig;
                  const checked = sourceConfig.document_ids.includes(document.id);
                  const disabled = document.latest_run?.status !== 'succeeded';
                  return (
                    <label className="ingestion-document-option" key={document.id}>
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={disabled}
                        onChange={(event) =>
                          updateNode(selected.id, (node) =>
                            node.type === 'source' && node.config.kind === 'existing_files'
                              ? {
                                  ...node,
                                  config: {
                                    ...node.config,
                                    document_ids: event.target.checked
                                      ? [...node.config.document_ids, document.id]
                                      : node.config.document_ids.filter(
                                          (id: string) => id !== document.id,
                                        ),
                                  },
                                }
                              : node,
                          )
                        }
                      />
                      <span>
                        <strong>{document.filename}</strong>
                        <small>
                          {disabled
                            ? `Processing ${document.latest_run?.status ?? 'required'}`
                            : `${document.latest_run?.chunk_count ?? 0} chunks ready`}
                        </small>
                      </span>
                    </label>
                  );
                })}
                {documents.length === 0 && (
                  <p>No uploaded documents. Add and process files in Knowledge Base first.</p>
                )}
              </div>
            )}
            {selected?.type === 'chunk' && (
              <div className="field-stack">
                <Label>
                  Chunk size (characters)
                  <Input
                    type="number"
                    min={100}
                    max={10000}
                    value={selected.size}
                    onChange={(event) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'chunk'
                          ? { ...node, size: Number(event.target.value) }
                          : node,
                      )
                    }
                  />
                </Label>
                <Label>
                  Overlap (characters)
                  <Input
                    type="number"
                    min={0}
                    value={selected.overlap}
                    onChange={(event) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'chunk'
                          ? { ...node, overlap: Number(event.target.value) }
                          : node,
                      )
                    }
                  />
                </Label>
              </div>
            )}
            {selected?.type === 'publish_index' && (
              <div className="field-stack">
                <Label>
                  Destination
                  <NativeSelect
                    value={selected.knowledge_set_id ?? ''}
                    onChange={(event) => {
                      const set = knowledgeSets.find((item) => item.id === event.target.value);
                      updateNode(selected.id, (node) =>
                        node.type === 'publish_index'
                          ? {
                              ...node,
                              knowledge_set_id: set?.id ?? null,
                              knowledge_set_name: set?.name ?? node.knowledge_set_name,
                            }
                          : node,
                      );
                    }}
                  >
                    <NativeSelectOption value="">Create a new knowledge set</NativeSelectOption>
                    {knowledgeSets.map((set) => (
                      <NativeSelectOption key={set.id} value={set.id}>
                        {set.name}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Label>
                {!selected.knowledge_set_id && (
                  <Label>
                    New knowledge set name
                    <Input
                      value={selected.knowledge_set_name}
                      maxLength={120}
                      onChange={(event) =>
                        updateNode(selected.id, (node) =>
                          node.type === 'publish_index'
                            ? { ...node, knowledge_set_name: event.target.value }
                            : node,
                        )
                      }
                    />
                  </Label>
                )}
              </div>
            )}
            {selected && !['source', 'chunk', 'publish_index'].includes(selected.type) && (
              <p className="field-hint">
                This deterministic stage uses the configured application implementation. Its exact
                settings are saved in the immutable version.
              </p>
            )}
          </aside>
        </div>
      </fieldset>
      {preview && (
        <section className="surface-section ingestion-results">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Source preview</p>
              <h2>
                {preview.included_count} included · {preview.excluded_count} excluded
              </h2>
            </div>
          </div>
          <ul className="project-list">
            {preview.items.map((item) => (
              <li key={item.document_id}>
                {item.included ? <Check size={18} /> : <X size={18} />}
                <div>
                  <strong>{item.filename}</strong>
                  <p>
                    {item.reason} · {item.chunk_count} chunks · {item.content_hash.slice(0, 12)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
      {run && (
        <section className="surface-section ingestion-results" aria-live="polite">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Ingestion run</p>
              <h2>
                {run.knowledge_set_name} · {run.status}
              </h2>
              <p>
                {run.stage} · {run.progress}% · {run.embedded_count}/{run.chunk_count} embedded
              </p>
            </div>
            {!terminal.has(run.status) && (
              <Button
                variant="outline"
                onClick={() =>
                  void perform(async () => setRun(await api.cancelIngestionRun(projectId, run.id)))
                }
              >
                <Square size={14} />
                Cancel
              </Button>
            )}
          </div>
          {run.error && (
            <p role="alert" className="error-message">
              {run.error}
            </p>
          )}
          {run.published_index_id && (
            <Button asChild variant="outline">
              <a
                href={`#/projects/${projectId}/knowledge-base?view=indexes&index=${run.published_index_id}`}
              >
                Inspect published index v{run.published_index_version}
              </a>
            </Button>
          )}
          <ul className="project-list">
            {items.map((item) => (
              <li key={item.document_id}>
                <FileText size={18} />
                <div>
                  <strong>{item.filename}</strong>
                  <p>
                    {item.status} · processing v{item.processing_version} · {item.chunk_count}{' '}
                    chunks · {item.content_hash.slice(0, 12)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
