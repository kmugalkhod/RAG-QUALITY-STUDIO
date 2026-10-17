import { useId, useState } from 'react';

import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { FIELD_ERROR } from './settingsStyles';

/** The values in a typed list: one per line (or comma), blank entries dropped. */
export function parseList(text: string, separator: '\n' | ',', trim: boolean): string[] {
  return text
    .split(separator)
    .map((value) => value.replace(/\r$/, ''))
    .map((value) => (trim ? value.trim() : value))
    .filter((value) => value.trim() !== '');
}

/**
 * A text box for a list of values (spec 0012 A17). It keeps exactly what is typed, spaces
 * and new lines included, and saves the parsed list as you type; the box shows the parsed
 * list again when it loses focus. Literals keep their spaces; names are trimmed.
 */
export function ListTextField({
  label,
  values,
  separator = '\n',
  trim = false,
  placeholder,
  hint,
  error,
  onChange,
}: {
  label: string;
  values: string[];
  separator?: '\n' | ',';
  trim?: boolean;
  placeholder?: string;
  hint?: string;
  error?: string;
  onChange: (values: string[]) => void;
}) {
  const id = useId();
  const joiner = separator === ',' ? ', ' : '\n';
  const [text, setText] = useState(values.join(joiner));
  // A reset or another edit outside this box replaces the typed text.
  const [seen, setSeen] = useState(values);
  if (
    seen !== values &&
    parseList(text, separator, trim).join('\u0000') !== values.join('\u0000')
  ) {
    setSeen(values);
    setText(values.join(joiner));
  }
  const described = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ');
  const props = {
    value: text,
    placeholder,
    'aria-invalid': !!error,
    'aria-describedby': described || undefined,
    onChange: (event: { target: { value: string } }) => {
      setText(event.target.value);
      const parsed = parseList(event.target.value, separator, trim);
      setSeen(parsed);
      onChange(parsed);
    },
    onBlur: () => setText(parseList(text, separator, trim).join(joiner)),
  };
  return (
    <div className="flex flex-col gap-2">
      <Label>
        {label}
        {separator === '\n' ? <Textarea {...props} /> : <Input {...props} />}
      </Label>
      {hint && (
        <small id={`${id}-hint`} className="text-xs text-foreground-muted">
          {hint}
        </small>
      )}
      {error && (
        <small id={`${id}-error`} role="alert" className={FIELD_ERROR}>
          {error}
        </small>
      )}
    </div>
  );
}
