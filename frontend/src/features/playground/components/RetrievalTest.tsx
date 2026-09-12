import { formatRetrievalScores } from '../../../lib/retrieval';
import { Button } from '../../../components/ui/button';

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
    <section className="retrieval-test-results" aria-label="Retrieval test results">
      <div className="chat-question">
        <span className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
          Search query
        </span>
        <p>{value.query}</p>
      </div>
      <h2>{value.result.items.length} matching passages</h2>
      <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
        Document set version {value.result.index_version} · Top k {value.topK} · No answer was
        generated.
      </p>
      {!value.result.items.length && (
        <p>No matching passages were found. Try another query or document set.</p>
      )}
      {value.result.retrieval && (
        <details className="source-metadata text-[11px] wrap-anywhere text-muted-foreground my-4.5 mx-0">
          <summary>Settings used for this search</summary>
          <pre className="rag-source-text">
            {JSON.stringify(
              { settings: value.result.retrieval, diagnostics: value.result.diagnostics },
              null,
              2,
            )}
          </pre>
        </details>
      )}
      <ol>
        {value.result.items.map((item) => (
          <li key={`${item.run_id}:${item.ordinal}`}>
            <div className="retrieval-hit-title">
              <h3>
                {item.rank}. {item.filename}
              </h3>
              <Button variant="outline" onClick={() => onInspect(item)}>
                View passage {item.rank}
              </Button>
            </div>
            <p>{item.text}</p>
            <span className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
              Passage {item.ordinal + 1}
              {item.page_number ? ` · Page ${item.page_number}` : ''} ·{' '}
              {formatRetrievalScores(item)}
            </span>
          </li>
        ))}
      </ol>
      <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
        {value.result.score_semantics}
      </p>
    </section>
  );
}
export function RetrievalInspector({ item }: { item: Evidence }) {
  return (
    <section className="answer-inspector" aria-label="Retrieved passage">
      <h2>{item.filename}</h2>
      <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
        Rank {item.rank} · Passage {item.ordinal + 1}
        {item.page_number ? ` · Page ${item.page_number}` : ''}
      </p>
      <p className="rag-source-text">{item.text}</p>
      <details className="source-metadata text-[11px] wrap-anywhere text-muted-foreground my-4.5 mx-0">
        <summary>Source details</summary>
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
      </details>
    </section>
  );
}
