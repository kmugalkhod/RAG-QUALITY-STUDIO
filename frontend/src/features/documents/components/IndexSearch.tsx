import type { FormEvent } from 'react';
import { Button } from '../../../components/ui/button';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { RetrievalSettingsForm } from '../../../components/RetrievalSettingsForm';
import { formatRetrievalScores, type RetrievalSettings } from '../../../lib/retrieval';
import type { IndexVersion, Retrieval } from '../model';
import { EmptyState } from '../../../components/states/EmptyState';
import { cn } from '../../../lib/utils';
import { CARD, InlineError, LIST, LIST_ROW, META, SUMMARY } from '../../../components/parts';

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
    <section className="flex flex-col gap-6">
      <p className={META}>
        {selected
          ? `Testing ${selected.knowledge_set_name} · immutable version ${selected.version}${selected.is_current ? ' · current' : ' · historical'}`
          : 'Choose a ready collection version to test.'}
      </p>
      <form
        onSubmit={onSubmit}
        noValidate
        aria-busy={searching}
        className={cn(CARD, 'flex flex-col gap-4 p-4')}
      >
        <div className="flex flex-col">
          <Label htmlFor="retrieval-query">Search query</Label>
          <Textarea
            id="retrieval-query"
            rows={3}
            maxLength={8000}
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            disabled={searching}
          />
        </div>
        <RetrievalSettingsForm value={settings} disabled={searching} onChange={onSettingsChange} />
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <p className={META}>Returns passages only. It does not generate an answer.</p>
          <Button type="submit" disabled={searching || !selected} className="max-md:w-full">
            {searching ? 'Testing retrieval…' : 'Run retrieval test'}
          </Button>
        </div>
      </form>
      {error && <InlineError>{error}</InlineError>}
      {result && (
        <section aria-label="Retrieval results" className="flex flex-col gap-3">
          <p role="status" className="text-sm text-foreground">
            {result.items.length} passages from immutable collection version {result.index_version}
          </p>
          {!result.items.length && (
            <EmptyState title="No matching passages in this document set." />
          )}
          {result.items.length > 0 && (
            <ol className={LIST}>
              {result.items.map((item) => (
                <li
                  key={`${item.run_id}-${item.ordinal}`}
                  className={cn(LIST_ROW, 'flex flex-col gap-2 p-4')}
                >
                  <h3 className="text-sm font-semibold text-foreground wrap-anywhere">
                    {item.rank}. {item.filename}
                  </h3>
                  <p className={cn(META, 'tabular-nums')}>
                    {formatRetrievalScores(item)} · Processing version {item.processing_version} ·
                    Chunk {item.ordinal + 1} ·{' '}
                    {item.page_number ? `PDF page ${item.page_number} · ` : ''}Characters{' '}
                    {item.start_char}–{item.end_char}
                  </p>
                  <pre className="font-mono text-xs whitespace-pre-wrap text-foreground wrap-anywhere">
                    {item.text}
                  </pre>
                  <details>
                    <summary className={SUMMARY}>Source identity</summary>
                    <div className={cn(META, 'flex flex-col gap-1 pb-2 wrap-anywhere')}>
                      <p>Document: {item.document_id}</p>
                      <p>Processing run: {item.run_id}</p>
                      <p>SHA-256: {item.content_hash}</p>
                    </div>
                  </details>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </section>
  );
}
