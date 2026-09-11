import { Button } from '../../components/ui/button';
import type { Evidence, Retrieval } from '../documents/indexApi';

export interface RetrievalTestResult {
  query: string;
  topK: number;
  result: Retrieval;
}

export function RetrievalResults({ value, onInspect }: { value: RetrievalTestResult; onInspect: (item: Evidence) => void }) {
  return <section className="retrieval-test-results" aria-label="Retrieval test results">
    <div className="chat-question"><span className="field-hint">Search query</span><p>{value.query}</p></div>
    <h2>{value.result.items.length} matching passages</h2>
    <p className="field-hint">Document set version {value.result.index_version} · Top k {value.topK} · No answer was generated.</p>
    {!value.result.items.length && <p>No matching passages were found. Try another query or document set.</p>}
    <ol>
      {value.result.items.map(item => <li key={`${item.run_id}:${item.ordinal}`}>
        <div className="retrieval-hit-title"><h3>{item.rank}. {item.filename}</h3><Button variant="outline" onClick={() => onInspect(item)}>View passage {item.rank}</Button></div>
        <p>{item.text}</p>
        <span className="field-hint">Passage {item.ordinal + 1}{item.page_number ? ` · Page ${item.page_number}` : ''} · Distance {item.cosine_distance.toFixed(4)}</span>
      </li>)}
    </ol>
    <p className="field-hint">Distance measures closeness to the query. Lower is closer; it is not confidence.</p>
  </section>;
}

export function RetrievalInspector({ item }: { item: Evidence }) {
  return <section className="answer-inspector" aria-label="Retrieved passage">
    <h2>{item.filename}</h2>
    <p className="field-hint">Rank {item.rank} · Passage {item.ordinal + 1}{item.page_number ? ` · Page ${item.page_number}` : ''}</p>
    <p className="rag-source-text">{item.text}</p>
    <details className="source-metadata"><summary>Source details</summary>
      <p>Processing version {item.processing_version} · Characters {item.start_char}–{item.end_char}</p>
      <p>Distance {item.cosine_distance.toFixed(4)} · Lower is closer, not confidence.</p>
      <p>Document {item.document_id}</p>
    </details>
  </section>;
}
