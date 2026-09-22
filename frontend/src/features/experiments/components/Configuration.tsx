import { getNodeRetrievalSettings, formatRetrievalSummary } from '../../../lib/retrieval';
import type { PipelineVersion } from '../../pipelines/model';

import { type Candidate } from '../model';
export function Configuration({ version }: { version: PipelineVersion | Candidate }) {
  const retriever = version.execution.nodes.find((n) => n.type === 'retriever');
  const llm = version.execution.nodes.find((n) => n.type === 'llm');
  return (
    <p className="candidate-settings">
      <strong>
        {version.name} · v{version.version}
      </strong>
      <br />
      {llm?.model} · {formatRetrievalSummary(getNodeRetrievalSettings(retriever))} · temperature{' '}
      {llm?.temperature} · max output {llm?.max_tokens}
      <br />
      Index {'index_version' in version ? `${version.index_version} · ` : ''}
      <span>{retriever?.index_id}</span>
      {'source_snapshot_id' in version && (
        <>
          <br />
          {version.source_snapshot_id
            ? `Source snapshot ${version.source_snapshot_number} · collected ${new Date(version.source_snapshot_collected_at!).toLocaleDateString()}`
            : 'Source snapshot lineage unavailable'}
        </>
      )}
    </p>
  );
}
