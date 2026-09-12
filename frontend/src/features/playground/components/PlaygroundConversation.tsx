import type { ReactNode } from 'react';
import { LoaderCircle, Search, Sparkles } from 'lucide-react';
import type { Evidence } from '../../documents/model';
import type { PlaygroundMode, QueryRun } from '../model';
import { RunResult } from './AnswerResult';
import { RetrievalResults, type RetrievalTestResult } from './RetrievalTest';

interface PlaygroundConversationProps {
  projectId: string;
  mode: PlaygroundMode;
  run?: QueryRun;
  retrievalResult?: RetrievalTestResult;
  busy: boolean;
  loading: boolean;
  hasIndexes: boolean;
  children: ReactNode;
  onCitation: (label: string) => void;
  onInspect: (passage: Evidence) => void;
}

export function PlaygroundConversation({
  projectId,
  mode,
  run,
  retrievalResult,
  busy,
  loading,
  hasIndexes,
  children,
  onCitation,
  onInspect,
}: PlaygroundConversationProps) {
  return (
    <div className="playground-conversation">
      <div className="playground-messages" tabIndex={0} aria-label="Messages">
        {mode === 'pipeline' && run ? (
          <RunResult run={run} onCitation={onCitation} />
        ) : mode === 'retrieval' && retrievalResult ? (
          <RetrievalResults value={retrievalResult} onInspect={onInspect} />
        ) : busy ? (
          <p className="answer-loading" role="status">
            <LoaderCircle className="animate-spin" size={18} />
            {mode === 'retrieval'
              ? 'Finding matching passages…'
              : 'Finding passages and writing an answer…'}
          </p>
        ) : (
          <section className="playground-welcome" aria-label="Answer workspace">
            <div className="welcome-symbol">
              {mode === 'retrieval' ? <Search size={26} /> : <Sparkles size={26} />}
            </div>
            <h2>{mode === 'retrieval' ? 'Test what your search finds' : 'Test your pipeline'}</h2>
            <p>
              {mode === 'retrieval'
                ? 'Choose documents and Top k, then enter a search query.'
                : 'Adjust the settings in the sidebar, then ask a question.'}
            </p>
            {!loading && !hasIndexes && (
              <a
                className="empty-next-action"
                href={`#/projects/${projectId}/knowledge-base?upload=1`}
              >
                Upload and prepare documents
              </a>
            )}
          </section>
        )}
      </div>
      {children}
    </div>
  );
}
