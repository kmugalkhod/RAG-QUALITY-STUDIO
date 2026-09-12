export type RetrievalMode = 'vector' | 'keyword' | 'hybrid';

export type RetrievalSettings =
  | {
      mode: 'vector';
      top_k: number;
      max_vector_distance?: number | null;
    }
  | {
      mode: 'keyword';
      top_k: number;
    }
  | {
      mode: 'hybrid';
      top_k: number;
      max_vector_distance?: number | null;
      vector_candidates: number;
      keyword_candidates: number;
      vector_weight: number;
    };

export const retrievalLimits = {
  topK: { min: 1, max: 50 },
  candidateCount: { max: 200 },
  vectorDistance: { min: 0, max: 2 },
  vectorWeight: { min: 0, max: 1 },
} as const;

const modeLabels: Record<RetrievalMode, string> = {
  vector: 'Vector',
  keyword: 'Keyword',
  hybrid: 'Hybrid',
};

export function createDefaultRetrievalSettings(topK = 5): RetrievalSettings {
  return { mode: 'vector', top_k: topK, max_vector_distance: null };
}

/** Legacy pipeline versions store top_k directly on the retriever node. */
export function getNodeRetrievalSettings(node?: {
  retrieval?: RetrievalSettings;
  top_k?: number;
}): RetrievalSettings {
  return node?.retrieval ?? createDefaultRetrievalSettings(node?.top_k);
}

export function changeRetrievalMode(
  settings: RetrievalSettings,
  mode: RetrievalMode,
): RetrievalSettings {
  if (mode === settings.mode) {
    return settings;
  }

  const topK = settings.top_k;
  const cutoff = settings.mode === 'keyword' ? null : (settings.max_vector_distance ?? null);

  switch (mode) {
    case 'keyword':
      return { mode, top_k: topK };
    case 'vector':
      return { mode, top_k: topK, max_vector_distance: cutoff };
    case 'hybrid':
      return {
        mode,
        top_k: topK,
        max_vector_distance: cutoff,
        vector_candidates: 50,
        keyword_candidates: 50,
        vector_weight: 0.5,
      };
  }
}

function isWithinRange(value: number, min: number, max: number): boolean {
  return Number.isFinite(value) && value >= min && value <= max;
}

export function validateRetrievalSettings(settings: RetrievalSettings): string[] {
  const errors: string[] = [];
  const { topK, candidateCount, vectorDistance, vectorWeight } = retrievalLimits;

  if (!Object.hasOwn(modeLabels, settings.mode)) {
    errors.push('Choose a supported search method.');
  }

  if (!Number.isInteger(settings.top_k) || !isWithinRange(settings.top_k, topK.min, topK.max)) {
    errors.push('Top k must be a whole number from 1 to 50.');
  }

  if (settings.mode !== 'keyword') {
    const cutoff = settings.max_vector_distance;
    if (cutoff != null && !isWithinRange(cutoff, vectorDistance.min, vectorDistance.max)) {
      errors.push('Maximum vector distance must be from 0 to 2, or off.');
    }
  }

  if (settings.mode === 'hybrid') {
    const candidateCounts = [settings.vector_candidates, settings.keyword_candidates];
    const hasInvalidCandidateCount = candidateCounts.some(
      (count) =>
        !Number.isInteger(count) || !isWithinRange(count, settings.top_k, candidateCount.max),
    );
    if (hasInvalidCandidateCount) {
      errors.push('Each candidate count must be a whole number between Top k and 200.');
    }
    if (!isWithinRange(settings.vector_weight, vectorWeight.min, vectorWeight.max)) {
      errors.push('Vector weight must be from 0 to 1.');
    }
  }

  return errors;
}

export function formatRetrievalSummary(settings: RetrievalSettings): string {
  return `${modeLabels[settings.mode]} · Top ${settings.top_k}`;
}

export function formatRetrievalScores(scores: {
  cosine_distance: number | null;
  lexical_score?: number | null;
  fusion_score?: number | null;
}): string {
  const labels: string[] = [];
  if (scores.cosine_distance != null) {
    labels.push(`Cosine distance ${scores.cosine_distance.toFixed(4)}`);
  }
  if (scores.lexical_score != null) {
    labels.push(`Keyword score ${scores.lexical_score.toFixed(4)}`);
  }
  if (scores.fusion_score != null) {
    labels.push(`RRF score ${scores.fusion_score.toFixed(6)}`);
  }
  return labels.join(' · ');
}
