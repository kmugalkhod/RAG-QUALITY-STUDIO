import { formatRetrievalSummary, getNodeRetrievalSettings } from '../../../lib/retrieval';
import type { PipelineNodeConfig, PipelineNodeKind } from '../model';

// The one line summary on an answer node card, one format per node kind (spec 0002, AC-9).
export function summarizeNodeConfig(kind: PipelineNodeKind, config: PipelineNodeConfig): string {
  switch (kind) {
    case 'question':
      return 'User input · single turn';
    case 'retriever':
      return `${formatRetrievalSummary(getNodeRetrievalSettings(config))} · ${
        config.index_id ? 'Documents selected' : 'Choose documents'
      }`;
    case 'prompt':
      return 'Answer with evidence';
    case 'llm':
      return config.model || 'Choose a model';
    case 'answer':
      return 'Response + citations';
  }
}
