import { useEffect, useState } from 'react';
import { ErrorState } from '../../components/states/ErrorState';
import { LoadingState } from '../../components/states/LoadingState';
import {
  loadProjectSettings,
  loadProjectSummary,
  type ProjectSettingsData,
  type ProjectSummaryData,
} from './data';
import { ProjectOverview } from './components/ProjectOverview';
import { ProjectSettings } from './components/ProjectSettings';

export function ProjectSummary({
  projectId,
  configuration = false,
  section,
}: {
  projectId: string;
  configuration?: boolean;
  /** A settings section to scroll to once loaded, such as `connections`. */
  section?: string;
}) {
  const [summary, setSummary] = useState<ProjectSummaryData>();
  const [settings, setSettings] = useState<ProjectSettingsData>();
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let disposed = false;
    setError('');
    const request = configuration ? loadProjectSettings(projectId) : loadProjectSummary(projectId);
    void request
      .then((result) => {
        if (disposed) {
          return;
        }
        if (configuration) {
          setSettings(result as ProjectSettingsData);
        } else {
          setSummary(result as ProjectSummaryData);
        }
      })
      .catch((cause) => {
        if (!disposed) {
          setError((cause as Error).message);
        }
      });
    return () => {
      disposed = true;
    };
  }, [projectId, configuration, revision]);

  const loaded = configuration ? !!settings : !!summary;
  useEffect(() => {
    if (loaded && section) {
      document.getElementById(`settings-${section}`)?.scrollIntoView({ block: 'start' });
    }
  }, [loaded, section]);

  if (error) {
    return (
      <ErrorState
        title={`Could not load project ${configuration ? 'settings' : 'overview'}`}
        message={error}
        onRetry={() => setRevision((value) => value + 1)}
      />
    );
  }
  if (configuration && settings) {
    return <ProjectSettings projectId={projectId} data={settings} />;
  }
  if (!configuration && summary) {
    return <ProjectOverview projectId={projectId} data={summary} />;
  }
  return <LoadingState label={`Loading project ${configuration ? 'settings' : 'overview'}…`} />;
}
