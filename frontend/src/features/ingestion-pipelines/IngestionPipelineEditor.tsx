import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNodesState, type Edge, type NodeChange, type ReactFlowInstance } from '@xyflow/react';
import { X } from 'lucide-react';

import { useUnsavedChanges } from '../../app/navigation';
import { InlineError } from '../../components/parts';
import { ErrorState } from '../../components/states/ErrorState';
import { LoadingState } from '../../components/states/LoadingState';
import { StatusBadge } from '../../components/StatusBadge';
import { Button } from '../../components/ui/button';
import { allPages, type Page } from '../../lib/pagination';
import { ApiError } from '../../lib/api';
import { docsHref } from '../../lib/docs';
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
import { AutomaticSync } from './components/AutomaticSync';
import {
  IngestionPipelineCanvas,
  type IngestionFlowNode,
} from './components/IngestionPipelineCanvas';
import { IngestionNodeSettings } from './components/IngestionNodeSettings';
import { IngestionPreviewResults, IngestionRunResults } from './components/IngestionResults';
import { IngestionRunStrip } from './components/IngestionRunStrip';
import { IngestionMoreActions, IngestionToolbar } from './components/IngestionToolbar';
import {
  defaultConfluence,
  defaultIngestionDraft as defaultDraft,
  defaultNotion,
  defaultS3,
  defaultWebsite,
  describeIngestionNode as detail,
  editableIngestionVersion as editableVersion,
  ingestionStageLabels as labels,
  requestErrorMessage as message,
  serverFieldErrors as fieldErrorsFrom,
  terminalIngestionStatuses as terminal,
  addWebsiteSource,
  addWebsiteSourceBlocked,
  maxWebsiteRunPages,
  removeSource,
  sourceLabel,
  sourceNodes,
  upgradeIngestionDraft,
  websitePageTotal,
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

const previewStatusLabels: Record<SourcePreview['status'], string> = {
  queued: 'Queued',
  running: 'Running',
  succeeded: 'Complete',
  failed: 'Failed',
  cancelled: 'Cancelled',
  expired: 'Expired',
};

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
  const [serverFieldErrors, setServerFieldErrors] = useState<Record<string, string>>({});
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
  const [resultsOpen, setResultsOpen] = useState<'preview' | 'run' | null>(null);
  const [dismissedRunId, setDismissedRunId] = useState('');
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
      setResultsOpen(null);
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
    const nodes = draft.execution.nodes.map((node) => ({
      id: node.id,
      type: 'ingestion' as const,
      position: draft.layout.positions[node.id],
      selected: node.id === selectedNode,
      data: {
        stage: node.type,
        label: node.type === 'source' ? sourceLabel(draft, node.id) : labels[node.type],
        detail: detail(node, documents),
        // Sources take no input and Publish has no output, however many sources there are.
        first: node.type === 'source',
        last: node.type === 'publish_index',
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
      document.getElementById('ingestion-preview')?.scrollIntoView({ block: 'nearest' });
    }
  }, [previewId]);

  useEffect(() => {
    if (activeRunId) {
      document.getElementById('ingestion-run')?.scrollIntoView({ block: 'nearest' });
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
    if (!settings) {
      return;
    }
    if (
      // Below the 1152px desktop breakpoint the settings panel stacks under the canvas.
      window.matchMedia('(max-width: 1151px)').matches
    ) {
      settings.scrollIntoView({ block: 'start' });
    } else {
      settings.scrollTop = 0;
    }
  }, [selectedNode]);
  // Every source of a pipeline uses one connector kind, so the first one stands for all.
  const firstSource = draft?.execution.nodes.find((node) => node.type === 'source');
  const validation = useMemo(() => {
    if (!draft) {
      return ['Loading configuration.'];
    }
    const reasons: string[] = [];
    if (!draft.name.trim()) {
      reasons.push('Enter a pipeline name.');
    }
    const sources = sourceNodes(draft);
    for (const source of sources) {
      // With several sources, say which one each message is about.
      const name = sources.length > 1 ? `${sourceLabel(draft, source.id)}: ` : '';
      if (source.config.kind === 'existing_files' && source.config.document_ids.length === 0) {
        reasons.push(name + 'Select at least one processed document.');
      }
      if (source.config.kind === 'website') {
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
          reasons.push(name + 'Enter at least one website URL.');
        }
        if (!source.config.allowed_origins.length) {
          reasons.push(name + 'Enter at least one allowed origin.');
        }
      }
      if (source.config.kind === 's3') {
        if (!connectionSettings?.enabled) {
          reasons.push(name + 'Enable the local encrypted connection vault before using S3.');
        }
        if (!source.config.connection_id) {
          reasons.push(name + 'Select an S3 connection.');
        }
        if (!source.config.region.trim()) {
          reasons.push(name + 'Enter an AWS region.');
        }
        if (!source.config.bucket.trim()) {
          reasons.push(name + 'Enter an S3 bucket.');
        }
        if (!source.config.allowed_file_types.length) {
          reasons.push(name + 'Allow TXT or PDF objects.');
        }
        if (source.config.max_total_bytes < source.config.max_object_bytes) {
          reasons.push(name + 'S3 total bytes must be at least the per-object limit.');
        }
      }
      if (source.config.kind === 'notion') {
        if (!connectionSettings?.enabled) {
          reasons.push(name + 'Enable the local encrypted connection vault before using Notion.');
        }
        if (!source.config.connection_id) {
          reasons.push(name + 'Select a Notion connection.');
        }
        if (
          (source.config.selection.mode === 'pages' &&
            source.config.selection.page_ids.length === 0) ||
          (source.config.selection.mode === 'data_sources' &&
            source.config.selection.data_source_ids.length === 0)
        ) {
          reasons.push(name + 'Enter at least one Notion page or data source ID.');
        }
      }
      if (source.config.kind === 'confluence') {
        if (!connectionSettings?.enabled) {
          reasons.push(
            name + 'Enable the local encrypted connection vault before using Confluence.',
          );
        }
        if (!source.config.connection_id) {
          reasons.push(name + 'Select a Confluence connection.');
        }
        if (
          (source.config.selection.mode === 'spaces' &&
            source.config.selection.space_ids.length === 0) ||
          (source.config.selection.mode === 'pages' &&
            source.config.selection.page_ids.length === 0)
        ) {
          reasons.push(name + 'Enter at least one Confluence space or page ID.');
        }
      }
    }
    const pageTotal = websitePageTotal(draft);
    if (sources.length > 1 && pageTotal > maxWebsiteRunPages) {
      reasons.push(
        `All Website sources together may fetch at most ${maxWebsiteRunPages.toLocaleString('en-US')} pages; they now allow ${pageTotal.toLocaleString('en-US')}.`,
      );
    }
    const chunk = draft.execution.nodes.find((node) => node.type === 'chunk');
    if (chunk?.type === 'chunk' && (chunk.algorithm ?? 'character_window') === 'character_window') {
      if (
        'size' in chunk &&
        (chunk.size < 100 || chunk.size > 10000 || chunk.overlap < 0 || chunk.overlap >= chunk.size)
      ) {
        reasons.push('Chunk size must be 100–10,000 and overlap must be smaller.');
      }
    }
    if (chunk?.type === 'chunk' && chunk.algorithm === 'section_token') {
      if (
        chunk.target_tokens < 64 ||
        chunk.target_tokens > chunk.maximum_tokens ||
        chunk.maximum_tokens > 16384 ||
        chunk.overlap_tokens < 0 ||
        chunk.overlap_tokens >= chunk.target_tokens
      ) {
        reasons.push('Section token target, hard maximum and overlap limits are invalid.');
      }
    }
    if (chunk?.type === 'chunk' && chunk.algorithm === 'parent_child') {
      if (
        chunk.child_target_tokens < 64 ||
        chunk.child_target_tokens > chunk.child_maximum_tokens ||
        chunk.child_overlap_tokens < 0 ||
        chunk.child_overlap_tokens >= chunk.child_target_tokens ||
        chunk.parent_target_tokens < 128 ||
        chunk.parent_target_tokens > chunk.parent_maximum_tokens ||
        chunk.child_maximum_tokens > chunk.parent_maximum_tokens
      ) {
        reasons.push('Parent and child token targets, maxima and overlap limits are invalid.');
      }
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
  }, [connectionSettings, draft]);

  function updateNode(id: string, update: (node: IngestionNode) => IngestionNode) {
    setServerFieldErrors({});
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

  function addSource() {
    if (!draft || addWebsiteSourceBlocked(draft)) {
      return;
    }
    const added = addWebsiteSource(draft);
    setServerFieldErrors({});
    setPreview(undefined);
    setDraft(added.draft);
    setSelectedNode(added.nodeId);
  }

  function deleteSource(nodeId: string) {
    if (!draft) {
      return;
    }
    const next = removeSource(draft, nodeId);
    if (next === draft) {
      return;
    }
    setServerFieldErrors({});
    setPreview(undefined);
    setDraft(next);
    setSelectedNode(sourceNodes(next)[0]?.id ?? 'extract');
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
    setServerFieldErrors({});
    try {
      await work();
    } catch (cause) {
      setError(message(cause));
      if (cause instanceof ApiError && cause.status === 422) {
        setServerFieldErrors(fieldErrorsFrom(cause.issues, draft?.execution.nodes));
      }
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
      setResultsOpen('preview');
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

  function refreshSource(nodeId: string) {
    if (!saved || dirty) {
      return;
    }
    void perform(async () => {
      setItems([]);
      setRun(
        await api.startIngestionRun(projectId, saved.pipeline_id, saved.id, {
          source_input: { kind: 'refresh', source_node_ids: [nodeId] },
        }),
      );
    });
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

  const websiteSource = firstSource?.type === 'source' && firstSource.config.kind === 'website';
  const s3Source = firstSource?.type === 'source' && firstSource.config.kind === 's3';
  const notionSource = firstSource?.type === 'source' && firstSource.config.kind === 'notion';
  const confluenceSource =
    firstSource?.type === 'source' && firstSource.config.kind === 'confluence';

  if (loading) {
    return (
      <div className="p-4 md:p-6">
        <LoadingState label="Loading ingestion pipeline…" />
      </div>
    );
  }
  if (!draft) {
    return (
      <div className="p-4 md:p-6">
        <ErrorState
          headingLevel="h1"
          title="Ingestion editor unavailable"
          message={error || 'The pipeline configuration could not be loaded.'}
          onRetry={() => window.location.reload()}
          retryLabel="Retry loading pipeline"
          action={
            <Button asChild variant="ghost">
              <a href={`#/projects/${projectId}/pipelines?kind=ingestion`}>
                All ingestion pipelines
              </a>
            </Button>
          }
        />
      </div>
    );
  }

  const legacy = draft.execution.schema_version === 1;
  const guide = websiteSource
    ? { href: docsHref('ingestion/sources/website'), label: 'Website source guide' }
    : s3Source
      ? { href: docsHref('ingestion/sources/s3'), label: 'S3 source guide' }
      : notionSource
        ? { href: docsHref('ingestion/sources/notion'), label: 'Notion source guide' }
        : confluenceSource
          ? { href: docsHref('ingestion/sources/confluence'), label: 'Confluence source guide' }
          : {
              href: docsHref('ingestion/pipelines'),
              label: 'Existing Files preview and run guide',
            };
  const runFinished = !!run && terminal.has(run.status);
  const showRunStrip = !!run && (!runFinished || dismissedRunId !== run.id);
  const results =
    resultsOpen === 'preview' && preview
      ? 'preview'
      : resultsOpen === 'run' && run && runFinished
        ? 'run'
        : null;
  // A preview checks the draft and a run publishes the saved version; start one at a time so
  // the canvas states and the preview results never describe two different jobs.
  const runActive = !!run && !runFinished;
  const previewActive = !!preview && !terminal.has(preview.status);

  return (
    // On desktop the editor fills the viewport below the shell header, so the canvas gets the
    // height the toolbar and any status strip leave.
    <div className="flex min-w-0 flex-col desktop:h-(--ingestion-workspace)">
      <h1 className="sr-only">Ingestion editor</h1>
      <fieldset className="contents" disabled={busy}>
        <div className="shrink-0 border-b border-border px-4 py-3 md:px-6">
          <IngestionToolbar
            backHref={`#/projects/${projectId}/pipelines?kind=ingestion`}
            name={draft.name}
            saved={saved}
            versions={versions}
            dirty={dirty}
            legacy={legacy}
            runLabel={websiteSource ? 'Collect source & publish index' : 'Run ingestion'}
            canPreview={validation.length === 0 && !runActive}
            runBlocked={previewActive}
            canSave={validation.length === 0 && dirty}
            sync={
              saved && (
                <AutomaticSync
                  open={automaticSyncOpen}
                  busy={busy}
                  saved={saved}
                  schedules={schedules}
                  scheduleName={scheduleName}
                  scheduleMinutes={scheduleMinutes}
                  onOpenChange={setAutomaticSyncOpen}
                  onScheduleNameChange={setScheduleName}
                  onScheduleMinutesChange={setScheduleMinutes}
                  onScheduleEdit={(changed) =>
                    setSchedules((values) =>
                      values.map((value) => (value.id === changed.id ? changed : value)),
                    )
                  }
                  onCreate={createSchedule}
                  onSave={saveSchedule}
                  onToggle={toggleSchedule}
                  onRun={runSchedule}
                />
              )
            }
            more={
              <IngestionMoreActions
                busy={busy}
                guideHref={guide.href}
                guideLabel={guide.label}
                websiteSource={websiteSource}
                legacy={legacy}
                canReprocess={!!saved && !dirty && !!snapshotId}
                snapshots={snapshots}
                snapshotId={snapshotId}
                onSnapshotChange={setSnapshotId}
                onReprocess={() => startRun('snapshot')}
                onUpgrade={() => setDraft(upgradeIngestionDraft(draft))}
              />
            }
            onNameChange={(name) => setDraft({ ...draft, name })}
            onVersionSelect={open}
            onDiscard={() => saved && open(saved)}
            onPreview={runPreview}
            onSave={save}
            onRun={() => startRun('refresh')}
          />
        </div>
        {(error || pollError) && (
          <div className="shrink-0 border-b border-border px-4 py-2 md:px-6">
            <InlineError id="ingestion-error" tabIndex={-1} className="outline-none">
              {error || pollError}
            </InlineError>
          </div>
        )}
        {run && showRunStrip && (
          <IngestionRunStrip
            projectId={projectId}
            run={run}
            displayStatus={runDisplayStatus ?? run.status}
            busy={busy}
            detailsOpen={results === 'run'}
            onCancel={() =>
              void perform(async () => setRun(await api.cancelIngestionRun(projectId, run.id)))
            }
            onToggleDetails={() => setResultsOpen(results === 'run' ? null : 'run')}
            onDismiss={() => {
              setDismissedRunId(run.id);
              if (results === 'run') {
                setResultsOpen(null);
              }
            }}
          />
        )}
        <div className="flex min-h-0 min-w-0 flex-col desktop:flex-1 desktop:flex-row">
          <div className="flex min-h-0 min-w-0 flex-col desktop:flex-1">
            <div
              data-slot="flow-canvas"
              className="relative h-(--canvas-compact) min-w-0 bg-background desktop:h-auto desktop:min-h-0 desktop:flex-1"
            >
              <IngestionPipelineCanvas
                canvasRef={canvasRef}
                nodes={flowNodes}
                edges={draft.execution.edges}
                onInit={setFlow}
                onNodesChange={changeFlowNodes}
                onSelectNode={setSelectedNode}
              />
            </div>
            {results && (
              // Preview and run items open under the canvas instead of growing the page.
              <section
                id="ingestion-results"
                aria-label={results === 'preview' ? 'Preview results' : 'Run results'}
                className="flex min-h-0 shrink-0 flex-col border-t border-border-strong bg-surface desktop:h-(--ingestion-drawer)"
              >
                <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-4 py-1 md:px-6">
                  {results === 'preview' && preview ? (
                    <div className="flex min-w-0 flex-wrap items-center gap-x-2">
                      <p className="text-xs font-medium text-foreground">Draft preview</p>
                      <StatusBadge status={preview.status}>
                        {previewStatusLabels[preview.status]}
                      </StatusBadge>
                      <p className="text-xs text-foreground-muted">
                        Checks the current settings; nothing is published.
                      </p>
                    </div>
                  ) : (
                    <p className="text-xs font-medium text-foreground">Run items · last run</p>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    icon
                    aria-label={
                      results === 'preview' ? 'Close preview results' : 'Close run details'
                    }
                    onClick={() => setResultsOpen(null)}
                  >
                    <X aria-hidden="true" />
                  </Button>
                </div>
                <div className="min-h-0 overflow-y-auto overscroll-contain *:border-t-0 desktop:flex-1">
                  {results === 'preview' && preview ? (
                    <IngestionPreviewResults
                      projectId={projectId}
                      preview={preview}
                      page={previewPage}
                      busy={busy}
                      onCancel={() =>
                        void perform(async () =>
                          setPreview(await api.cancelSourcePreview(projectId, preview.id)),
                        )
                      }
                      onRetry={() =>
                        void perform(async () => {
                          setPreviewPage({ items: [], total: 0, limit: 20, offset: 0 });
                          setPreview(await api.retrySourcePreview(projectId, preview.id));
                        })
                      }
                      onPageChange={loadPreviewPage}
                    />
                  ) : (
                    run && <IngestionRunResults projectId={projectId} run={run} items={items} />
                  )}
                </div>
              </section>
            )}
          </div>
          <IngestionNodeSettings
            projectId={projectId}
            selected={selected}
            selectedNode={selectedNode}
            nodes={draft.execution.nodes}
            dirty={dirty}
            saved={saved}
            validation={validation}
            serverFieldErrors={serverFieldErrors}
            connectionSettings={connectionSettings}
            connections={connections}
            documents={documents}
            knowledgeSets={knowledgeSets}
            websiteSource={websiteSource}
            extractionCapabilities={extractionCapabilities}
            schemaVersion={draft.execution.schema_version}
            updateNode={updateNode}
            changeSourceKind={changeSourceKind}
            sourceCount={sourceNodes(draft).length}
            sourceLabel={(nodeId) => sourceLabel(draft, nodeId)}
            addSourceBlocked={addWebsiteSourceBlocked(draft)}
            websitePageTotal={websitePageTotal(draft)}
            onAddSource={addSource}
            onRemoveSource={deleteSource}
            onRefreshSource={refreshSource}
            refreshSourceBlocked={
              !saved
                ? 'Save this pipeline and publish an index first.'
                : dirty
                  ? 'Save or discard your changes first.'
                  : runActive || previewActive
                    ? 'Wait for the current run or preview to finish.'
                    : null
            }
            onSelectNode={setSelectedNode}
          />
        </div>
      </fieldset>
    </div>
  );
}
