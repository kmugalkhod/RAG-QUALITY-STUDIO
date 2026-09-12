import type { FormEvent, ReactNode } from 'react';
import { Button } from '../../../components/ui/button';
import type { RetrievalSettings } from '../../../lib/retrieval';
import type { Evidence, IndexVersion } from '../../documents/model';
import type {
  Pipeline,
  PipelineDraft,
  PipelineOptions,
  PipelineVersion,
} from '../../pipelines/model';
import type { PlaygroundMode, PlaygroundPanel, QueryRun } from '../model';
import type { RetrievalTestResult } from './RetrievalTest';
import { RetrievalInspector } from './RetrievalTest';
import { RunInspector } from './AnswerResult';
import { PipelineTestSettings } from './PipelineTestSettings';
import { PlaygroundConversation } from './PlaygroundConversation';
import { PlaygroundSidePanel } from './PlaygroundSidePanel';
import { PlaygroundToolbar } from './PlaygroundToolbar';
import { QuestionComposer } from './QuestionComposer';
import { RetrievalTestSettings } from './RetrievalTestSettings';
import { RunHistory } from './RunHistory';

export interface PlaygroundViewProps {
  projectId: string;
  mode: PlaygroundMode;
  panel: PlaygroundPanel;
  indexes: IndexVersion[];
  pipelines: Pipeline[];
  versions: PipelineVersion[];
  options?: PipelineOptions;
  selectedPipeline: string;
  selectedVersion: string;
  draft?: PipelineDraft;
  dirty: boolean;
  running: boolean;
  saving: boolean;
  loading: boolean;
  versionsLoading: boolean;
  loadError: string;
  error: string;
  pollError: string;
  notice: string;
  run?: QueryRun;
  runs: QueryRun[];
  total: number;
  offset: number;
  indexId: string;
  retrieval: RetrievalSettings;
  retrievalResult?: RetrievalTestResult;
  selectedPassage?: Evidence;
  sourceLabel: string;
  focusRequest: number;
  question: string;
  canTest: boolean;
  draftErrors: string[];
  onModeChange: (mode: PlaygroundMode) => void;
  onTogglePanel: (panel: 'settings' | 'history' | 'sources') => void;
  onClosePanel: () => void;
  onPipeline: (id: string) => void;
  onVersion: (id: string) => void;
  onDraftChange: (draft: PipelineDraft) => void;
  onSave: () => void;
  onReset: () => void;
  onIndex: (id: string) => void;
  onRetrievalChange: (settings: RetrievalSettings) => void;
  onRefreshHistory: () => void;
  onHistoryPage: (offset: number) => void;
  onRunSelect: (run: QueryRun) => void;
  onPanelChange: (panel: PlaygroundPanel) => void;
  onCitation: (label: string) => void;
  onInspectPassage: (passage: Evidence) => void;
  onQuestionChange: (question: string) => void;
  onSubmit: (event: FormEvent) => void;
}

export function PlaygroundView(props: PlaygroundViewProps) {
  const messages: ReactNode = (
    <>
      {props.loading && <p role="status">Loading documents and pipelines…</p>}
      {props.loadError && <p role="alert">{props.loadError}</p>}
      {props.pollError && (
        <p role="alert" className="error-message">
          {props.pollError}
        </p>
      )}
      {props.error && (
        <p role="alert" className="error-message">
          {props.error}
        </p>
      )}
      {props.notice && (
        <p role="status" className="success-message">
          {props.notice}
        </p>
      )}
    </>
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Playground</h1>
          <p>Run a question and inspect the evidence behind the answer.</p>
        </div>
      </div>
      <PlaygroundToolbar
        mode={props.mode}
        panel={props.panel}
        disabled={props.running || props.saving}
        saved={props.versions.find((version) => version.id === props.selectedVersion)}
        dirty={props.dirty}
        hasRun={!!props.run}
        onModeChange={props.onModeChange}
        onTogglePanel={props.onTogglePanel}
      />
      {messages}
      <div className={`playground-layout ${props.panel ? 'settings-open' : ''}`}>
        <PlaygroundSidePanel open={!!props.panel} onClose={props.onClosePanel}>
          {props.panel === 'settings' &&
            (props.mode === 'pipeline' ? (
              <PipelineTestSettings
                pipelines={props.pipelines}
                versions={props.versions}
                indexes={props.indexes}
                options={props.options}
                pipelineId={props.selectedPipeline}
                versionId={props.selectedVersion}
                draft={props.draft}
                dirty={props.dirty}
                disabled={props.running || props.saving || props.versionsLoading}
                errors={props.draftErrors}
                onPipeline={props.onPipeline}
                onVersion={props.onVersion}
                onChange={props.onDraftChange}
                onSave={props.onSave}
                onReset={props.onReset}
              />
            ) : (
              <RetrievalTestSettings
                indexes={props.indexes}
                indexId={props.indexId}
                retrieval={props.retrieval}
                disabled={props.running}
                onIndexChange={props.onIndex}
                onChange={props.onRetrievalChange}
              />
            ))}
          {props.panel === 'history' && (
            <RunHistory
              runs={props.runs}
              total={props.total}
              offset={props.offset}
              running={props.running}
              onRefresh={props.onRefreshHistory}
              onPage={props.onHistoryPage}
              onSelect={props.onRunSelect}
            />
          )}
          {props.run && (props.panel === 'sources' || props.panel === 'details') && (
            <>
              <div className="inspector-tabs" role="group" aria-label="Answer inspection">
                <Button
                  variant="outline"
                  aria-pressed={props.panel === 'sources'}
                  onClick={() => props.onPanelChange('sources')}
                >
                  Sources
                </Button>
                <Button
                  variant="outline"
                  aria-pressed={props.panel === 'details'}
                  onClick={() => props.onPanelChange('details')}
                >
                  Answer details
                </Button>
              </div>
              <RunInspector
                run={props.run}
                mode={props.panel}
                sourceLabel={props.sourceLabel}
                focusRequest={props.focusRequest}
              />
            </>
          )}
          {props.panel === 'retrieval' && props.selectedPassage && (
            <RetrievalInspector item={props.selectedPassage} />
          )}
        </PlaygroundSidePanel>
        <PlaygroundConversation
          projectId={props.projectId}
          mode={props.mode}
          run={props.run}
          retrievalResult={props.retrievalResult}
          busy={props.running}
          loading={props.loading}
          hasIndexes={props.indexes.length > 0}
          onCitation={props.onCitation}
          onInspect={props.onInspectPassage}
        >
          <QuestionComposer
            mode={props.mode}
            question={props.question}
            running={props.running}
            canTest={props.canTest}
            onQuestionChange={props.onQuestionChange}
            onSubmit={props.onSubmit}
          />
        </PlaygroundConversation>
      </div>
    </>
  );
}
