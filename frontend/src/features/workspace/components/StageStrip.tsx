import { useCallback, useEffect, useState } from 'react';
import {
  loadAskStage,
  loadCompareStage,
  loadPrepareStage,
  primaryStage,
  type StageId,
  type StageResult,
  type StageSummary,
} from '../stages';
import { StageCard } from './StageCard';

const STAGES: {
  id: StageId;
  title: string;
  description: string;
  actionLabel: string;
  page: string;
}[] = [
  {
    id: 'prepare',
    title: 'Prepare knowledge',
    description: 'Upload documents and build a searchable index.',
    actionLabel: 'Upload documents',
    page: 'knowledge-base',
  },
  {
    id: 'ask',
    title: 'Ask a question',
    description: 'Run an answer pipeline and inspect the cited evidence.',
    actionLabel: 'Ask a question',
    page: 'playground',
  },
  {
    id: 'compare',
    title: 'Compare results',
    description: 'Score configurations on the same dataset for quality, latency and cost.',
    actionLabel: 'Run experiment',
    page: 'experiments',
  },
];

// Load one stage, and reload it on retry or when the project changes.
function useStage(load: (projectId: string) => Promise<StageSummary>, projectId: string) {
  const [result, setResult] = useState<StageResult>({ status: 'loading' });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let disposed = false;
    setResult({ status: 'loading' });
    load(projectId)
      .then((summary) => {
        if (!disposed) {
          setResult({ status: 'loaded', summary });
        }
      })
      .catch((error: unknown) => {
        if (!disposed) {
          setResult({
            status: 'failed',
            message: error instanceof Error ? error.message : 'The request failed.',
          });
        }
      });
    return () => {
      disposed = true;
    };
  }, [load, projectId, revision]);
  const retry = useCallback(() => setRevision((value) => value + 1), []);
  return [result, retry] as const;
}

// Spec 0002, AC-6. Each stage loads on its own so one failure shows Retry on that card only.
export function StageStrip({ projectId }: { projectId: string }) {
  const [prepare, retryPrepare] = useStage(loadPrepareStage, projectId);
  const [ask, retryAsk] = useStage(loadAskStage, projectId);
  const [compare, retryCompare] = useStage(loadCompareStage, projectId);
  const results: Record<StageId, StageResult> = { prepare, ask, compare };
  const retries: Record<StageId, () => void> = {
    prepare: retryPrepare,
    ask: retryAsk,
    compare: retryCompare,
  };
  const primary = primaryStage(results);

  return (
    <section aria-labelledby="stages-title" className="flex flex-col gap-4">
      <h2 id="stages-title" className="text-base font-semibold text-foreground">
        Workflow
      </h2>
      <ol className="grid gap-4 md:grid-cols-3">
        {STAGES.map((stage, index) => (
          <StageCard
            key={stage.id}
            step={index + 1}
            title={stage.title}
            description={stage.description}
            result={results[stage.id]}
            actionLabel={stage.actionLabel}
            href={`#/projects/${projectId}/${stage.page}`}
            primary={primary === stage.id}
            onRetry={retries[stage.id]}
          />
        ))}
      </ol>
    </section>
  );
}
