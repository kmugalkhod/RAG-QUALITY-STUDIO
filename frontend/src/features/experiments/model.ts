import type { PipelineExecution } from '../pipelines/model';
import type { QueryRun } from '../playground/model';
export type Metric = 'faithfulness' | 'response_relevancy' | 'context_recall';
export const metricLabel: Record<Metric, string> = {
  faithfulness: 'Faithfulness',
  response_relevancy: 'Response relevancy',
  context_recall: 'Context recall',
};
export type Row = { question: string; reference_answer: string | null };
export type Dataset = {
  id: string;
  dataset_id: string;
  name: string;
  version: number;
  rows: Row[];
  content_hash: string;
};
export type Preview = {
  rows: Row[];
  errors: { row: number; message: string }[];
  content_hash: string;
};
export type Candidate = {
  id: string;
  pipeline_id: string;
  name: string;
  version: number;
  execution: PipelineExecution;
  index_id: string;
  index_version: number;
  generation_config: { model: string };
  embedding_config: { model: string };
};
export type Score = {
  status: string;
  value: number | null;
  reason: string | null;
  evaluation_cost_usd: number | null;
  calls?: { structured_output?: unknown; usage?: Record<string, number>; model: string }[];
};
export type Item = {
  candidate: number;
  ordinal: number;
  query_run_id: string | null;
  status: string;
  stage: string;
  output: Partial<QueryRun>;
  metrics: Partial<Record<Metric, Score>>;
  error: string | null;
};
export type Experiment = {
  id: string;
  name: string;
  status: string;
  progress: number;
  total: number;
  cancel_requested: boolean;
  error: string | null;
  created_at: string;
  snapshot: {
    dataset: Dataset;
    candidates: Candidate[];
    evaluator: { model: string; metrics: Metric[]; ragas_version: string };
    application: { source_sha256: string };
  };
};
type Cost = { known_sum: number | null; known_count: number; total: number };
export type Detail = Experiment & {
  items: Item[];
  summary: {
    candidates: {
      candidate: number;
      total: number;
      generation_failures: number;
      skipped: number;
      metrics: Record<
        Metric,
        {
          mean: number | null;
          scored: number;
          failed: number;
          skipped: number;
          unavailable: number;
          missing_reference: number;
          pending: number;
        }
      >;
      query_latency_ms: { mean: number | null; count: number };
      generation_cost_usd: Cost;
      evaluation_cost_usd: Cost;
      query_tokens: Cost;
    }[];
    paired: Partial<
      Record<
        Metric,
        { count: number; a_mean: number | null; b_mean: number | null; b_minus_a: number | null }
      >
    >;
  };
};
