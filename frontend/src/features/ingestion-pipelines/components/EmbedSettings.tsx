import { Callout } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import type { EmbeddingConfig } from '../../documents/model';
import type { IngestionNode, IngestionRun, SourcePreview } from '../model';
import { HINT, STACK } from './settingsStyles';

type EmbedNode = Extract<IngestionNode, { type: 'embed' }>;

/**
 * OpenRouter list prices in USD per million input tokens, checked 2026-10. They are
 * used only for the labelled estimate; runs record the provider-reported cost.
 */
export const embeddingListPrices: Record<string, number> = {
  'openai/text-embedding-3-small': 0.02,
  'openai/text-embedding-3-large': 0.13,
};

/** English text averages about four UTF-8 bytes per embedding token. */
const BYTES_PER_TOKEN = 4;

export function sameEmbedding(node: EmbedNode, server: EmbeddingConfig) {
  return (
    node.provider === server.provider &&
    node.model === server.model &&
    node.dimensions === server.dimensions &&
    node.config_version === server.revision
  );
}

function money(value: number) {
  if (value > 0 && value < 0.0001) {
    return 'under $0.0001';
  }
  return `$${value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: value < 0.01 ? 4 : 2,
  })}`;
}

/** "about N chunks, about X, estimated $Y (list price, estimate)" for a preview. */
export function previewEstimateText(preview: SourcePreview, model: string): string | undefined {
  const estimate = (
    preview.cost_basis as { embedding_estimate?: { chunks: number; embedding_bytes: number } }
  )?.embedding_estimate;
  if (!estimate || preview.status !== 'succeeded') {
    return undefined;
  }
  const kilobytes = Math.max(1, Math.round(estimate.embedding_bytes / 1000));
  const price = embeddingListPrices[model];
  const cost =
    price === undefined
      ? 'cost unknown (no list price for this model)'
      : `estimated ${money(((estimate.embedding_bytes / BYTES_PER_TOKEN) * price) / 1_000_000)} (list price, estimate)`;
  return `About ${estimate.chunks.toLocaleString('en-US')} chunks, about ${kilobytes.toLocaleString('en-US')} KB, ${cost}. Vectors an earlier run already made are reused and cost nothing.`;
}

/** "N new, M reused, cost $Z or unknown" for a finished run. */
export function runUsageText(run: IngestionRun): string | undefined {
  const usage = run.embedding_usage;
  if (!usage || !['succeeded', 'failed', 'cancelled'].includes(run.status)) {
    return undefined;
  }
  const cost = usage.cost_usd === null ? 'cost unknown' : `cost ${money(usage.cost_usd)}`;
  if (usage.reused_vectors === null || usage.reused_vectors === undefined) {
    return `${run.embedded_count.toLocaleString('en-US')} passages embedded, ${cost}.`;
  }
  const reused = Math.min(usage.reused_vectors, run.embedded_count);
  return `${(run.embedded_count - reused).toLocaleString('en-US')} new, ${reused.toLocaleString('en-US')} reused, ${cost}.`;
}

/**
 * The Embed panel (spec 0012 Part B): what the server embeds with, what a preview would
 * cost, what the last run cost, and a one-click fix for a version saved under another
 * model (A12). There are no settings to change.
 */
export function EmbedSettings({
  node,
  serverEmbedding,
  preview,
  lastRun,
  update,
}: {
  node: EmbedNode;
  serverEmbedding?: EmbeddingConfig;
  preview?: SourcePreview;
  lastRun?: IngestionRun;
  update: (node: EmbedNode) => void;
}) {
  const mismatch = serverEmbedding && !sameEmbedding(node, serverEmbedding);
  const estimate = preview ? previewEstimateText(preview, node.model) : undefined;
  const usage = lastRun ? runUsageText(lastRun) : undefined;
  return (
    <div className={STACK}>
      <p className="text-sm text-foreground">
        Uses {node.model} ({node.dimensions.toLocaleString('en-US')} dimensions), set by the server.
      </p>
      {mismatch && serverEmbedding && (
        <Callout tone="warning" role="note" title="Saved with a different embedding model">
          <p>
            This version embeds with {node.model} ({node.dimensions} dimensions), but the server now
            uses {serverEmbedding.model} ({serverEmbedding.dimensions} dimensions), so it cannot
            run. Using the server&apos;s settings creates a new version when you save; its next run
            embeds every passage again.
          </p>
          <div>
            <Button
              type="button"
              variant="outline"
              onClick={() =>
                update({
                  ...node,
                  provider: serverEmbedding.provider,
                  model: serverEmbedding.model,
                  dimensions: serverEmbedding.dimensions,
                  config_version: serverEmbedding.revision,
                })
              }
            >
              Use the server&apos;s embedding settings
            </Button>
          </div>
        </Callout>
      )}
      <p className={HINT}>
        {estimate ??
          'Preview the pipeline to see how many passages a run would embed and an estimated cost.'}
      </p>
      {usage && <p className={HINT}>Last run: {usage}</p>}
    </div>
  );
}
