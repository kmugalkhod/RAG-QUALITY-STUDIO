import type { FormEvent } from 'react';
import { Button } from '../../../components/ui/button';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { RetrievalSettingsForm } from '../../../components/RetrievalSettingsForm';
import { formatRetrievalScores, type RetrievalSettings } from '../../../lib/retrieval';
import type { IndexVersion, Retrieval } from '../model';

export function IndexSearch({
  selected,
  query,
  settings,
  searching,
  error,
  result,
  onQueryChange,
  onSettingsChange,
  onSubmit,
}: {
  selected?: IndexVersion;
  query: string;
  settings: RetrievalSettings;
  searching: boolean;
  error: string;
  result?: Retrieval;
  onQueryChange: (value: string) => void;
  onSettingsChange: (value: RetrievalSettings) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <details className="chunk-inspector" open={!!selected}>
      <summary>Search documents only</summary>
      <p>
        {selected
          ? `Searching document set · Version ${selected.version}`
          : 'Choose a ready document set above.'}
      </p>
      <form onSubmit={onSubmit} noValidate aria-busy={searching}>
        <Label htmlFor="retrieval-query">Search query</Label>
        <Textarea
          id="retrieval-query"
          rows={3}
          maxLength={8000}
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          disabled={searching}
        />
        <RetrievalSettingsForm value={settings} disabled={searching} onChange={onSettingsChange} />
        <Button type="submit" disabled={searching || !selected}>
          {searching ? 'Searching…' : 'Search documents only'}
        </Button>
        <p className="field-hint">Returns passages only. It does not generate an answer.</p>
      </form>
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      {result && (
        <section aria-label="Retrieval results">
          <p role="status">
            {result.items.length} passages from document set version {result.index_version}
          </p>
          {!result.items.length && <p>No matching passages in this document set.</p>}
          <ol className="chunk-list">
            {result.items.map((item) => (
              <li key={`${item.run_id}-${item.ordinal}`}>
                <h3>
                  {item.rank}. {item.filename}
                </h3>
                <p className="chunk-provenance">
                  {formatRetrievalScores(item)} · Processing version {item.processing_version} ·
                  Chunk {item.ordinal + 1} ·{' '}
                  {item.page_number ? `PDF page ${item.page_number} · ` : ''}Characters{' '}
                  {item.start_char}–{item.end_char}
                </p>
                <pre>{item.text}</pre>
                <details className="source-metadata">
                  <summary>Source identity</summary>
                  <p>Document: {item.document_id}</p>
                  <p>Processing run: {item.run_id}</p>
                  <p>SHA-256: {item.content_hash}</p>
                </details>
              </li>
            ))}
          </ol>
        </section>
      )}
    </details>
  );
}
