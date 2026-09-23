import { useState, type FormEvent } from 'react';
import { Button } from '../../../components/ui/button';
import { Checkbox } from '../../../components/ui/checkbox';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import type { PipelineVersion } from '../../pipelines/model';
import type { IndexVersion } from '../../documents/model';
import * as api from '../api';
import { type Dataset, type Metric, metricLabel } from '../model';
import { Configuration } from './Configuration';

const metrics = Object.keys(metricLabel) as Metric[];
type EvaluationOptions = Awaited<ReturnType<typeof api.getEvaluationOptions>>;

export function ExperimentForm({
  projectId,
  datasets,
  pipelines,
  indexes,
  options,
  name,
  datasetId,
  candidateA,
  candidateB,
  selectedMetrics,
  busy,
  storageError,
  onNameChange,
  onCandidateAChange,
  onCandidateBChange,
  onMetricsChange,
  onReset,
  onSubmit,
}: {
  projectId: string;
  datasets: Dataset[];
  pipelines: PipelineVersion[];
  indexes: IndexVersion[];
  options?: EvaluationOptions;
  name: string;
  datasetId: string;
  candidateA: string;
  candidateB: string;
  selectedMetrics: Metric[];
  busy: boolean;
  storageError: string;
  onNameChange: (value: string) => void;
  onCandidateAChange: (value: string) => void;
  onCandidateBChange: (value: string) => void;
  onMetricsChange: (value: Metric[]) => void;
  onReset: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const [candidateStageOpen, setCandidateStageOpen] = useState(true);
  const [metricsStageOpen, setMetricsStageOpen] = useState(true);
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
  const candidateIndexes = [candidateA, candidateB].filter(Boolean).map((id) => {
    const version = pipelines.find((value) => value.id === id);
    const indexId = version?.execution.nodes.find((node) => node.type === 'retriever')?.index_id;
    return indexes.find((index) => index.id === indexId);
  });
  const sameSnapshot =
    candidateIndexes.length === 2 &&
    candidateIndexes.every(
      (index) =>
        index?.source_snapshot_id &&
        index.source_snapshot_id === candidateIndexes[0]?.source_snapshot_id,
    );
  const selectedDataset = datasets.find((dataset) => dataset.id === datasetId);
  const selectedCandidateCount = [candidateA, candidateB].filter(Boolean).length;

  return (
    <form className="experiment-workbench" onSubmit={onSubmit}>
      <div className="experiment-stage-stack">
        <details
          className="experiment-stage"
          open={candidateStageOpen}
          onToggle={(event) => setCandidateStageOpen(event.currentTarget.open)}
        >
          <summary>
            <span className="experiment-stage-index" aria-hidden="true">
              2
            </span>
            <span>
              <strong>Candidate configurations</strong>
              <small>Select one saved version to evaluate, or two to compare.</small>
            </span>
          </summary>
          <div className="experiment-stage-body">
            {candidateIndexes.length === 2 && (
              <p className={sameSnapshot ? 'success-message' : 'index-difference'}>
                {sameSnapshot
                  ? `Same source snapshot · Snapshot ${candidateIndexes[0]?.source_snapshot_number}`
                  : 'Comparison caveat: these candidates use different source snapshots, or legacy lineage is unavailable. Content changes may affect results.'}
              </p>
            )}
            <div className="candidate-columns">
              {candidates.map((candidate) => (
                <div className="candidate-column" key={candidate.label}>
                  <Label>
                    Candidate {candidate.label}
                    {candidate.required ? '' : ' (optional)'}
                    <NativeSelect
                      required={candidate.required}
                      value={candidate.value}
                      onChange={(event) => candidate.onChange(event.target.value)}
                    >
                      <NativeSelectOption value="">
                        {candidate.required
                          ? 'Select a saved pipeline version'
                          : 'Single candidate'}
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
          </div>
        </details>
        <details
          className="experiment-stage"
          open={metricsStageOpen}
          onToggle={(event) => setMetricsStageOpen(event.currentTarget.open)}
        >
          <summary>
            <span className="experiment-stage-index" aria-hidden="true">
              3
            </span>
            <span>
              <strong>Metrics &amp; execution</strong>
              <small>Name the run, choose measures, then review the execution summary.</small>
            </span>
          </summary>
          <div className="experiment-stage-body">
            <Label className="experiment-name-field">
              Experiment name
              <Input
                required
                maxLength={120}
                value={name}
                onChange={(event) => onNameChange(event.target.value)}
              />
            </Label>
            <fieldset>
              <legend>Evaluation metrics</legend>
              <div className="metric-grid">
                {metrics.map((metric) => (
                  <Label className="metric-choice" key={metric} htmlFor={`metric-${metric}`}>
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
              </div>
            </fieldset>
            <p className="evaluator-note">
              Evaluator: <strong>{options?.model || 'Not configured'}</strong>. Scores use paid
              model calls, can vary between runs, and require human review.
            </p>
          </div>
        </details>
      </div>
      <aside className="experiment-run-summary" aria-label="Experiment run summary">
        <div>
          <h2>Run summary</h2>
          <p className="draft-notice" role="status">
            {storageError || 'Draft saved in this browser tab.'}
          </p>
        </div>
        {options?.error && (
          <p role="alert" className="error-message">
            {options.error}
          </p>
        )}
        {!pipelines.length && (
          <p>
            Save a pipeline in <a href={`#/projects/${projectId}/pipelines`}>Pipelines</a> before
            running an experiment.
          </p>
        )}
        <dl>
          <div>
            <dt>Dataset</dt>
            <dd>
              {selectedDataset
                ? `${selectedDataset.name} · v${selectedDataset.version}`
                : 'Not selected'}
            </dd>
          </div>
          <div>
            <dt>Candidates</dt>
            <dd>{selectedCandidateCount || 'None selected'}</dd>
          </div>
          <div>
            <dt>Metrics</dt>
            <dd>{selectedMetrics.length}</dd>
          </div>
          <div>
            <dt>Evaluator</dt>
            <dd>{options?.model || 'Unavailable'}</dd>
          </div>
        </dl>
        <Button
          type="submit"
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
        <Button variant="ghost" disabled={busy} onClick={onReset}>
          Reset draft
        </Button>
      </aside>
    </form>
  );
}
