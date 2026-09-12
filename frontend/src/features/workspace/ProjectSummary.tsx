import { useEffect, useState } from 'react';
import { Button } from '../../components/ui/button';
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
}: {
  projectId: string;
  configuration?: boolean;
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

  if (error) {
    return (
      <div role="alert">
        {error}
        <Button variant="outline" onClick={() => setRevision((value) => value + 1)}>
          Retry
        </Button>
      </div>
    );
  }
  if (configuration && settings) {
    return <ProjectSettings projectId={projectId} data={settings} />;
  }
  if (!configuration && summary) {
    return <ProjectOverview projectId={projectId} data={summary} />;
  }
  return <p role="status">Loading project {configuration ? 'settings' : 'overview'}…</p>;
}
