import { META, PRE } from './parts';

/**
 * What a passage is searched as, when that is not just its text (spec 0015 U4):
 * the section prefix, and the searched text when it differs from the passage, as
 * for a table row searched by its "column: value" pairs. Null when they match.
 */
export function searchedAsParts(
  text: string,
  embeddingText: string | null | undefined,
  prefix: string | null | undefined,
): { prefix: string; body: string | null } | null {
  if (!embeddingText || embeddingText === text) {
    return null;
  }
  const head = prefix && embeddingText.startsWith(prefix) ? prefix : '';
  const rest = embeddingText.slice(head.length);
  const body = rest === text ? null : rest;
  if (!head.trim() && body === null) {
    return null;
  }
  return { prefix: head.trim(), body };
}

export function SearchedAs({
  label,
  text,
  embeddingText,
  prefix,
}: {
  label: string;
  text: string;
  embeddingText: string | null | undefined;
  prefix: string | null | undefined;
}) {
  const parts = searchedAsParts(text, embeddingText, prefix);
  if (!parts) {
    return null;
  }
  return (
    <section aria-label={label} className="flex flex-col gap-1">
      <small className={META}>
        Searched as
        {parts.body === null ? ' · section prefix, then the passage text' : ''}
      </small>
      <pre className={PRE}>{[parts.prefix, parts.body].filter((value) => value).join('\n\n')}</pre>
    </section>
  );
}
