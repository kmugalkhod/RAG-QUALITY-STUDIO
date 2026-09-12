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
    </p>
  );
}
