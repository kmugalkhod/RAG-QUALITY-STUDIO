import type { PlaygroundMode, PlaygroundPanel } from './model';
import { useQueryRun } from './useQueryRun';
import { usePlaygroundCatalog } from './usePlaygroundCatalog';
import { useRunHistory } from './useRunHistory';
import { createPipelineDraft } from '../pipelines/pipelineTemplate';
import {
  type PipelineDraft,
  canonical,
  createEditableExecution,
  validatePipelineExecution,
} from '../pipelines/model';
import {
  createDefaultRetrievalSettings,
  validateRetrievalSettings,
  type RetrievalSettings,
} from '../../lib/retrieval';
import { useEffect, useState, type FormEvent } from 'react';
import { useUnsavedChanges } from '../../app/navigation';
import { retrieve } from '../documents/indexApi';
import { type Evidence } from '../documents/model';
import * as pipelinesApi from '../pipelines/api';
import { type RetrievalTestResult } from './components/RetrievalTest';
const errorText = (error: unknown) => (error instanceof Error ? error.message : 'Request failed.');
const copy = <T>(value: T): T => structuredClone(value);
export interface PlaygroundProps {
  projectId: string;
  pipelineId?: string;
  versionId?: string;
  readyIndexId?: string;
  retrievalCount?: string;
  testMode?: string;
}
export function usePlaygroundController({
  projectId,
  pipelineId = '',
  versionId = '',
  readyIndexId = '',
  retrievalCount = '5',
  testMode = 'pipeline',
}: PlaygroundProps) {
  const [mode, setMode] = useState<PlaygroundMode>(
    testMode === 'retrieval' ? 'retrieval' : 'pipeline',
  );
  const [panel, setPanel] = useState<PlaygroundPanel>('settings');
  const catalog = usePlaygroundCatalog(projectId, pipelineId, versionId);
  const {
    indexes,
    pipelines,
    versions,
    options,
    selectedPipeline,
    selectedVersion,
    setPipelines,
    setVersions,
    setSelectedPipeline,
    setSelectedVersion,
  } = catalog;
  const [draft, setDraft] = useState<PipelineDraft>();
  const [baseline, setBaseline] = useState('');
  const [indexId, setIndexId] = useState(readyIndexId);
  const [retrieval, setRetrieval] = useState<RetrievalSettings>(() =>
    createDefaultRetrievalSettings(Number(retrievalCount) || 5),
  );
  const topK = retrieval.top_k;
  const [question, setQuestion] = useState('');
  const { run, setRun, pollError, completedRuns } = useQueryRun(projectId);
  const [retrievalResult, setRetrievalResult] = useState<RetrievalTestResult>();
  const [selectedPassage, setSelectedPassage] = useState<Evidence>();
  const [sourceLabel, setSourceLabel] = useState('');
  const [focusRequest, setFocusRequest] = useState(0);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const history = useRunHistory(projectId, completedRuns);
  const { loading, versionsLoading, loadError } = catalog;
  const saved = versions.find((version) => version.id === selectedVersion);
  const dirty = !!draft && canonical(draft) !== baseline;
  const running = busy || run?.status === 'running';
  const draftErrors = draft
    ? validatePipelineExecution(
        draft.execution,
        options,
        indexes.map((index) => index.id),
      )
    : ['Choose a pipeline or configure a custom test.'];
  useUnsavedChanges(dirty);
  useEffect(() => {
    setMode(testMode === 'retrieval' ? 'retrieval' : 'pipeline');
    setSelectedPipeline(pipelineId);
    setSelectedVersion(versionId);
    setIndexId(readyIndexId);
    setRetrieval((current) => ({ ...current, top_k: Number(retrievalCount) || 5 }));
  }, [
    pipelineId,
    versionId,
    readyIndexId,
    retrievalCount,
    testMode,
    setSelectedPipeline,
    setSelectedVersion,
  ]);
  useEffect(() => {
    if (!saved) {
      return;
    }
    const value = copy({
      name: saved.name,
      execution: createEditableExecution(saved.execution),
      layout: saved.layout,
    });
    setDraft(value);
    setBaseline(canonical(value));
  }, [saved]);
  useEffect(() => {
    if (selectedPipeline || !options || draft) {
      return;
    }
    const value = createPipelineDraft(
      options,
      'Playground pipeline',
      readyIndexId,
      Number(retrievalCount) || 5,
    );
    setDraft(value);
    setBaseline(canonical(value));
  }, [selectedPipeline, options, draft, readyIndexId, retrievalCount]);
  function remember(
    nextMode = mode,
    pipeline = selectedPipeline,
    version = selectedVersion,
    index = indexId,
    count = topK,
  ) {
    const params = new URLSearchParams({ mode: nextMode, index, top_k: String(count) });
    if (pipeline) {
      params.set('pipeline', pipeline);
      params.set('version', version);
    }
    const hash = `#/projects/${projectId}/playground?${params}`;
    window.history.replaceState(null, '', hash);
    sessionStorage.setItem(`playground:${projectId}`, hash);
  }
  function switchMode(next: PlaygroundMode) {
    setMode(next);
    setPanel('settings');
    setError('');
    setNotice('');
    remember(next);
  }
  function choosePipeline(id: string) {
    if (dirty && !window.confirm('Discard unsaved pipeline changes?')) {
      return;
    }
    setSelectedPipeline(id);
    setSelectedVersion('');
    setDraft(undefined);
    setError('');
    setNotice('');
    remember(mode, id, '');
  }
  function chooseVersion(id: string) {
    if (dirty && !window.confirm('Discard unsaved pipeline changes?')) {
      return;
    }
    setSelectedVersion(id);
    setError('');
    setNotice('');
    remember(mode, selectedPipeline, id);
  }
  function closePanel() {
    document
      .querySelector<HTMLButtonElement>('.playground-toolbar [aria-expanded="true"]')
      ?.focus();
    setPanel(null);
  }
  function resetDraft() {
    if (!options) {
      return;
    }
    const value = saved
      ? copy({
          name: saved.name,
          execution: createEditableExecution(saved.execution),
          layout: saved.layout,
        })
      : createPipelineDraft(
          options,
          'Playground pipeline',
          readyIndexId,
          Number(retrievalCount) || 5,
        );
    setDraft(value);
    setBaseline(canonical(value));
    setNotice('Test changes reset.');
  }
  async function saveDraft() {
    if (!draft || draftErrors.length) {
      return;
    }
    setSaving(true);
    setError('');
    try {
      const value = selectedPipeline
        ? await pipelinesApi.createPipelineVersion(projectId, selectedPipeline, draft)
        : await pipelinesApi.createPipeline(projectId, draft);
      setBaseline(canonical(draft));
      setSelectedPipeline(value.pipeline_id);
      setSelectedVersion(value.id);
      setVersions((current) => [value, ...current.filter((version) => version.id !== value.id)]);
      setPipelines((current) => [
        { id: value.pipeline_id, name: value.name, kind: 'answer' },
        ...current.filter((pipeline) => pipeline.id !== value.pipeline_id),
      ]);
      remember(mode, value.pipeline_id, value.id);
      setNotice(`Saved pipeline version ${value.version}.`);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  }
  const validRetrieval =
    indexes.some((index) => index.id === indexId) && !validateRetrievalSettings(retrieval).length;
  const canTest =
    !running &&
    !saving &&
    !loading &&
    !loadError &&
    !!question.trim() &&
    (mode === 'retrieval'
      ? validRetrieval
      : !!draft && !versionsLoading && !draftErrors.length && !options?.error);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canTest || (mode === 'pipeline' && !draft)) {
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    const text = question.trim();
    try {
      if (mode === 'retrieval') {
        const result = await retrieve(projectId, indexId, text, retrieval);
        setRetrievalResult({ query: text, topK, result });
        setPanel(null);
      } else {
        setRun(undefined);
        const value =
          saved && !dirty
            ? await pipelinesApi.runPipelineVersion(projectId, saved.pipeline_id, saved.id, text)
            : await pipelinesApi.previewPipeline(projectId, draft!.execution, text, saved);
        setRun(value);
        history.setOffset(0);
        history.refresh();
      }
      setQuestion('');
    } catch (e) {
      setError(
        `${errorText(e)}${mode === 'pipeline' ? ' Check past questions before retrying an interrupted request.' : ''}`,
      );
    } finally {
      setBusy(false);
    }
  }
  function togglePanel(next: 'settings' | 'history' | 'sources') {
    if (next === 'sources') {
      setSourceLabel('');
      setPanel((panel) => (panel === 'sources' || panel === 'details' ? null : 'sources'));
    } else {
      setPanel((panel) => (panel === next ? null : next));
    }
  }
  function inspectCitation(label: string) {
    setSourceLabel(label);
    setFocusRequest((request) => request + 1);
    setPanel('sources');
  }
  function inspectPassage(passage: Evidence) {
    setSelectedPassage(passage);
    setPanel('retrieval');
  }
  function chooseIndex(nextIndexId: string) {
    setIndexId(nextIndexId);
    remember(mode, selectedPipeline, selectedVersion, nextIndexId);
  }
  function changeRetrievalSettings(settings: RetrievalSettings) {
    setRetrieval(settings);
    remember(mode, selectedPipeline, selectedVersion, indexId, settings.top_k);
  }
  function selectRun(selectedRun: typeof run) {
    setRun(selectedRun);
    setPanel(null);
  }
  return {
    projectId,
    mode,
    panel,
    indexes,
    pipelines,
    versions,
    options,
    selectedPipeline,
    selectedVersion,
    draft,
    dirty,
    running: !!running,
    saving,
    loading,
    versionsLoading,
    loadError,
    error: error || history.error,
    pollError,
    notice,
    run,
    runs: history.runs,
    total: history.total,
    offset: history.offset,
    indexId,
    retrieval,
    retrievalResult,
    selectedPassage,
    sourceLabel,
    focusRequest,
    question,
    canTest: !!canTest,
    draftErrors,
    onModeChange: switchMode,
    onTogglePanel: togglePanel,
    onClosePanel: closePanel,
    onPipeline: choosePipeline,
    onVersion: chooseVersion,
    onDraftChange: setDraft,
    onSave: () => void saveDraft(),
    onReset: resetDraft,
    onIndex: chooseIndex,
    onRetrievalChange: changeRetrievalSettings,
    onRefreshHistory: history.refresh,
    onHistoryPage: history.setOffset,
    onRunSelect: selectRun,
    onPanelChange: setPanel,
    onCitation: inspectCitation,
    onInspectPassage: inspectPassage,
    onQuestionChange: setQuestion,
    onSubmit: submit,
  };
}
