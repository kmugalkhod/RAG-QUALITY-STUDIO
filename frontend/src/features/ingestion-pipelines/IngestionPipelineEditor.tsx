import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNodesState, type Edge, type NodeChange, type ReactFlowInstance } from '@xyflow/react';
import { ChevronDown, Clock3, Database, Play, Save, Square, X } from 'lucide-react';

import { useUnsavedChanges } from '../../app/navigation';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../components/ui/native-select';
import { allPages, type Page } from '../../lib/pagination';
import { listDocuments } from '../documents/api';
import {
  getEmbeddingSettings,
  listKnowledgeSets,
  listSourceSnapshots,
} from '../documents/indexApi';
import type { Document, KnowledgeSet, SourceSnapshot } from '../documents/model';
import { getConnectionSettings, listConnections } from '../connections/api';
import type { ConnectionSettings, SourceConnection } from '../connections/model';
import * as api from './api';
import {
  executionStatusPresentation,
  IngestionPipelineCanvas,
  stageIcons,
  type IngestionFlowNode,
} from './components/IngestionPipelineCanvas';
import { IngestionNodeSettings } from './components/IngestionNodeSettings';
import { IngestionPreviewResults, IngestionRunResults } from './components/IngestionResults';
import {
  defaultConfluence,
  defaultIngestionDraft as defaultDraft,
  defaultNotion,
  defaultS3,
  defaultWebsite,
  describeCadence,
  describeIngestionNode as detail,
  editableIngestionVersion as editableVersion,
  ingestionStageLabels as labels,
  requestErrorMessage as message,
  terminalIngestionStatuses as terminal,
  upgradeIngestionDraft,
} from './editorModel';
import { ingestionNodeExecutionStates, ingestionRunDisplayStatus } from './executionState';
import {
  canonicalIngestion,
  type ExistingFilesConfig,
  type ExtractionCapabilities,
  type IngestionNode,
  type IngestionPipelineDraft,
  type IngestionPipelineVersion,
  type IngestionRun,
  type IngestionRunItem,
  type IngestionSchedule,
  type SourcePreview,
  type SourcePreviewItem,
} from './model';

async function loadConnectionState(projectId: string) {
  const settings = await getConnectionSettings(projectId);
  const connections = settings.enabled
    ? await allPages((offset) => listConnections(projectId, offset))
    : [];
  return { settings, connections };
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
  const [snapshots, setSnapshots] = useState<SourceSnapshot[]>([]);
  const [snapshotId, setSnapshotId] = useState('');
  const [connectionSettings, setConnectionSettings] = useState<ConnectionSettings>();
  const [connections, setConnections] = useState<SourceConnection[]>([]);
  const [extractionCapabilities, setExtractionCapabilities] = useState<ExtractionCapabilities>();
  const [selectedNode, setSelectedNode] = useState('source');
  const [preview, setPreview] = useState<SourcePreview>();
  const [previewPage, setPreviewPage] = useState<Page<SourcePreviewItem>>({
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
  });
  const [run, setRun] = useState<IngestionRun>();
  const [items, setItems] = useState<IngestionRunItem[]>([]);
  const [schedules, setSchedules] = useState<IngestionSchedule[]>([]);
  const [automaticSyncOpen, setAutomaticSyncOpen] = useState(false);
  const [scheduleName, setScheduleName] = useState('Daily sync');
  const [scheduleMinutes, setScheduleMinutes] = useState(1440);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const canvasRef = useRef<HTMLDivElement>(null);
  const runRestoreGeneration = useRef(0);
  const [flow, setFlow] = useState<ReactFlowInstance<IngestionFlowNode, Edge>>();
  const [flowNodes, setFlowNodes, onFlowNodesChange] = useNodesState<IngestionFlowNode>([]);
  const dirty = !!draft && canonicalIngestion(draft) !== baseline;
  useUnsavedChanges(dirty);

  const open = useCallback(
    (version: IngestionPipelineVersion) => {
      runRestoreGeneration.current += 1;
      const editable = editableVersion(version);
      setDraft(editable);
      setSaved(version);
      setBaseline(canonicalIngestion(editable));
      setPreview(undefined);
      setPreviewPage({ items: [], total: 0, limit: 20, offset: 0 });
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
      allPages((offset) => listSourceSnapshots(projectId, offset)),
      getEmbeddingSettings(projectId),
      loadConnectionState(projectId),
      api.getExtractionCapabilities(projectId),
      pipelineId === 'new'
        ? Promise.resolve([] as IngestionPipelineVersion[])
        : allPages((offset) => api.listIngestionPipelineVersions(projectId, pipelineId, offset)),
    ])
      .then(
        ([
          docs,
          sets,
          sourceSnapshots,
          embedding,
          connectionState,
          capabilities,
          savedVersions,
        ]) => {
          if (disposed) {
            return;
          }
          setDocuments(docs);
          setKnowledgeSets(sets);
          const readySnapshots = sourceSnapshots.filter((snapshot) => snapshot.status === 'ready');
          setSnapshots(readySnapshots);
          setSnapshotId((current) => current || readySnapshots[0]?.id || '');
          setConnectionSettings(connectionState.settings);
          setConnections(connectionState.connections);
          setExtractionCapabilities(capabilities);
          setVersions(savedVersions);
          if (!embedding.configured || !embedding.config) {
            throw new Error(
              embedding.error ||
                'Configure an embedding provider before creating ingestion pipelines.',
            );
          }
          if (pipelineId === 'new') {
            setDraft(defaultDraft(embedding.config, [], capabilities));
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
        },
      )
      .catch((cause) => !disposed && setError(message(cause)))
      .finally(() => !disposed && setLoading(false));
    return () => {
      disposed = true;
    };
  }, [projectId, pipelineId, versionId, open]);

  useEffect(() => {
    let disposed = false;
    if (!saved) {
      setSchedules([]);
      return;
    }
    void allPages((offset) => api.listIngestionSchedules(projectId, offset))
      .then((values) => {
        if (!disposed) {
          setSchedules(values.filter((value) => value.pipeline_version_id === saved.id));
        }
      })
      .catch((cause) => !disposed && setError(message(cause)));
    return () => {
      disposed = true;
    };
  }, [projectId, saved]);

  useEffect(() => {
    let disposed = false;
    if (!saved) {
      return;
    }
    const generation = ++runRestoreGeneration.current;

    const restoreLatestRun = async () => {
      try {
        const page = await api.listIngestionRuns(projectId, saved.id);
        if (disposed || generation !== runRestoreGeneration.current) {
          return;
        }
        const latest = page.items.find((candidate) => candidate.pipeline_version_id === saved.id);
        setRun(latest);
        setItems([]);
        if (latest && terminal.has(latest.status)) {
          const restoredItems = await allPages((offset) =>
            api.listIngestionRunItems(projectId, latest.id, offset),
          );
          if (!disposed && generation === runRestoreGeneration.current) {
            setItems(restoredItems);
          }
        }
        if (!disposed && generation === runRestoreGeneration.current) {
          setPollError('');
        }
      } catch (cause) {
        if (!disposed && generation === runRestoreGeneration.current) {
          setPollError(`Run history unavailable. ${message(cause)}`);
        }
      }
    };

    void restoreLatestRun();
    return () => {
      disposed = true;
    };
  }, [projectId, saved]);

  useEffect(() => {
    if (!draft) {
      return;
    }
    const executionStates = ingestionNodeExecutionStates(run, draft.execution.nodes);
    const nodes = draft.execution.nodes.map((node, index) => ({
      id: node.id,
      type: 'ingestion' as const,
      position: draft.layout.positions[node.id],
      selected: node.id === selectedNode,
      data: {
        stage: node.type,
        label:
          node.type === 'source'
            ? node.config.kind === 'website'
              ? 'Website'
              : node.config.kind === 's3'
                ? 'Amazon S3'
                : node.config.kind === 'notion'
                  ? 'Notion'
                  : node.config.kind === 'confluence'
                    ? 'Confluence'
                    : 'Existing files'
            : labels[node.type],
        detail: detail(node, documents),
        first: index === 0,
        last: index === draft.execution.nodes.length - 1,
        executionStatus: executionStates[node.id],
        executionWasStarted: run?.node_states?.find((state) => state.node_id === node.id)
          ? Boolean(run.node_states.find((state) => state.node_id === node.id)?.started_at)
          : undefined,
      },
    }));
    setFlowNodes(nodes);
  }, [draft, documents, run, selectedNode, setFlowNodes]);

  const activeRunId = run?.id;
  const activeRunStatus = run?.status;
  const runDisplayStatus = run ? ingestionRunDisplayStatus(run) : undefined;
  const savedVersionId = saved?.id;
  const previewId = preview?.id;

  useEffect(() => {
    if (previewId) {
      document.getElementById('ingestion-preview')?.scrollIntoView({ block: 'start' });
    }
  }, [previewId]);

  useEffect(() => {
    if (activeRunId) {
      document.getElementById('ingestion-run')?.scrollIntoView({ block: 'start' });
    }
  }, [activeRunId]);

  useEffect(() => {
    if (error) {
      document.getElementById('ingestion-error')?.focus();
    }
  }, [error]);

  useEffect(() => {
    if (!activeRunId || (activeRunStatus && terminal.has(activeRunStatus))) {
      setPollError('');
      return;
    }

    let disposed = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const next = await api.getIngestionRun(projectId, activeRunId);
        if (disposed) {
          return;
        }
        if (terminal.has(next.status)) {
          const nextItems = await allPages((offset) =>
            api.listIngestionRunItems(projectId, next.id, offset),
          );
          if (disposed) {
            return;
          }
          setItems(nextItems);
          if (savedVersionId) {
            const refreshed = await allPages((offset) =>
              api.listIngestionSchedules(projectId, offset),
            );
            if (disposed) {
              return;
            }
            setSchedules(refreshed.filter((value) => value.pipeline_version_id === savedVersionId));
          }
          setRun((current) => (current?.id === activeRunId ? next : current));
          setPollError('');
          return;
        }
        setRun((current) => (current?.id === activeRunId ? next : current));
        setPollError('');
        timer = window.setTimeout(() => void poll(), 1200);
      } catch (cause) {
        if (!disposed) {
          setPollError(message(cause));
          timer = window.setTimeout(() => void poll(), 1200);
        }
      }
    };

    timer = window.setTimeout(() => void poll(), 1200);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [activeRunId, activeRunStatus, projectId, savedVersionId]);

  useEffect(() => {
    if (!preview || terminal.has(preview.status)) {
      return;
    }
    const timer = window.setTimeout(() => {
      void api
        .getSourcePreview(projectId, preview.id)
        .then(async (next) => {
          setPreview(next);
          if (terminal.has(next.status)) {
            setPreviewPage(await api.listSourcePreviewItems(projectId, next.id));
          }
        })
        .catch((cause) => setError(message(cause)));
    }, 800);
    return () => window.clearTimeout(timer);
  }, [preview, projectId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !flow) {
      return;
    }
    // React Flow handles the initial fit. A delayed fit on every observer delivery
    // can overwrite a user's zoom or a node selection after layout has settled.
    let width = canvas.clientWidth;
    let height = canvas.clientHeight;
    const observer = new ResizeObserver(() => {
      const nextWidth = canvas.clientWidth;
      const nextHeight = canvas.clientHeight;
      if (nextWidth === width && nextHeight === height) {
        return;
      }
      width = nextWidth;
      height = nextHeight;
      void flow.fitView({ padding: 0.12, maxZoom: 1 });
    });
    observer.observe(canvas);
    return () => {
      observer.disconnect();
    };
  }, [flow]);

  const selected = draft?.execution.nodes.find((node) => node.id === selectedNode);
  useEffect(() => {
    const settings = document.getElementById('node-settings');
    const navigation = document.querySelector('.ingestion-stage-nav');
    if (!settings || !navigation) {
      return;
    }
    if (window.matchMedia('(max-width: 1100px)').matches) {
      settings.scrollIntoView({ block: 'start' });
    } else {
      settings.scrollTop = 0;
    }
  }, [selectedNode]);
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
    if (source?.type === 'source' && source.config.kind === 'website') {
      const selection = source.config.selection;
      const selectedUrls =
        selection.mode === 'url_list'
          ? selection.urls
          : [
              selection.mode === 'single_url'
                ? selection.url
                : selection.mode === 'crawl'
                  ? selection.start_url
                  : selection.sitemap_url,
            ];
      if (!selectedUrls.length || selectedUrls.some((url) => !url.trim())) {
        reasons.push('Enter at least one website URL.');
      }
      if (!source.config.allowed_origins.length) {
        reasons.push('Enter at least one allowed origin.');
      }
    }
    if (source?.type === 'source' && source.config.kind === 's3') {
      if (!connectionSettings?.enabled) {
        reasons.push('Enable the local encrypted connection vault before using S3.');
      }
      if (!source.config.connection_id) {
        reasons.push('Select an S3 connection.');
      }
      if (!source.config.region.trim()) {
        reasons.push('Enter an AWS region.');
      }
      if (!source.config.bucket.trim()) {
        reasons.push('Enter an S3 bucket.');
      }
      if (!source.config.allowed_file_types.length) {
        reasons.push('Allow TXT or PDF objects.');
      }
      if (source.config.max_total_bytes < source.config.max_object_bytes) {
        reasons.push('S3 total bytes must be at least the per-object limit.');
      }
    }
    if (source?.type === 'source' && source.config.kind === 'notion') {
      if (!connectionSettings?.enabled) {
        reasons.push('Enable the local encrypted connection vault before using Notion.');
      }
      if (!source.config.connection_id) {
        reasons.push('Select a Notion connection.');
      }
      if (
        (source.config.selection.mode === 'pages' &&
          source.config.selection.page_ids.length === 0) ||
        (source.config.selection.mode === 'data_sources' &&
          source.config.selection.data_source_ids.length === 0)
      ) {
        reasons.push('Enter at least one Notion page or data source ID.');
      }
    }
    if (source?.type === 'source' && source.config.kind === 'confluence') {
      if (!connectionSettings?.enabled) {
        reasons.push('Enable the local encrypted connection vault before using Confluence.');
      }
      if (!source.config.connection_id) {
        reasons.push('Select a Confluence connection.');
      }
      if (
        (source.config.selection.mode === 'spaces' &&
          source.config.selection.space_ids.length === 0) ||
        (source.config.selection.mode === 'pages' && source.config.selection.page_ids.length === 0)
      ) {
        reasons.push('Enter at least one Confluence space or page ID.');
      }
    }
    const chunk = draft.execution.nodes.find((node) => node.type === 'chunk');
    if (
      chunk?.type === 'chunk' &&
      (chunk.size < 100 || chunk.size > 10000 || chunk.overlap < 0 || chunk.overlap >= chunk.size)
    ) {
      reasons.push('Chunk size must be 100–10,000 and overlap must be smaller.');
    }
    const clean = draft.execution.nodes.find((node) => node.type === 'clean');
    if (
      draft.execution.schema_version === 2 &&
      clean?.type === 'clean' &&
      ((clean.minimum_text_chars ?? 1) < 1 ||
        (clean.minimum_text_chars ?? 1) > 100000 ||
        (clean.maximum_text_chars ?? 2_000_000) < (clean.minimum_text_chars ?? 1) ||
        (clean.maximum_text_chars ?? 2_000_000) > 2_000_000)
    ) {
      reasons.push('Cleaned-text limits must be valid and the minimum cannot exceed the maximum.');
    }
    return reasons;
  }, [connectionSettings, draft, source]);

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

  function changeSourceKind(
    nodeId: string,
    kind: 'existing_files' | 'website' | 's3' | 'notion' | 'confluence',
  ) {
    updateNode(nodeId, (node) =>
      node.type === 'source'
        ? {
            ...node,
            config:
              kind === 'website'
                ? defaultWebsite()
                : kind === 's3'
                  ? defaultS3(connections.find((item) => item.kind === 's3')?.id)
                  : kind === 'notion'
                    ? defaultNotion(connections.find((item) => item.kind === 'notion')?.id)
                    : kind === 'confluence'
                      ? defaultConfluence(
                          connections.find((item) => item.kind === 'confluence')?.id,
                        )
                      : ({
                          kind: 'existing_files',
                          document_ids: [],
                        } satisfies ExistingFilesConfig),
          }
        : node,
    );
  }

  function changeFlowNodes(changes: NodeChange<IngestionFlowNode>[]) {
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
    runRestoreGeneration.current += 1;
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
    void perform(async () => {
      setPreviewPage({ items: [], total: 0, limit: 20, offset: 0 });
      setPreview(await api.previewIngestion(projectId, draft.execution));
    });
  }

  function loadPreviewPage(offset: number) {
    if (!preview) {
      return;
    }
    void perform(async () =>
      setPreviewPage(await api.listSourcePreviewItems(projectId, preview.id, offset)),
    );
  }

  function startRun(source: 'refresh' | 'snapshot' = 'refresh') {
    if (!saved || dirty) {
      return;
    }
    void perform(async () => {
      setItems([]);
      setRun(
        await api.startIngestionRun(
          projectId,
          saved.pipeline_id,
          saved.id,
          !websiteSource
            ? false
            : source === 'snapshot'
              ? { source_input: { kind: 'snapshot', source_snapshot_id: snapshotId } }
              : { source_input: { kind: 'refresh' } },
        ),
      );
    });
  }

  function createSchedule() {
    if (!saved) {
      return;
    }
    void perform(async () => {
      const created = await api.createIngestionSchedule(projectId, {
        name: scheduleName,
        pipeline_id: saved.pipeline_id,
        pipeline_version_id: saved.id,
        cadence: { kind: 'interval', minutes: scheduleMinutes },
        enabled: true,
      });
      setSchedules((values) => [created, ...values]);
      setScheduleName('Daily sync');
    });
  }

  function toggleSchedule(schedule: IngestionSchedule) {
    void perform(async () => {
      const changed = await api.updateIngestionSchedule(
        projectId,
        schedule,
        schedule.status !== 'enabled',
      );
      setSchedules((values) => values.map((value) => (value.id === changed.id ? changed : value)));
    });
  }

  function saveSchedule(schedule: IngestionSchedule) {
    void perform(async () => {
      const changed = await api.updateIngestionSchedule(
        projectId,
        schedule,
        schedule.status === 'enabled',
      );
      setSchedules((values) => values.map((value) => (value.id === changed.id ? changed : value)));
    });
  }

  function runSchedule(schedule: IngestionSchedule) {
    runRestoreGeneration.current += 1;
    void perform(async () => setRun(await api.runIngestionSchedule(projectId, schedule.id)));
  }

  const websiteSource = source?.type === 'source' && source.config.kind === 'website';
  const s3Source = source?.type === 'source' && source.config.kind === 's3';
  const notionSource = source?.type === 'source' && source.config.kind === 'notion';
  const confluenceSource = source?.type === 'source' && source.config.kind === 'confluence';

  if (loading) {
    return <p role="status">Loading ingestion pipeline…</p>;
  }
  if (!draft) {
    return (
      <section className="p-6">
        <h1>Ingestion editor unavailable</h1>
        <p role="alert" className="error-message">
          {error || 'The pipeline configuration could not be loaded.'}
        </p>
        <Button variant="outline" onClick={() => window.location.reload()}>
          Retry loading pipeline
        </Button>
        <Button asChild variant="ghost">
          <a href={`#/projects/${projectId}/pipelines?kind=ingestion`}>All ingestion pipelines</a>
        </Button>
      </section>
    );
  }

  return (
    <div className="editor-workspace ingestion-editor">
      <div className="ingestion-editor-heading">
        <a className="back-link" href={`#/projects/${projectId}/pipelines?kind=ingestion`}>
          All ingestion pipelines
        </a>
        <div className="editor-title">
          <h1>Ingestion editor</h1>
          <span>
            {websiteSource
              ? 'Website → ready index'
              : s3Source
                ? 'Amazon S3 → ready index'
                : notionSource
                  ? 'Notion → ready index'
                  : confluenceSource
                    ? 'Confluence → ready index'
                    : 'Existing files → ready index'}
          </span>
        </div>
      </div>
      {(error || pollError) && (
        <p id="ingestion-error" tabIndex={-1} role="alert" className="error-message">
          {error || pollError}
        </p>
      )}
      <fieldset className="pipeline-fields" disabled={busy}>
        <div className="pipeline-toolbar ingestion-toolbar">
          <div className="ingestion-toolbar-identity">
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
            {draft.execution.schema_version === 1 && (
              <span className="draft-status">Legacy character extraction</span>
            )}
          </div>
          <div className="ingestion-toolbar-actions">
            {draft.execution.schema_version === 1 && (
              <Button variant="outline" onClick={() => setDraft(upgradeIngestionDraft(draft))}>
                Upgrade as draft
              </Button>
            )}
            <Button
              variant={dirty ? 'default' : 'outline'}
              onClick={save}
              disabled={validation.length > 0 || !dirty}
            >
              <Save size={15} />
              Save version
            </Button>
            {saved && dirty && (
              <Button variant="ghost" onClick={() => open(saved)}>
                Discard changes
              </Button>
            )}
            <Button variant="outline" onClick={runPreview} disabled={validation.length > 0}>
              Preview source
            </Button>
            {websiteSource && (
              <div className="snapshot-run-choice">
                <Label>
                  Ready source snapshot
                  <NativeSelect
                    value={snapshotId}
                    onChange={(event) => setSnapshotId(event.target.value)}
                  >
                    <NativeSelectOption value="">Choose a snapshot</NativeSelectOption>
                    {snapshots.map((snapshot) => (
                      <NativeSelectOption key={snapshot.id} value={snapshot.id}>
                        Snapshot {snapshot.snapshot_number} ·{' '}
                        {snapshot.source_identity.origins?.join(', ') || 'Website'}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Label>
                <Button
                  variant="outline"
                  onClick={() => startRun('snapshot')}
                  disabled={!saved || dirty || !snapshotId}
                >
                  <Database size={15} />
                  Reprocess saved source
                </Button>
              </div>
            )}
            <Button
              variant={dirty ? 'outline' : 'default'}
              onClick={() => startRun('refresh')}
              disabled={!saved || dirty}
            >
              <Play size={15} />
              {websiteSource ? 'Collect source & publish index' : 'Run ingestion'}
            </Button>
            {saved && (
              <Button
                variant="outline"
                aria-expanded={automaticSyncOpen}
                aria-controls="automatic-sync-panel"
                onClick={() => setAutomaticSyncOpen((open) => !open)}
              >
                <Clock3 size={15} aria-hidden="true" />
                Automatic sync
                <ChevronDown
                  className={automaticSyncOpen ? 'is-open' : ''}
                  size={15}
                  aria-hidden="true"
                />
              </Button>
            )}
          </div>
        </div>
        {draft.execution.schema_version === 1 && (
          <p className="legacy-upgrade-note" role="note">
            Upgrade mapping: current source extraction becomes native-text-v1, saved Clean values
            move to standard-v1, and character windows become character-window-v1. The saved legacy
            version is not changed.
          </p>
        )}
        {saved && automaticSyncOpen && (
          <section
            id="automatic-sync-panel"
            className="automatic-sync-panel"
            aria-labelledby="automatic-sync-heading"
          >
            <div className="automatic-sync-intro">
              <div>
                <h2 id="automatic-sync-heading">Automatic sync</h2>
                <p>
                  Keep the published index up to date by running saved version {saved.version} on a
                  schedule. Unsaved changes are not included.
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Close automatic sync settings"
                onClick={() => setAutomaticSyncOpen(false)}
              >
                <X size={16} aria-hidden="true" />
              </Button>
            </div>

            <div className="automatic-sync-create">
              <div>
                <h3>Add a schedule</h3>
                <p>
                  The first sync starts after the selected interval. You can run it now or pause it
                  anytime.
                </p>
              </div>
              <div className="automatic-sync-form">
                <Label>
                  Schedule name
                  <Input
                    value={scheduleName}
                    maxLength={120}
                    onChange={(event) => setScheduleName(event.target.value)}
                  />
                </Label>
                <Label>
                  Sync frequency
                  <NativeSelect
                    value={scheduleMinutes}
                    onChange={(event) => setScheduleMinutes(Number(event.target.value))}
                  >
                    <NativeSelectOption value={15}>Every 15 minutes</NativeSelectOption>
                    <NativeSelectOption value={60}>Every hour</NativeSelectOption>
                    <NativeSelectOption value={360}>Every 6 hours</NativeSelectOption>
                    <NativeSelectOption value={720}>Every 12 hours</NativeSelectOption>
                    <NativeSelectOption value={1440}>Every day</NativeSelectOption>
                    <NativeSelectOption value={10080}>Every week</NativeSelectOption>
                  </NativeSelect>
                </Label>
                <Button onClick={createSchedule} disabled={!scheduleName.trim()}>
                  Start automatic sync
                </Button>
              </div>
            </div>

            {schedules.length > 0 && (
              <div className="automatic-sync-saved">
                <h3>Saved schedules</h3>
                <ul aria-label="Automatic sync schedules">
                  {schedules.map((schedule) => (
                    <li key={schedule.id}>
                      <div className="automatic-sync-summary">
                        <div>
                          <strong>{schedule.name}</strong>
                          <span>{describeCadence(schedule)}</span>
                        </div>
                        <span className={`sync-status is-${schedule.status}`}>
                          {schedule.status === 'enabled' ? 'Active' : 'Paused'}
                        </span>
                      </div>
                      <div className="automatic-sync-form is-saved">
                        <Label>
                          Schedule name
                          <Input
                            value={schedule.name}
                            onChange={(event) =>
                              setSchedules((values) =>
                                values.map((value) =>
                                  value.id === schedule.id
                                    ? { ...value, name: event.target.value }
                                    : value,
                                ),
                              )
                            }
                          />
                        </Label>
                        {schedule.cadence.kind === 'interval' && (
                          <Label>
                            Interval (minutes)
                            <Input
                              type="number"
                              min={15}
                              max={10080}
                              value={schedule.cadence.minutes}
                              onChange={(event) =>
                                setSchedules((values) =>
                                  values.map((value) =>
                                    value.id === schedule.id
                                      ? {
                                          ...value,
                                          cadence: {
                                            kind: 'interval',
                                            minutes: Number(event.target.value),
                                          },
                                        }
                                      : value,
                                  ),
                                )
                              }
                            />
                          </Label>
                        )}
                      </div>
                      <p className="automatic-sync-timing">
                        {schedule.next_run_at
                          ? `Next sync ${new Date(schedule.next_run_at).toLocaleString()}`
                          : 'No automatic runs while paused'}
                        {' · '}
                        Last result: {schedule.last_outcome ?? 'Not run yet'}
                      </p>
                      {schedule.last_error && (
                        <p className="automatic-sync-error">{schedule.last_error}</p>
                      )}
                      <div className="automatic-sync-actions">
                        <Button
                          variant="outline"
                          onClick={() => saveSchedule(schedule)}
                          disabled={
                            !schedule.name.trim() ||
                            (schedule.cadence.kind === 'interval' &&
                              (schedule.cadence.minutes < 15 || schedule.cadence.minutes > 10080))
                          }
                        >
                          Save changes
                        </Button>
                        <Button variant="outline" onClick={() => toggleSchedule(schedule)}>
                          {schedule.status === 'enabled' ? 'Pause sync' : 'Resume sync'}
                        </Button>
                        <Button variant="outline" onClick={() => runSchedule(schedule)}>
                          Run now
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}
        <nav className="ingestion-stage-nav" aria-label="Ingestion stages">
          {draft.execution.nodes.map((node, index) => {
            const Icon = stageIcons[node.type];
            return (
              <Button
                key={node.id}
                variant="ghost"
                aria-pressed={selectedNode === node.id}
                aria-controls="node-settings"
                onClick={() => setSelectedNode(node.id)}
              >
                <span className="ingestion-stage-number">{index + 1}</span>
                <Icon size={15} aria-hidden="true" />
                {labels[node.type]}
              </Button>
            );
          })}
        </nav>
        {run && (
          <div className="ingestion-run-bar">
            <div id="ingestion-run" className="ingestion-run-summary" aria-live="polite">
              <div className="ingestion-run-summary-heading">
                {(() => {
                  const displayStatus = runDisplayStatus ?? run.status;
                  const presentation = executionStatusPresentation[displayStatus];
                  const StatusIcon = presentation.icon;
                  return (
                    <span className="ingestion-run-state" data-status={displayStatus}>
                      <StatusIcon
                        className={displayStatus === 'running' ? 'ingestion-status-spinner' : ''}
                        size={14}
                        aria-hidden="true"
                      />
                      {presentation.label}
                    </span>
                  );
                })()}
                <strong>{run.progress}%</strong>
              </div>
              <p title={run.knowledge_set_name}>{run.knowledge_set_name}</p>
              <div
                className="ingestion-run-progress"
                role="progressbar"
                aria-label="Ingestion run progress"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={run.progress}
              >
                <span style={{ transform: `scaleX(${run.progress / 100})` }} />
              </div>
              <small>
                {run.stage === 'indexing'
                  ? `${run.embedded_count}/${run.chunk_count} chunks embedded`
                  : `${run.stage} checkpoint`}
              </small>
              {!terminal.has(run.status) && (
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  onClick={() =>
                    void perform(async () =>
                      setRun(await api.cancelIngestionRun(projectId, run.id)),
                    )
                  }
                >
                  <Square size={13} />
                  Cancel run
                </Button>
              )}
            </div>
          </div>
        )}
        <div className="pipeline-editor ingestion-editor-grid">
          <IngestionPipelineCanvas
            canvasRef={canvasRef}
            nodes={flowNodes}
            edges={draft.execution.edges}
            onInit={setFlow}
            onNodesChange={changeFlowNodes}
            onSelectNode={setSelectedNode}
          />
          <IngestionNodeSettings
            projectId={projectId}
            selected={selected}
            selectedNode={selectedNode}
            nodes={draft.execution.nodes}
            dirty={dirty}
            saved={saved}
            validation={validation}
            connectionSettings={connectionSettings}
            connections={connections}
            documents={documents}
            knowledgeSets={knowledgeSets}
            websiteSource={websiteSource}
            extractionCapabilities={extractionCapabilities}
            schemaVersion={draft.execution.schema_version}
            updateNode={updateNode}
            changeSourceKind={changeSourceKind}
          />
        </div>
      </fieldset>
      {preview && (
        <IngestionPreviewResults
          preview={preview}
          page={previewPage}
          busy={busy}
          onCancel={() =>
            void perform(async () =>
              setPreview(await api.cancelSourcePreview(projectId, preview.id)),
            )
          }
          onPageChange={loadPreviewPage}
        />
      )}
      {run && terminal.has(run.status) && (
        <IngestionRunResults projectId={projectId} run={run} items={items} />
      )}
    </div>
  );
}
