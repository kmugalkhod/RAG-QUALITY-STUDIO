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

const HINT = 'text-xs text-foreground-muted';

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
      className="flex min-w-0 flex-col gap-3"
      disabled={disabled}
      aria-describedby={errors.length ? `${id}-errors` : undefined}
    >
      <legend className="mb-3 text-sm font-semibold text-foreground">Search settings</legend>
      <Label>
        Search method
        <NativeSelect
          className="mt-2"
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
          className="mt-2"
          type="number"
          min={retrievalLimits.topK.min}
          max={retrievalLimits.topK.max}
          step={1}
          value={Number.isFinite(value.top_k) ? value.top_k : ''}
          onChange={(e) => onChange({ ...value, top_k: e.target.valueAsNumber })}
        />
      </Label>
      <p className={HINT}>
        Maximum chunks returned to the next node. Search can return fewer matches.
      </p>
      {value.mode !== 'keyword' && (
        <details className="group flex flex-col border-t border-border pt-2">
          <summary className="flex min-h-row items-center text-sm font-medium text-foreground">
            Advanced search settings
          </summary>
          <div className="flex flex-col gap-3 pt-2">
            <Label>
              Maximum vector distance (optional)
              <Input
                className="mt-2"
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
            <p className={HINT}>
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
                    className="mt-2"
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
                    className="mt-2"
                    type="number"
                    min={value.top_k}
                    max={retrievalLimits.candidateCount.max}
                    step={1}
                    value={
                      Number.isFinite(value.keyword_candidates) ? value.keyword_candidates : ''
                    }
                    onChange={(e) =>
                      onChange({ ...value, keyword_candidates: e.target.valueAsNumber })
                    }
                  />
                </Label>
                <p className={HINT}>
                  Candidates gathered by each branch before merging. Each count must be at least Top
                  k.
                </p>
                <Label>
                  Vector weight
                  <Input
                    className="mt-2"
                    type="number"
                    min={retrievalLimits.vectorWeight.min}
                    max={retrievalLimits.vectorWeight.max}
                    step="any"
                    value={Number.isFinite(value.vector_weight) ? value.vector_weight : ''}
                    onChange={(e) => onChange({ ...value, vector_weight: e.target.valueAsNumber })}
                  />
                </Label>
                <p className={HINT}>
                  Keyword weight:{' '}
                  {Number.isFinite(value.vector_weight)
                    ? Number((1 - value.vector_weight).toFixed(4))
                    : '—'}
                  . Weights influence rank fusion, not the percentage of results. A zero-weight
                  branch is skipped.
                </p>
              </>
            )}
          </div>
        </details>
      )}
      {value.mode === 'keyword' && (
        <p className={HINT}>
          Searches words and phrases in the prepared chunks. No query embedding is needed.
        </p>
      )}
      {!!errors.length && (
        <ul
          id={`${id}-errors`}
          className="flex flex-col gap-1 text-xs text-danger"
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
