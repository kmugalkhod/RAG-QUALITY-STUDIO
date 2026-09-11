import './playground.css';
import { useEffect, useState, type FormEvent } from 'react';
import { ArrowUp, History, LoaderCircle, PanelRightOpen, Search, SlidersHorizontal, Sparkles, X } from 'lucide-react';
import { useUnsavedChanges } from '../../app/navigation';
import { Button } from '../../components/ui/button';
import { listIndexes, retrieve, type Evidence, type IndexVersion } from '../documents/indexApi';
import * as pipelinesApi from '../pipelines/api';
import * as api from './api';
import { RunInspector, RunResult } from './AnswerResult';
import { PipelineTestSettings } from './PipelineTestSettings';
import { RetrievalInspector, RetrievalResults, type RetrievalTestResult } from './RetrievalTest';

type Mode = 'retrieval' | 'pipeline';
type Panel = 'settings' | 'history' | 'sources' | 'details' | 'retrieval' | null;
const errorText = (error: unknown) => error instanceof Error ? error.message : 'Request failed.';
const copy = <T,>(value: T): T => structuredClone(value);

function newDraft(options: pipelinesApi.Options, indexId: string, topK: number): pipelinesApi.Draft {
  const nodes: pipelinesApi.ExecutionNode[] = [
    { id: 'question', type: 'question' },
    { id: 'retriever', type: 'retriever', index_id: indexId, top_k: topK },
    { id: 'prompt', type: 'prompt', template: options.template },
    { id: 'llm', type: 'llm', model: options.models[0] || '', max_tokens: options.max_tokens, temperature: 0 },
    { id: 'answer', type: 'answer' },
  ];
  return {
    name: 'Playground pipeline',
    execution: { schema_version: 1, nodes, edges: pipelinesApi.order.slice(1).map((kind, i) => ({ source: pipelinesApi.order[i], target: kind })) },
    layout: { positions: Object.fromEntries(nodes.map((node, i) => [node.id, { x: 80, y: 40 + i * 116 }])) },
  };
}

interface Props {
  projectId: string;
  pipelineId?: string;
  versionId?: string;
  readyIndexId?: string;
  retrievalCount?: string;
  testMode?: string;
}

export function Playground({ projectId, pipelineId = '', versionId = '', readyIndexId = '', retrievalCount = '5', testMode = 'pipeline' }: Props) {
  const [mode, setMode] = useState<Mode>(testMode === 'retrieval' ? 'retrieval' : 'pipeline');
  const [panel, setPanel] = useState<Panel>('settings');
  const [indexes, setIndexes] = useState<IndexVersion[]>([]);
  const [pipelines, setPipelines] = useState<pipelinesApi.Pipeline[]>([]);
  const [versions, setVersions] = useState<pipelinesApi.Version[]>([]);
  const [options, setOptions] = useState<pipelinesApi.Options>();
  const [selectedPipeline, setSelectedPipeline] = useState(pipelineId);
  const [selectedVersion, setSelectedVersion] = useState(versionId);
  const [draft, setDraft] = useState<pipelinesApi.Draft>();
  const [baseline, setBaseline] = useState('');
  const [indexId, setIndexId] = useState(readyIndexId);
  const [topK, setTopK] = useState(Number(retrievalCount) || 5);
  const [question, setQuestion] = useState('');
  const [run, setRun] = useState<api.QueryRun>();
  const [retrievalResult, setRetrievalResult] = useState<RetrievalTestResult>();
  const [selectedPassage, setSelectedPassage] = useState<Evidence>();
  const [sourceLabel, setSourceLabel] = useState('');
  const [focusRequest, setFocusRequest] = useState(0);
  const [runs, setRuns] = useState<api.QueryRun[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const saved = versions.find(version => version.id === selectedVersion);
  const dirty = !!draft && pipelinesApi.canonical(draft) !== baseline;
  const running = busy || run?.status === 'running';
  const draftErrors = draft ? pipelinesApi.validate(draft.execution, options, indexes.map(index => index.id)) : ['Choose a pipeline or configure a custom test.'];
  useUnsavedChanges(dirty);

  useEffect(() => {
    setMode(testMode === 'retrieval' ? 'retrieval' : 'pipeline');
    setSelectedPipeline(pipelineId);
    setSelectedVersion(versionId);
    setIndexId(readyIndexId);
    setTopK(Number(retrievalCount) || 5);
  }, [pipelineId, versionId, readyIndexId, retrievalCount, testMode]);

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    void Promise.all([
      pipelinesApi.allPages(start => listIndexes(projectId, start)),
      pipelinesApi.allPages(start => pipelinesApi.list(projectId, start)),
      pipelinesApi.options(projectId),
    ]).then(([allIndexes, allPipelines, serverOptions]) => {
      if (disposed) return;
      setIndexes(allIndexes.filter(index => index.status === 'succeeded'));
      setPipelines(allPipelines);
      setOptions(serverOptions);
      setLoadError('');
    }).catch(e => { if (!disposed) setLoadError(errorText(e)); }).finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [projectId]);

  useEffect(() => {
    let disposed = false;
    void api.listRuns(projectId, offset).then(page => {
      if (!disposed) { setRuns(page.items); setTotal(page.total); }
    }).catch(e => { if (!disposed) setError(errorText(e)); });
    return () => { disposed = true; };
  }, [projectId, offset, revision]);

  useEffect(() => {
    let disposed = false;
    setVersions([]);
    setDraft(undefined);
    setBaseline('');
    if (!selectedPipeline) { setVersionsLoading(false); return; }
    setVersionsLoading(true);
    void pipelinesApi.allPages(start => pipelinesApi.versions(projectId, selectedPipeline, start)).then(values => {
      if (disposed) return;
      setVersions(values);
      const requested = selectedPipeline === pipelineId && versionId ? versionId : values[0]?.id || '';
      if (requested && !values.some(value => value.id === requested)) {
        setError('The linked pipeline version is unavailable. Choose another version.');
        setSelectedVersion('');
      } else setSelectedVersion(requested);
    }).catch(e => { if (!disposed) setError(errorText(e)); }).finally(() => { if (!disposed) setVersionsLoading(false); });
    return () => { disposed = true; };
  }, [projectId, selectedPipeline, pipelineId, versionId]);

  useEffect(() => {
    if (!saved) return;
    const value = copy({ name: saved.name, execution: saved.execution, layout: saved.layout });
    setDraft(value);
    setBaseline(pipelinesApi.canonical(value));
  }, [saved]);

  useEffect(() => {
    if (selectedPipeline || !options || draft) return;
    const value = newDraft(options, readyIndexId, Number(retrievalCount) || 5);
    setDraft(value);
    setBaseline(pipelinesApi.canonical(value));
  }, [selectedPipeline, options, draft, readyIndexId, retrievalCount]);

  useEffect(() => {
    if (!run || run.status !== 'running') return;
    let disposed = false;
    const timer = setInterval(() => {
      void pipelinesApi.readRun(projectId, run.id).then(value => {
        if (!disposed) { setRun(value); if (value.status !== 'running') setRevision(n => n + 1); }
      }).catch(e => { if (!disposed) setError(errorText(e)); });
    }, 1000);
    return () => { disposed = true; clearInterval(timer); };
  }, [projectId, run]);

  function remember(nextMode = mode, pipeline = selectedPipeline, version = selectedVersion, index = indexId, count = topK) {
    const params = new URLSearchParams({ mode: nextMode, index, top_k: String(count) });
    if (pipeline) { params.set('pipeline', pipeline); params.set('version', version); }
    const hash = `#/projects/${projectId}/playground?${params}`;
    window.history.replaceState(null, '', hash);
    sessionStorage.setItem(`playground:${projectId}`, hash);
  }
  function switchMode(next: Mode) {
    setMode(next); setPanel('settings'); setError(''); setNotice('');
    remember(next);
  }
  function choosePipeline(id: string) {
    if (dirty && !window.confirm('Discard unsaved pipeline changes?')) return;
    setSelectedPipeline(id); setSelectedVersion(''); setDraft(undefined); setError(''); setNotice('');
    remember(mode, id, '');
  }
  function chooseVersion(id: string) {
    if (dirty && !window.confirm('Discard unsaved pipeline changes?')) return;
    setSelectedVersion(id); setError(''); setNotice(''); remember(mode, selectedPipeline, id);
  }
  function closePanel() {
    document.querySelector<HTMLButtonElement>('.playground-toolbar [aria-expanded="true"]')?.focus();
    setPanel(null);
  }
  function resetDraft() {
    if (!options) return;
    const value = saved ? copy({ name: saved.name, execution: saved.execution, layout: saved.layout }) : newDraft(options, readyIndexId, Number(retrievalCount) || 5);
    setDraft(value); setBaseline(pipelinesApi.canonical(value)); setNotice('Test changes reset.');
  }
  async function saveDraft() {
    if (!draft || draftErrors.length) return;
    setSaving(true); setError('');
    try {
      const value = await pipelinesApi.save(projectId, draft, selectedPipeline || undefined);
      setBaseline(pipelinesApi.canonical(draft));
      setSelectedPipeline(value.pipeline_id);
      setSelectedVersion(value.id);
      setVersions(current => [value, ...current.filter(version => version.id !== value.id)]);
      setPipelines(current => [{ id: value.pipeline_id, name: value.name }, ...current.filter(pipeline => pipeline.id !== value.pipeline_id)]);
      remember(mode, value.pipeline_id, value.id);
      setNotice(`Saved pipeline version ${value.version}.`);
    } catch (e) { setError(errorText(e)); }
    finally { setSaving(false); }
  }
  const validRetrieval = indexes.some(index => index.id === indexId) && Number.isInteger(topK) && topK >= 1 && topK <= 50;
  const canTest = !running && !saving && !loading && !loadError && !!question.trim() && (mode === 'retrieval' ? validRetrieval : !!draft && !versionsLoading && !draftErrors.length && !options?.error);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canTest || (mode === 'pipeline' && !draft)) return;
    setBusy(true); setError(''); setNotice('');
    const text = question.trim();
    try {
      if (mode === 'retrieval') {
        const result = await retrieve(projectId, indexId, text, topK);
        setRetrievalResult({ query: text, topK, result });
        setPanel(null);
      } else {
        setRun(undefined);
        const value = saved && !dirty ? await pipelinesApi.run(projectId, saved, text) : await pipelinesApi.preview(projectId, draft!.execution, text, saved);
        setRun(value); setOffset(0); setRevision(n => n + 1);
      }
      setQuestion('');
    } catch (e) { setError(`${errorText(e)}${mode === 'pipeline' ? ' Check past questions before retrying an interrupted request.' : ''}`); }
    finally { setBusy(false); }
  }

  return <>
    <div className="page-heading"><div><h1>Playground</h1><p>Change settings, run a test, and inspect what happened.</p></div></div>
    <div className="playground-test-modes" role="group" aria-label="Test mode">
      <button aria-label="Retrieval test" aria-pressed={mode === 'retrieval'} disabled={running || saving} onClick={() => switchMode('retrieval')}><Search size={18}/><span><strong>Retrieval test</strong><small>Find passages only</small></span></button>
      <button aria-label="Pipeline test" aria-pressed={mode === 'pipeline'} disabled={running || saving} onClick={() => switchMode('pipeline')}><Sparkles size={18}/><span><strong>Pipeline test</strong><small>Find passages + generate an answer</small></span></button>
    </div>
    <div className="playground-toolbar">
      <span className="playground-context">{mode === 'retrieval' ? 'Retrieval settings affect document search only' : saved ? `${saved.name} · Version ${saved.version}${dirty ? ' · Test draft' : ''}` : 'Custom pipeline test'}</span>
      <Button variant="outline" aria-expanded={panel === 'settings'} aria-controls="playground-settings" onClick={() => setPanel(value => value === 'settings' ? null : 'settings')}><SlidersHorizontal size={16}/>{mode === 'retrieval' ? 'Retrieval settings' : 'Pipeline settings'}</Button>
      {mode === 'pipeline' && <Button variant="outline" aria-expanded={panel === 'history'} aria-controls="playground-settings" onClick={() => setPanel(value => value === 'history' ? null : 'history')}><History size={16}/>Past questions</Button>}
      {mode === 'pipeline' && run && <Button variant="outline" aria-expanded={panel === 'sources' || panel === 'details'} aria-controls="playground-settings" onClick={() => { setSourceLabel(''); setPanel(value => value === 'sources' || value === 'details' ? null : 'sources'); }}><PanelRightOpen size={16}/>Sources & details</Button>}
    </div>
    {loading && <p role="status">Loading documents and pipelines…</p>}
    {loadError && <p role="alert">{loadError}</p>}
    {error && <p role="alert" className="error-message">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <div className={`playground-layout ${panel ? 'settings-open' : ''}`}>
      <aside id="playground-settings" className="playground-settings" hidden={!panel} aria-label="Playground side panel" onKeyDown={e => { if (e.key === 'Escape') closePanel(); }}>
        <button className="inspector-close icon-button" aria-label="Close side panel" onClick={closePanel}><X size={18}/></button>
        {panel === 'settings' && (mode === 'pipeline' ? <PipelineTestSettings pipelines={pipelines} versions={versions} indexes={indexes} options={options} pipelineId={selectedPipeline} versionId={selectedVersion} draft={draft} dirty={dirty} disabled={!!running || saving || versionsLoading} errors={draftErrors} onPipeline={choosePipeline} onVersion={chooseVersion} onChange={setDraft} onSave={() => void saveDraft()} onReset={resetDraft}/> : <div className="retrieval-test-settings"><h2>Retrieval settings</h2><fieldset disabled={!!running}><label>Documents to search<select value={indexId} onChange={e => { setIndexId(e.target.value); remember(mode, selectedPipeline, selectedVersion, e.target.value); }}><option value="">Choose prepared documents</option>{indexes.map(index => <option key={index.id} value={index.id}>Document set · Version {index.version} · {index.chunk_count} passages</option>)}</select></label><label>Top k<input type="number" min={1} max={50} value={topK} onChange={e => { setTopK(e.target.valueAsNumber); remember(mode, selectedPipeline, selectedVersion, indexId, e.target.valueAsNumber); }}/></label><p className="field-hint">Maximum matching passages to return. This test does not call an answer model.</p></fieldset></div>)}
        {panel === 'history' && <div className="playground-history"><section aria-labelledby="history-title"><div className="section-heading"><h2 id="history-title">Past questions</h2><Button variant="outline" disabled={!!running} onClick={() => setRevision(n => n + 1)}>Refresh</Button></div>{!runs.length && <p>No saved questions yet.</p>}<ul className="document-list">{runs.map(item => <li key={item.id}><div><button className="document-name" disabled={!!running} onClick={() => { setRun(item); setPanel(null); }}>{item.question}</button><p>{item.snapshot.pipeline_preview ? 'Test draft' : item.pipeline_version_id ? `Pipeline v${item.snapshot.pipeline_version}` : 'Default settings'} · {item.status.replaceAll('_', ' ')}</p></div></li>)}</ul>{(total > 20 || offset > 0) && <nav className="pagination" aria-label="Query history pages"><Button variant="outline" disabled={!offset || !!running} onClick={() => setOffset(n => n - 20)}>Previous queries</Button><span>Page {offset / 20 + 1}</span><Button variant="outline" disabled={offset + 20 >= total || !!running} onClick={() => setOffset(n => n + 20)}>Next queries</Button></nav>}</section></div>}
        {run && (panel === 'sources' || panel === 'details') && <><div className="inspector-tabs" role="group" aria-label="Answer inspection"><Button variant="outline" aria-pressed={panel === 'sources'} onClick={() => setPanel('sources')}>Sources</Button><Button variant="outline" aria-pressed={panel === 'details'} onClick={() => setPanel('details')}>Answer details</Button></div><RunInspector run={run} mode={panel} sourceLabel={sourceLabel} focusRequest={focusRequest}/></>}
        {panel === 'retrieval' && selectedPassage && <RetrievalInspector item={selectedPassage}/>}
      </aside>
      <div className="playground-conversation">
        <div className="playground-messages" tabIndex={0} aria-label="Messages">
          {mode === 'pipeline' && run ? <RunResult run={run} onCitation={label => { setSourceLabel(label); setFocusRequest(n => n + 1); setPanel('sources'); }}/>
            : mode === 'retrieval' && retrievalResult ? <RetrievalResults value={retrievalResult} onInspect={item => { setSelectedPassage(item); setPanel('retrieval'); }}/>
              : busy ? <p className="answer-loading" role="status"><LoaderCircle className="animate-spin" size={18}/>{mode === 'retrieval' ? 'Finding matching passages…' : 'Finding passages and writing an answer…'}</p>
                : <section className="playground-welcome" aria-label="Answer workspace"><div className="welcome-symbol">{mode === 'retrieval' ? <Search size={26}/> : <Sparkles size={26}/>}</div><h2>{mode === 'retrieval' ? 'Test what your search finds' : 'Test your pipeline'}</h2><p>{mode === 'retrieval' ? 'Choose documents and Top k, then enter a search query.' : 'Adjust the settings in the sidebar, then ask a question.'}</p>{!loading && !indexes.length && <a className="empty-next-action" href={`#/projects/${projectId}/knowledge-base?upload=1`}>Upload and prepare documents</a>}</section>}
        </div>
        <form className="playground-chat-composer" onSubmit={submit} aria-busy={!!running}>
          <label className="sr-only" htmlFor="rag-question">{mode === 'retrieval' ? 'Search query' : 'Question'}</label>
          <textarea id="rag-question" rows={2} required maxLength={8000} placeholder={mode === 'retrieval' ? 'Search for information in your documents…' : 'Ask a question to test this pipeline…'} disabled={!!running} value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (canTest) e.currentTarget.form?.requestSubmit(); } }}/>
          <div className="composer-footer"><p className="field-hint">{mode === 'retrieval' ? 'Document search only · No generated answer' : 'Tests the current sidebar settings · Each question is independent'}</p><Button className="chat-send" type="submit" aria-label={mode === 'retrieval' ? 'Run retrieval test' : 'Run pipeline test'} disabled={!canTest}>{running ? <LoaderCircle className="animate-spin" size={20}/> : <ArrowUp size={20}/>}</Button></div>
        </form>
      </div>
    </div>
  </>;
}
