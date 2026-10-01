import { useState, type FormEvent } from 'react';
import { ChevronDown } from 'lucide-react';
import { Callout, CARD, InlineError } from '../../../components/parts';
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
import { docsHref } from '../../../lib/docs';

import { StageNumber } from './parts';

const metrics = Object.keys(metricLabel) as Metric[];
const STAGE = `${CARD} group flex min-w-0 flex-col`;
const STAGE_SUMMARY =
  'flex min-h-row list-none items-start gap-3 rounded-card p-4 outline-none focus-visible:outline-2 focus-visible:outline-accent md:p-6 [&::-webkit-details-marker]:hidden';
const CHEVRON =
  'mt-1 size-4 shrink-0 text-foreground-subtle transition-transform duration-(--transition-fast) group-open:rotate-180';
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

  const candidateNote =
    candidateIndexes.length === 2 ? (
      sameSnapshot ? (
        <Callout tone="success">
          Same source snapshot · Snapshot {candidateIndexes[0]?.source_snapshot_number}
        </Callout>
      ) : (
        <Callout tone="warning">
          Comparison caveat: these candidates use different source snapshots, or legacy lineage is
          unavailable. Content changes may affect results.
        </Callout>
      )
    ) : null;
  return (
    // display: contents lets the stages and the summary join the page grid while staying one form.
    <form className="contents" onSubmit={onSubmit}>
      <div className="flex min-w-0 flex-col gap-4 desktop:col-start-1">
        <details
          className={STAGE}
          open={candidateStageOpen}
          onToggle={(event) => setCandidateStageOpen(event.currentTarget.open)}
        >
          <summary className={STAGE_SUMMARY}>
            <StageNumber>2</StageNumber>
            <span className="flex min-w-0 flex-1 flex-col gap-1">
              <strong className="text-base font-semibold text-foreground">
                Candidate configurations
              </strong>
              <small className="text-sm text-foreground-muted">
                Select one saved version to evaluate, or two to compare.
              </small>
            </span>
            <ChevronDown aria-hidden="true" className={CHEVRON} />
          </summary>
          <div className="flex flex-col gap-4 px-4 pb-4 md:px-6 md:pb-6">
            {candidateNote}
            <div className="grid gap-4 md:grid-cols-2">
              {candidates.map((candidate) => {
                const version = pipelines.find((pipeline) => pipeline.id === candidate.value);
                return (
                  <div className="flex min-w-0 flex-col gap-3" key={candidate.label}>
                    <Label className="mb-0">
                      Candidate {candidate.label}
                      {candidate.required ? '' : ' (optional)'}
                      <NativeSelect
                        className="mt-2"
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
                    {version && <Configuration version={version} />}
                  </div>
                );
              })}
            </div>
          </div>
        </details>
        <details
          className={STAGE}
          open={metricsStageOpen}
          onToggle={(event) => setMetricsStageOpen(event.currentTarget.open)}
        >
          <summary className={STAGE_SUMMARY}>
            <StageNumber>3</StageNumber>
            <span className="flex min-w-0 flex-1 flex-col gap-1">
              <strong className="text-base font-semibold text-foreground">
                Metrics &amp; execution
              </strong>
              <small className="text-sm text-foreground-muted">
                Name the run, choose measures, then review the execution summary.
              </small>
            </span>
            <ChevronDown aria-hidden="true" className={CHEVRON} />
          </summary>
          <div className="flex flex-col gap-4 px-4 pb-4 md:px-6 md:pb-6">
            <Label className="mb-0">
              Experiment name
              <Input
                className="mt-2"
                required
                maxLength={120}
                value={name}
                onChange={(event) => onNameChange(event.target.value)}
              />
            </Label>
            <fieldset className="flex min-w-0 flex-col gap-3">
              <legend className="mb-3 text-sm font-semibold text-foreground">
                Evaluation metrics
              </legend>
              <div className="grid gap-2 md:grid-cols-2">
                {metrics.map((metric) => (
                  <Label
                    className="mb-0 flex min-h-row cursor-pointer items-start gap-3 rounded-control border border-border bg-background p-3 has-data-[state=checked]:border-accent"
                    key={metric}
                    htmlFor={`metric-${metric}`}
                  >
                    <Checkbox
                      id={`metric-${metric}`}
                      className="mt-1"
                      checked={selectedMetrics.includes(metric)}
                      onCheckedChange={(checked) =>
                        onMetricsChange(
                          checked === true
                            ? [...selectedMetrics, metric]
                            : selectedMetrics.filter((value) => value !== metric),
                        )
                      }
                    />
                    <span className="flex min-w-0 flex-col gap-1">
                      <strong className="text-sm font-medium text-foreground">
                        {metricLabel[metric]}
                      </strong>
                      <small className="text-xs font-normal text-foreground-muted">
                        {options?.metrics[metric]}
                      </small>
                    </span>
                  </Label>
                ))}
              </div>
            </fieldset>
            <p className="text-sm text-foreground-muted">
              Evaluator:{' '}
              <strong className="font-medium text-foreground">
                {options?.model || 'Not configured'}
              </strong>
              . Scores use paid model calls, can vary between runs, and require human review.
            </p>
          </div>
        </details>
      </div>
      <aside
        className="flex flex-col gap-4 rounded-card border border-border bg-surface p-4 desktop:sticky desktop:top-16 desktop:col-start-2 desktop:row-span-2 desktop:row-start-1"
        aria-label="Experiment run summary"
      >
        <div className="flex flex-col gap-1 border-b border-border pb-4">
          <h2 className="text-base font-semibold text-foreground">Run summary</h2>
          <a
            className="self-start text-sm text-accent hover:underline"
            href={docsHref('experiments/runs')}
            target="_blank"
            rel="noopener noreferrer"
          >
            Experiment run guide
          </a>
          <p
            className={storageError ? 'text-xs text-warning' : 'text-xs text-foreground-muted'}
            role="status"
          >
            {storageError || 'Draft saved in this browser tab.'}
          </p>
        </div>
        {options?.error && <InlineError>{options.error}</InlineError>}
        {!pipelines.length && (
          <p className="text-sm text-foreground-muted">
            Save a pipeline in{' '}
            <a className="text-accent hover:underline" href={`#/projects/${projectId}/pipelines`}>
              Pipelines
            </a>{' '}
            before running an experiment.
          </p>
        )}
        <dl className="flex flex-col gap-3 text-sm">
          {(
            [
              [
                'Dataset',
                selectedDataset
                  ? `${selectedDataset.name} · v${selectedDataset.version}`
                  : 'Not selected',
              ],
              ['Candidates', selectedCandidateCount || 'None selected'],
              ['Metrics', selectedMetrics.length],
              ['Evaluator', options?.model || 'Unavailable'],
            ] as const
          ).map(([term, value]) => (
            <div key={term} className="flex flex-col gap-1">
              <dt className="text-xs text-foreground-muted">{term}</dt>
              <dd className="text-foreground tabular-nums wrap-anywhere">{value}</dd>
            </div>
          ))}
        </dl>
        <div className="flex flex-col gap-2">
          <Button
            type="submit"
            loading={busy}
            disabled={
              busy ||
              !!options?.error ||
              !datasetId ||
              !candidateA ||
              !selectedMetrics.length ||
              !name.trim()
            }
          >
            Run experiment
          </Button>
          <Button variant="ghost" disabled={busy} onClick={onReset}>
            Reset draft
          </Button>
        </div>
      </aside>
    </form>
  );
}
