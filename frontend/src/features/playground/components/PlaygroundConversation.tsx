import type { ReactNode } from 'react';
import { BookOpenCheck, Database, Loader2, Search } from 'lucide-react';
import { EmptyState } from '../../../components/states/EmptyState';
import { LoadingState } from '../../../components/states/LoadingState';
import { Button } from '../../../components/ui/button';
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

/** A readable measure for questions, answers and the composer. */
export const CHAT_MEASURE = 'mx-auto w-full max-w-[72ch]';

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
  let content: ReactNode;
  if (mode === 'pipeline' && run) {
    content = <RunResult run={run} onCitation={onCitation} />;
  } else if (mode === 'retrieval' && retrievalResult) {
    content = <RetrievalResults value={retrievalResult} onInspect={onInspect} />;
  } else if (busy) {
    content = (
      <p role="status" className="flex items-center gap-2 py-4 text-sm text-foreground-muted">
        <Loader2 aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" />
        {mode === 'retrieval'
          ? 'Finding matching passages…'
          : 'Finding passages and writing an answer…'}
      </p>
    );
  } else if (loading) {
    content = <LoadingState label="Loading documents and pipelines…" />;
  } else if (!hasIndexes) {
    content = (
      <EmptyState
        icon={<Database />}
        headingLevel="h2"
        title="No prepared documents yet"
        description="Upload documents in the Knowledge Base and publish a collection, then test it here."
        action={
          <Button asChild>
            <a href={`#/projects/${projectId}/knowledge-base?upload=1`}>
              Upload and prepare documents
            </a>
          </Button>
        }
      />
    );
  } else {
    content = (
      <section
        className="flex flex-1 flex-col items-center justify-center gap-2 px-4 py-12 text-center"
        aria-label="Answer workspace"
      >
        <span aria-hidden="true" className="mb-2 text-foreground-subtle">
          {mode === 'retrieval' ? (
            <Search className="size-(--icon-lg)" />
          ) : (
            <BookOpenCheck className="size-(--icon-lg)" />
          )}
        </span>
        <h2 className="text-lg font-semibold text-foreground">
          {mode === 'retrieval' ? 'Test what your search finds' : 'Test your pipeline'}
        </h2>
        <p className="max-w-panel text-sm text-foreground-muted">
          {mode === 'retrieval'
            ? 'Choose documents and Top k, then enter a search query.'
            : 'Adjust the settings in the side panel, then ask a question.'}
        </p>
      </section>
    );
  }
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4 desktop:min-h-0">
      <div
        className="flex min-h-0 flex-1 flex-col rounded-control outline-none focus-visible:outline-2 focus-visible:outline-accent desktop:overflow-y-auto desktop:overscroll-contain"
        tabIndex={0}
        aria-label="Messages"
      >
        <div className={`${CHAT_MEASURE} flex flex-1 flex-col`}>{content}</div>
      </div>
      {children}
    </div>
  );
}
