import type { FormEvent } from 'react';
import { ArrowUp, LoaderCircle } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import type { PlaygroundMode } from '../model';

interface QuestionComposerProps {
  mode: PlaygroundMode;
  question: string;
  running: boolean;
  canTest: boolean;
  onQuestionChange: (question: string) => void;
  onSubmit: (event: FormEvent) => void;
}

export function QuestionComposer({
  mode,
  question,
  running,
  canTest,
  onQuestionChange,
  onSubmit,
}: QuestionComposerProps) {
  return (
    <form className="playground-chat-composer" onSubmit={onSubmit} aria-busy={!!running}>
      <Label className="sr-only" htmlFor="rag-question">
        {mode === 'retrieval' ? 'Search query' : 'Question'}
      </Label>
      <Textarea
        id="rag-question"
        rows={2}
        required
        maxLength={8000}
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
      <div className="composer-footer">
        <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
          {mode === 'retrieval'
            ? 'Document search only · No generated answer'
            : 'Tests the current sidebar settings · Each question is independent'}
        </p>
        <Button
          className="chat-send"
          type="submit"
          aria-label={mode === 'retrieval' ? 'Run retrieval test' : 'Run pipeline test'}
          disabled={!canTest}
        >
          {running ? <LoaderCircle className="animate-spin" size={20} /> : <ArrowUp size={20} />}
        </Button>
      </div>
    </form>
  );
}
