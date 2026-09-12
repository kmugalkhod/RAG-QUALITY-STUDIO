import { useEffect, useState } from 'react';
import { allPages } from '../../lib/pagination';
import { listIndexes } from '../documents/indexApi';
import type { IndexVersion } from '../documents/model';
import * as pipelinesApi from '../pipelines/api';
import type { Pipeline, PipelineOptions, PipelineVersion } from '../pipelines/model';

const errorText = (cause: unknown) => (cause instanceof Error ? cause.message : 'Request failed.');

export function usePlaygroundCatalog(
  projectId: string,
  linkedPipeline: string,
  linkedVersion: string,
) {
  const [indexes, setIndexes] = useState<IndexVersion[]>([]);
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [versions, setVersions] = useState<PipelineVersion[]>([]);
  const [options, setOptions] = useState<PipelineOptions>();
  const [selectedPipeline, setSelectedPipeline] = useState(linkedPipeline);
  const [selectedVersion, setSelectedVersion] = useState(linkedVersion);
  const [loading, setLoading] = useState(true);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    void Promise.all([
      allPages((offset) => listIndexes(projectId, offset)),
      allPages((offset) => pipelinesApi.listPipelines(projectId, offset)),
      pipelinesApi.getPipelineOptions(projectId),
    ])
      .then(([allIndexes, allPipelines, serverOptions]) => {
        if (disposed) {
          return;
        }
        setIndexes(allIndexes.filter((index) => index.status === 'succeeded'));
        setPipelines(allPipelines);
        setOptions(serverOptions);
        setLoadError('');
      })
      .catch((cause) => {
        if (!disposed) {
          setLoadError(errorText(cause));
        }
      })
      .finally(() => {
        if (!disposed) {
          setLoading(false);
        }
      });
    return () => {
      disposed = true;
    };
  }, [projectId]);

  useEffect(() => {
    let disposed = false;
    setVersions([]);
    if (!selectedPipeline) {
      setVersionsLoading(false);
      return;
    }
    setVersionsLoading(true);
    void allPages((offset) =>
      pipelinesApi.listPipelineVersions(projectId, selectedPipeline, offset),
    )
      .then((values) => {
        if (disposed) {
          return;
        }
        setVersions(values);
        const requested =
          selectedPipeline === linkedPipeline && linkedVersion
            ? linkedVersion
            : values[0]?.id || '';
        if (requested && !values.some((value) => value.id === requested)) {
          setLoadError('The linked pipeline version is unavailable. Choose another version.');
          setSelectedVersion('');
        } else {
          setSelectedVersion(requested);
        }
      })
      .catch((cause) => {
        if (!disposed) {
          setLoadError(errorText(cause));
        }
      })
      .finally(() => {
        if (!disposed) {
          setVersionsLoading(false);
        }
      });
    return () => {
      disposed = true;
    };
  }, [projectId, selectedPipeline, linkedPipeline, linkedVersion]);

  return {
    indexes,
    pipelines,
    versions,
    options,
    selectedPipeline,
    selectedVersion,
    loading,
    versionsLoading,
    loadError,
    setPipelines,
    setVersions,
    setSelectedPipeline,
    setSelectedVersion,
  };
}
