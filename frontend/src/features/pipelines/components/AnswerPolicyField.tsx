import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { Label } from '../../../components/ui/label';
import { META } from '../../../components/parts';
import { getAnswerPolicy, type AnswerPolicy } from '../model';

interface Props {
  value: AnswerPolicy | undefined;
  onChange: (policy: AnswerPolicy) => void;
}

// Saved versions without a policy keep the original strict prompt.
export function AnswerPolicyField({ value, onChange }: Props) {
  const policy = getAnswerPolicy(value);
  return (
    <>
      <Label className="mb-0">
        Answer style
        <NativeSelect
          className="mt-2"
          aria-label="Answer style"
          value={policy}
          onChange={(e) => onChange(e.target.value as AnswerPolicy)}
        >
          <NativeSelectOption value="complete-v2">
            Complete answers (recommended)
          </NativeSelectOption>
          <NativeSelectOption value="strict-v1">Strict (original)</NativeSelectOption>
        </NativeSelect>
      </Label>
      <p className={META}>
        {policy === 'complete-v2'
          ? 'Gives a full answer with steps and code from the sources, answers the supported part of a question and names what the sources do not cover. Each source is sent once and repeated passages are skipped.'
          : 'Refuses with insufficient evidence unless the sources answer the whole question. Earlier saved versions use this style.'}
      </p>
    </>
  );
}
