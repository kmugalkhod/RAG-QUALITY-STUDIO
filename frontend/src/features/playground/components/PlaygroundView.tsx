import type { FormEvent } from 'react';
import { InlineError, Notice } from '../../../components/parts';
import { PageHeader } from '../../../components/PageHeader';
import { ErrorState } from '../../../components/states/ErrorState';
import { Button } from '../../../components/ui/button';
import { docsHref } from '../../../lib/docs';
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
  /** Loads the catalog again after it failed. */
  onRetry?: () => void;
}

const GUIDE = 'text-accent hover:underline';

function panelTitle(panel: PlaygroundPanel, mode: PlaygroundMode) {
  switch (panel) {
    case 'settings':
      return mode === 'pipeline' ? 'Pipeline settings' : 'Retrieval settings';
    case 'history':
      return 'Past questions';
    case 'sources':
    case 'details':
      return 'Answer inspection';
    case 'retrieval':
      return 'Retrieved passage';
    default:
      return '';
  }
}

export function PlaygroundView(props: PlaygroundViewProps) {
  // Options arrive with the rest of the catalog, so their absence after loading means the
  // catalog request itself failed rather than a linked version being unavailable.
  const catalogFailed = !props.loading && !!props.loadError && !props.options;
  return (
    <div className="flex min-w-0 flex-col gap-4 desktop:min-h-0 desktop:flex-1">
      <PageHeader
        title="Playground"
        meta={
          <>
            Run a question and inspect the evidence behind the answer. Guides:{' '}
            <a
              className={GUIDE}
              href={docsHref('answers/playground')}
              target="_blank"
              rel="noopener noreferrer"
            >
              Playground guide
            </a>
            {' · '}
            <a
              className={GUIDE}
              href={docsHref('answers/retrieval')}
              target="_blank"
              rel="noopener noreferrer"
            >
              Retrieval settings guide
            </a>
            {' · '}
            <a
              className={GUIDE}
              href={docsHref('answers/evidence')}
              target="_blank"
              rel="noopener noreferrer"
            >
              How to inspect evidence
            </a>
          </>
        }
      />
      {catalogFailed ? (
        <ErrorState
          headingLevel="h2"
          title="We couldn’t load the Playground"
          message={props.loadError}
          onRetry={props.onRetry}
        />
      ) : (
        <>
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
          {props.loadError && <InlineError>{props.loadError}</InlineError>}
          {props.pollError && <InlineError>{props.pollError}</InlineError>}
          {props.error && <InlineError>{props.error}</InlineError>}
          <Notice>{props.notice}</Notice>
          <div className="flex min-w-0 flex-col gap-6 desktop:min-h-0 desktop:flex-1 desktop:flex-row">
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
            <PlaygroundSidePanel
              open={!!props.panel}
              title={panelTitle(props.panel, props.mode)}
              onClose={props.onClosePanel}
            >
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
                <div className="flex flex-col gap-4 p-4">
                  <div
                    className="grid grid-cols-2 gap-1 rounded-control border border-border bg-background p-1"
                    role="group"
                    aria-label="Inspection view"
                  >
                    {(
                      [
                        ['sources', 'Sources'],
                        ['details', 'Answer details'],
                      ] as const
                    ).map(([value, label]) => (
                      <Button
                        key={value}
                        variant="ghost"
                        size="sm"
                        className="text-foreground-muted aria-pressed:bg-surface-hover aria-pressed:text-foreground"
                        aria-pressed={props.panel === value}
                        onClick={() => props.onPanelChange(value)}
                      >
                        {label}
                      </Button>
                    ))}
                  </div>
                  <RunInspector
                    run={props.run}
                    mode={props.panel}
                    sourceLabel={props.sourceLabel}
                    focusRequest={props.focusRequest}
                  />
                </div>
              )}
              {props.panel === 'retrieval' && props.selectedPassage && (
                <RetrievalInspector item={props.selectedPassage} />
              )}
            </PlaygroundSidePanel>
          </div>
        </>
      )}
    </div>
  );
}
