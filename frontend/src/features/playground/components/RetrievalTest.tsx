import { formatRetrievalScores } from '../../../lib/retrieval';
import { Button } from '../../../components/ui/button';
import { CARD, META, PRE } from '../../../components/parts';
import { Disclosure, QuestionBubble } from './AnswerResult';

import { type Evidence, type Retrieval } from '../../documents/model';
export interface RetrievalTestResult {
  query: string;
  topK: number;
  result: Retrieval;
}
export function RetrievalResults({
  value,
  onInspect,
}: {
  value: RetrievalTestResult;
  onInspect: (item: Evidence) => void;
}) {
  return (
    <section className="flex flex-col gap-4 py-4" aria-label="Retrieval test results">
      <QuestionBubble label="Search query">{value.query}</QuestionBubble>
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-foreground">
          {value.result.items.length} matching passages
        </h2>
        <p className={META}>
          Document set version {value.result.index_version} · Top k {value.topK} · No answer was
          generated.
        </p>
      </div>
      {!value.result.items.length && (
        <p className="text-sm text-foreground-muted">
          No matching passages were found. Try another query or document set.
        </p>
      )}
      {value.result.retrieval && (
        <Disclosure summary="Settings used for this search">
          <pre className={PRE}>
            {JSON.stringify(
              { settings: value.result.retrieval, diagnostics: value.result.diagnostics },
              null,
              2,
            )}
          </pre>
        </Disclosure>
      )}
      <ol className="flex flex-col gap-3">
        {value.result.items.map((item) => (
          <li key={`${item.run_id}:${item.ordinal}`} className={`${CARD} flex flex-col gap-2 p-4`}>
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <h3 className="min-w-0 text-sm font-medium text-foreground wrap-anywhere">
                {item.rank}. {item.source_url ?? item.filename}
              </h3>
              <Button
                variant="outline"
                size="sm"
                className="md:shrink-0"
                onClick={() => onInspect(item)}
              >
                View passage {item.rank}
              </Button>
            </div>
            <p className="line-clamp-4 text-sm text-foreground whitespace-pre-wrap wrap-anywhere">
              {item.text}
            </p>
            <span className={META}>
              Passage {item.ordinal + 1}
              {item.page_number ? ` · Page ${item.page_number}` : ''} ·{' '}
              {formatRetrievalScores(item)}
            </span>
          </li>
        ))}
      </ol>
      <p className={META}>{value.result.score_semantics}</p>
    </section>
  );
}
export function RetrievalInspector({ item }: { item: Evidence }) {
  return (
    <section
      className="flex min-w-0 flex-col gap-3 p-4 wrap-anywhere"
      aria-label="Retrieved passage"
    >
      <h3 className="text-sm font-semibold text-foreground">{item.source_url ?? item.filename}</h3>
      {item.section_path && item.section_path.length > 0 && (
        <p className={META}>Section: {item.section_path.join(' › ')}</p>
      )}
      <p className={META}>
        Rank {item.rank} · Passage {item.ordinal + 1}
        {item.page_number ? ` · Page ${item.page_number}` : ''}
      </p>
      <p className="text-sm text-foreground whitespace-pre-wrap">{item.text}</p>
      <Disclosure summary="Source details">
        <p>
          Processing version {item.processing_version} · Characters {item.start_char}–
          {item.end_char}
        </p>
        <p>
          {formatRetrievalScores(item)} · Distance: lower is closer. Keyword and RRF scores: higher
          ranks first. Scores are not confidence.
        </p>
        <p>
          Vector rank: {item.vector_rank ?? 'Not available'} · Keyword rank:{' '}
          {item.keyword_rank ?? 'Not available'}
        </p>
        <p>Document {item.document_id}</p>
      </Disclosure>
    </section>
  );
}
