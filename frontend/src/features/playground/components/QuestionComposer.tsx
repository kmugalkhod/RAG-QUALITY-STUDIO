import type { FormEvent } from 'react';
import { ArrowUp } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import type { PlaygroundMode } from '../model';
import { CHAT_MEASURE } from './PlaygroundConversation';

interface QuestionComposerProps {
  mode: PlaygroundMode;
  question: string;
  running: boolean;
  canTest: boolean;
  onQuestionChange: (question: string) => void;
  onSubmit: (event: FormEvent) => void;
}

// The send action sits at the right end on desktop and spans the width on phones
// (spec 0002 layout rules). data-composer hides the phone tab bar while the field has focus.
export function QuestionComposer({
  mode,
  question,
  running,
  canTest,
  onQuestionChange,
  onSubmit,
}: QuestionComposerProps) {
  return (
    <form
      data-testid="playground-composer"
      className={`${CHAT_MEASURE} flex shrink-0 flex-col gap-2 rounded-card border border-border-strong bg-surface p-3 has-[textarea:focus]:outline-2 has-[textarea:focus]:outline-offset-2 has-[textarea:focus]:outline-accent`}
      onSubmit={onSubmit}
      aria-busy={!!running}
    >
      <Label className="sr-only" htmlFor="rag-question">
        {mode === 'retrieval' ? 'Search query' : 'Question'}
      </Label>
      <Textarea
        id="rag-question"
        data-composer=""
        rows={2}
        required
        maxLength={8000}
        className="min-h-12 resize-y border-0 bg-transparent px-1 py-1 focus-visible:outline-none"
        placeholder={
          mode === 'retrieval'
            ? 'Search for information in your documents…'
            : 'Ask a question to test this pipeline…'
        }
        disabled={!!running}
        value={question}
        onChange={(e) => onQuestionChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (canTest) {
              e.currentTarget.form?.requestSubmit();
            }
          }
        }}
      />
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <p className="px-1 text-xs text-foreground-muted">
          {mode === 'retrieval'
            ? 'Document search only · No generated answer'
            : 'Tests the current panel settings · Each question is independent'}
        </p>
        <Button
          type="submit"
          aria-label={mode === 'retrieval' ? 'Run retrieval test' : 'Run pipeline test'}
          loading={running}
          disabled={!canTest}
          className="max-md:w-full md:w-control-md md:shrink-0 md:px-0"
        >
          <ArrowUp aria-hidden="true" />
          <span className="md:sr-only">{mode === 'retrieval' ? 'Search' : 'Ask'}</span>
        </Button>
      </div>
    </form>
  );
}
