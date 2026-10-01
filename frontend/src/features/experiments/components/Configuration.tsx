import { getNodeRetrievalSettings, formatRetrievalSummary } from '../../../lib/retrieval';
import type { PipelineVersion } from '../../pipelines/model';

import { type Candidate } from '../model';

// The exact saved configuration a candidate runs with.
export function Configuration({ version }: { version: PipelineVersion | Candidate }) {
  const retriever = version.execution.nodes.find((n) => n.type === 'retriever');
  const llm = version.execution.nodes.find((n) => n.type === 'llm');
  return (
    <div className="flex flex-col gap-1 rounded-control border border-border bg-background px-3 py-2 text-xs text-foreground-muted wrap-anywhere">
      <p className="text-sm font-medium text-foreground">
        {version.name} · v{version.version}
      </p>
      <p>
        {llm?.model} · {formatRetrievalSummary(getNodeRetrievalSettings(retriever))} · temperature{' '}
        {llm?.temperature} · max output {llm?.max_tokens}
      </p>
      <p>
        Index {'index_version' in version ? `${version.index_version} · ` : ''}
        <span className="font-mono">{retriever?.index_id}</span>
      </p>
      {'source_snapshot_id' in version && (
        <p>
          {version.source_snapshot_id
            ? `Source snapshot ${version.source_snapshot_number} · collected ${new Date(version.source_snapshot_collected_at!).toLocaleDateString()}`
            : 'Source snapshot lineage unavailable'}
        </p>
      )}
    </div>
  );
}
