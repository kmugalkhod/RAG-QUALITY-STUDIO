import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { RetrievalSettingsForm } from '../../../components/RetrievalSettingsForm';
import type { RetrievalSettings } from '../../../lib/retrieval';
import { formatIndexOption, type IndexVersion } from '../../documents/model';

interface RetrievalTestSettingsProps {
  indexes: IndexVersion[];
  indexId: string;
  retrieval: RetrievalSettings;
  disabled: boolean;
  onIndexChange: (indexId: string) => void;
  onChange: (settings: RetrievalSettings) => void;
}

export function RetrievalTestSettings({
  indexes,
  indexId,
  retrieval,
  disabled,
  onIndexChange,
  onChange,
}: RetrievalTestSettingsProps) {
  return (
    <div className="retrieval-test-settings">
      <h2>Retrieval settings</h2>
      <fieldset disabled={disabled}>
        <Label>
          Documents to search
          <NativeSelect value={indexId} onChange={(event) => onIndexChange(event.target.value)}>
            <NativeSelectOption value="">Choose prepared documents</NativeSelectOption>
            {indexes.map((index) => (
              <NativeSelectOption key={index.id} value={index.id}>
                {formatIndexOption(index)}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Label>
        <RetrievalSettingsForm value={retrieval} onChange={onChange} />
        <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
          This test does not call an answer model.
        </p>
      </fieldset>
    </div>
  );
}
