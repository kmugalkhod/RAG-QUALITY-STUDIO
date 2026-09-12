import type { FormEvent } from 'react';
import { Button } from '../../../components/ui/button';
import { Checkbox } from '../../../components/ui/checkbox';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import type { PipelineVersion } from '../../pipelines/model';
import * as api from '../api';
import { type Dataset, type Metric, metricLabel } from '../model';
import { Configuration } from './Configuration';
import { Questions } from './Questions';

const metrics = Object.keys(metricLabel) as Metric[];
type EvaluationOptions = Awaited<ReturnType<typeof api.getEvaluationOptions>>;

export function ExperimentForm({
  projectId,
  datasets,
  pipelines,
  options,
  name,
  datasetId,
  candidateA,
  candidateB,
  selectedMetrics,
  busy,
  storageError,
  onNameChange,
  onDatasetChange,
  onCandidateAChange,
  onCandidateBChange,
  onMetricsChange,
  onReset,
  onSubmit,
}: {
  projectId: string;
  datasets: Dataset[];
  pipelines: PipelineVersion[];
  options?: EvaluationOptions;
  name: string;
  datasetId: string;
  candidateA: string;
  candidateB: string;
  selectedMetrics: Metric[];
  busy: boolean;
  storageError: string;
  onNameChange: (value: string) => void;
  onDatasetChange: (value: string) => void;
  onCandidateAChange: (value: string) => void;
  onCandidateBChange: (value: string) => void;
  onMetricsChange: (value: Metric[]) => void;
  onReset: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const candidates = [
    {
      label: 'A',
      value: candidateA,
      other: candidateB,
      required: true,
      onChange: onCandidateAChange,
    },
    {
      label: 'B',
      value: candidateB,
      other: candidateA,
      required: false,
      onChange: onCandidateBChange,
    },
  ];

  return (
    <section className="experiment-section mt-6 border-t border-border py-6">
      <div className="experiment-heading mb-5 flex items-center justify-between gap-5">
        <h2>Run an experiment</h2>
        <Button variant="outline" disabled={busy} onClick={onReset}>
          Reset draft
        </Button>
      </div>
      <p className="draft-notice" role="status">
        {storageError || 'Draft saved in this browser tab.'}
      </p>
      {options?.error && <p role="alert">{options.error}</p>}
      {!pipelines.length && (
        <p>
          Save a pipeline in <a href={`#/projects/${projectId}/pipelines`}>Pipelines</a> before
          running an experiment.
        </p>
      )}
      <form onSubmit={onSubmit}>
        <div className="experiment-fields my-5 grid grid-cols-2 gap-5">
          <Label>
            Experiment name
            <Input
              required
              maxLength={120}
              value={name}
              onChange={(event) => onNameChange(event.target.value)}
            />
          </Label>
          <Label>
            Dataset version
            <NativeSelect
              required
              value={datasetId}
              onChange={(event) => onDatasetChange(event.target.value)}
            >
              <NativeSelectOption value="">Select reviewed questions</NativeSelectOption>
              {datasets.map((dataset) => (
                <NativeSelectOption key={dataset.id} value={dataset.id}>
                  {dataset.name} · v{dataset.version} · {dataset.rows.length} questions
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Label>
        </div>
        {datasetId && (
          <details>
            <summary>Inspect dataset questions</summary>
            <Questions rows={datasets.find((dataset) => dataset.id === datasetId)?.rows || []} />
          </details>
        )}
        <div className="experiment-fields my-5 grid grid-cols-2 gap-5">
          {candidates.map((candidate) => (
            <div key={candidate.label}>
              <Label>
                Candidate {candidate.label}
                {candidate.required ? '' : ' (optional)'}
                <NativeSelect
                  required={candidate.required}
                  value={candidate.value}
                  onChange={(event) => candidate.onChange(event.target.value)}
                >
                  <NativeSelectOption value="">
                    {candidate.required ? 'Select a saved pipeline version' : 'Single candidate'}
                  </NativeSelectOption>
                  {pipelines
                    .filter((pipeline) => pipeline.id !== candidate.other)
                    .map((pipeline) => (
                      <NativeSelectOption key={pipeline.id} value={pipeline.id}>
                        {pipeline.name} · v{pipeline.version}
                      </NativeSelectOption>
                    ))}
                </NativeSelect>
              </Label>
              {pipelines.find((pipeline) => pipeline.id === candidate.value) && (
                <Configuration
                  version={pipelines.find((pipeline) => pipeline.id === candidate.value)!}
                />
              )}
            </div>
          ))}
        </div>
        <fieldset>
          <legend>Evaluation metrics</legend>
          {metrics.map((metric) => (
            <Label
              className="metric-choice my-4 flex items-start gap-3"
              key={metric}
              htmlFor={`metric-${metric}`}
            >
              <Checkbox
                id={`metric-${metric}`}
                checked={selectedMetrics.includes(metric)}
                onCheckedChange={(checked) =>
                  onMetricsChange(
                    checked === true
                      ? [...selectedMetrics, metric]
                      : selectedMetrics.filter((value) => value !== metric),
                  )
                }
              />
              <span>
                <strong>{metricLabel[metric]}</strong>
                <small>{options?.metrics[metric]}</small>
              </span>
            </Label>
          ))}
        </fieldset>
        <p>
          Evaluator: <strong>{options?.model || 'Not configured'}</strong>. Scores use paid model
          calls and require human review.
        </p>
        <Button
          disabled={
            busy ||
            !!options?.error ||
            !datasetId ||
            !candidateA ||
            !selectedMetrics.length ||
            !name.trim()
          }
        >
          {busy ? 'Submitting…' : 'Run experiment'}
        </Button>
      </form>
    </section>
  );
}
