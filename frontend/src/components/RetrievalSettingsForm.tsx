import { Input } from './ui/input';
import { NativeSelect, NativeSelectOption } from './ui/native-select';
import { Label } from './ui/label';
import { useId } from 'react';
import {
  changeRetrievalMode,
  retrievalLimits,
  validateRetrievalSettings,
  type RetrievalMode,
  type RetrievalSettings,
} from '../lib/retrieval';
export function RetrievalSettingsForm({
  value,
  onChange,
  disabled = false,
}: {
  value: RetrievalSettings;
  onChange: (value: RetrievalSettings) => void;
  disabled?: boolean;
}) {
  const id = useId();
  const errors = validateRetrievalSettings(value);
  const cutoff = value.mode !== 'keyword' ? value.max_vector_distance : null;
  return (
    <fieldset
      className="retrieval-settings-form border-0 p-0 mt-6 mx-0 mb-3 min-w-0 grid gap-3"
      disabled={disabled}
      aria-describedby={errors.length ? `${id}-errors` : undefined}
    >
      <legend>Search settings</legend>
      <Label>
        Search method
        <NativeSelect
          value={value.mode}
          onChange={(event) =>
            onChange(changeRetrievalMode(value, event.currentTarget.value as RetrievalMode))
          }
        >
          <NativeSelectOption value="vector">Vector</NativeSelectOption>
          <NativeSelectOption value="keyword">Keyword</NativeSelectOption>
          <NativeSelectOption value="hybrid">Hybrid</NativeSelectOption>
        </NativeSelect>
      </Label>
      <Label>
        Top k
        <Input
          type="number"
          min={retrievalLimits.topK.min}
          max={retrievalLimits.topK.max}
          step={1}
          value={Number.isFinite(value.top_k) ? value.top_k : ''}
          onChange={(e) => onChange({ ...value, top_k: e.target.valueAsNumber })}
        />
      </Label>
      <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
        Maximum chunks returned to the next node. Search can return fewer matches.
      </p>
      {value.mode !== 'keyword' && (
        <details className="retrieval-advanced border-t border-border pt-3">
          <summary>Advanced search settings</summary>
          <Label>
            Maximum vector distance (optional)
            <Input
              type="number"
              min={retrievalLimits.vectorDistance.min}
              max={retrievalLimits.vectorDistance.max}
              step="any"
              placeholder="Off"
              value={cutoff != null && Number.isFinite(cutoff) ? cutoff : ''}
              onChange={(e) =>
                onChange({
                  ...value,
                  max_vector_distance: e.target.value === '' ? null : e.target.valueAsNumber,
                })
              }
            />
          </Label>
          <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
            Leave blank for no cutoff. Lower distance is closer, not confidence.
            {value.mode === 'hybrid'
              ? ' Limits the vector branch only; keyword matches can still appear.'
              : ''}
          </p>
          {value.mode === 'hybrid' && (
            <>
              <Label>
                Vector candidate count
                <Input
                  type="number"
                  min={value.top_k}
                  max={retrievalLimits.candidateCount.max}
                  step={1}
                  value={Number.isFinite(value.vector_candidates) ? value.vector_candidates : ''}
                  onChange={(e) =>
                    onChange({ ...value, vector_candidates: e.target.valueAsNumber })
                  }
                />
              </Label>
              <Label>
                Keyword candidate count
                <Input
                  type="number"
                  min={value.top_k}
                  max={retrievalLimits.candidateCount.max}
                  step={1}
                  value={Number.isFinite(value.keyword_candidates) ? value.keyword_candidates : ''}
                  onChange={(e) =>
                    onChange({ ...value, keyword_candidates: e.target.valueAsNumber })
                  }
                />
              </Label>
              <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
                Candidates gathered by each branch before merging. Each count must be at least Top
                k.
              </p>
              <Label>
                Vector weight
                <Input
                  type="number"
                  min={retrievalLimits.vectorWeight.min}
                  max={retrievalLimits.vectorWeight.max}
                  step="any"
                  value={Number.isFinite(value.vector_weight) ? value.vector_weight : ''}
                  onChange={(e) => onChange({ ...value, vector_weight: e.target.valueAsNumber })}
                />
              </Label>
              <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
                Keyword weight:{' '}
                {Number.isFinite(value.vector_weight)
                  ? Number((1 - value.vector_weight).toFixed(4))
                  : '—'}
                . Weights influence rank fusion, not the percentage of results. A zero-weight branch
                is skipped.
              </p>
            </>
          )}
        </details>
      )}
      {value.mode === 'keyword' && (
        <p className="field-hint text-[11px] text-muted-foreground mt-2 leading-relaxed">
          Searches words and phrases in the prepared chunks. No query embedding is needed.
        </p>
      )}
      {!!errors.length && (
        <ul
          id={`${id}-errors`}
          className="error-message text-xs mt-4 text-destructive"
          aria-live="polite"
        >
          {errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      )}
    </fieldset>
  );
}
