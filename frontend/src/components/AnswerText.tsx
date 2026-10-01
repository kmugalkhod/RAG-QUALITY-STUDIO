import { Button } from './ui/button';
import { cn } from '../lib/utils';
import { Fragment, type ReactNode } from 'react';
// Deliberately small, inert formatting vocabulary for untrusted model output.
// No HTML parsing, external links/images, or execution. Unknown syntax stays text.
export function AnswerText({
  text,
  citations = [],
  onCitation,
}: {
  text: string;
  citations?: string[];
  onCitation?: (label: string) => void;
}) {
  function inline(value: string, depth = 0): ReactNode {
    if (depth > 3) {
      return value;
    }
    const parts = value.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|\[[^\]\n[]+\])/g);
    return parts.map((part, i) => {
      if (part.startsWith('`') && part.endsWith('`')) {
        return <code key={i}>{part.slice(1, -1)}</code>;
      }
      if (
        (part.startsWith('**') && part.endsWith('**')) ||
        (part.startsWith('__') && part.endsWith('__'))
      ) {
        return <strong key={i}>{inline(part.slice(2, -2), depth + 1)}</strong>;
      }
      if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
        return <em key={i}>{inline(part.slice(1, -1), depth + 1)}</em>;
      }
      const label = part.slice(1, -1);
      if (part.startsWith('[') && part.endsWith(']') && citations.includes(label) && onCitation) {
        return (
          <Button
            variant="link"
            type="button"
            size="sm"
            className="inline h-auto px-1 align-baseline whitespace-normal underline pointer-coarse:inline-flex pointer-coarse:h-auto pointer-coarse:min-h-row pointer-coarse:min-w-row pointer-coarse:align-middle"
            key={i}
            onClick={() => onCitation(label)}
          >
            {part}
          </Button>
        );
      }
      return <Fragment key={i}>{part}</Fragment>;
    });
  }
  const lines = text.replaceAll('\r\n', '\n').split('\n');
  const blocks: ReactNode[] = [];
  for (let i = 0; i < lines.length; ) {
    const key = i;
    if (!lines[i].trim()) {
      i++;
      continue;
    }
    if (/^\s*```/.test(lines[i])) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) {
        code.push(lines[i++]);
      }
      if (i < lines.length) {
        i++;
      }
      blocks.push(
        <pre key={key}>
          <code>{code.join('\n')}</code>
        </pre>,
      );
      continue;
    }
    const list = /^\s*(?:([-+*])|(\d+)\.)\s+(.+)$/.exec(lines[i]);
    if (list) {
      const ordered = !!list[2];
      const items: ReactNode[] = [];
      while (i < lines.length) {
        const match = /^\s*(?:([-+*])|(\d+)\.)\s+(.+)$/.exec(lines[i]);
        if (!match || !!match[2] !== ordered) {
          break;
        }
        items.push(<li key={i}>{inline(match[3])}</li>);
        i++;
      }
      blocks.push(
        ordered ? (
          <ol key={key} start={Number(list[2])}>
            {items}
          </ol>
        ) : (
          <ul key={key}>{items}</ul>
        ),
      );
      continue;
    }
    if (/^#{1,6}\s+/.test(lines[i])) {
      blocks.push(
        <p key={key}>
          <strong>{inline(lines[i++].replace(/^#{1,6}\s+/, ''))}</strong>
        </p>,
      );
      continue;
    }
    const paragraph = [lines[i++]];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^\s*(?:```|#{1,6}\s|[-+*]\s|\d+\.\s)/.test(lines[i])
    ) {
      paragraph.push(lines[i++]);
    }
    blocks.push(<p key={key}>{inline(paragraph.join('\n'))}</p>);
  }
  return (
    <div
      data-slot="answer-text"
      className={cn(
        'leading-6 wrap-anywhere whitespace-normal [&_p]:mb-3 [&_p]:whitespace-pre-wrap [&_p:last-child]:mb-0',
        '[&_:is(ul,ol)]:my-3 [&_:is(ul,ol)]:pl-6 [&_li]:my-1 [&_ol]:list-decimal [&_ul]:list-disc',
        '[&_code]:rounded-control [&_code]:bg-surface-hover [&_code]:px-1 [&_code]:font-mono [&_code]:text-sm',
        '[&_pre]:my-3 [&_pre]:rounded-control [&_pre]:bg-surface-hover [&_pre]:p-3 [&_pre]:whitespace-pre-wrap [&_pre]:wrap-anywhere [&_pre_code]:p-0',
      )}
    >
      {blocks}
    </div>
  );
}
