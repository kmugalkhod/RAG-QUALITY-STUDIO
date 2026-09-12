import { allPages } from '../../lib/pagination';
import { getUploadSettings, listDocuments } from '../documents/api';
import { getEmbeddingSettings, listIndexes } from '../documents/indexApi';
import { getPipelineOptions, listPipelines } from '../pipelines/api';
import { getProject } from '../projects/api';

export async function loadProjectSummary(projectId: string) {
  const [project, documents, indexes, pipelines] = await Promise.all([
    getProject(projectId),
    allPages((offset) => listDocuments(projectId, offset)),
    allPages((offset) => listIndexes(projectId, offset)),
    allPages((offset) => listPipelines(projectId, 'answer', offset)),
  ]);
  return { project, documents, indexes, pipelines };
}

export async function loadProjectSettings(projectId: string) {
  const [project, upload, embedding, generation] = await Promise.all([
    getProject(projectId),
    getUploadSettings(projectId),
    getEmbeddingSettings(projectId),
    getPipelineOptions(projectId),
  ]);
  return { project, upload, embedding, generation };
}

export type ProjectSummaryData = Awaited<ReturnType<typeof loadProjectSummary>>;
export type ProjectSettingsData = Awaited<ReturnType<typeof loadProjectSettings>>;
