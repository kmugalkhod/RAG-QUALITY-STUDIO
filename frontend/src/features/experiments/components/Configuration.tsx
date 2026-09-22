import { getNodeRetrievalSettings, formatRetrievalSummary } from '../../../lib/retrieval';
import type { PipelineVersion } from '../../pipelines/model';
import type { IndexVersion } from '../../documents/model';

import { type Candidate } from '../model';
export function Configuration({
  version,
  index,
}: {
  version: PipelineVersion | Candidate;
  index?: IndexVersion;
}) {
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
      Index{' '}
      {'index_version' in version
        ? `${version.index_name || 'Index'} · version ${version.index_version}`
        : index
          ? `${index.knowledge_set_name} · version ${index.version}`
          : retriever?.index_id}
      <br />
      {'source_snapshot' in version ? (
        version.source_snapshot ? (
          <span>Source snapshot {version.source_snapshot.snapshot_number}</span>
        ) : (
          <span>Source snapshot lineage unavailable</span>
        )
      ) : index?.source_snapshot ? (
        <span>Source snapshot {index.source_snapshot.snapshot_number}</span>
      ) : (
        <span>Source snapshot lineage unavailable</span>
      )}
    </p>
  );
}
