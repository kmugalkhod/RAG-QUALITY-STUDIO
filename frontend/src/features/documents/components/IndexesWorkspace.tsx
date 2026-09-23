import { useEffect, useState } from 'react';
import { Tabs, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import { IndexPanel } from './IndexPanel';
import { SnapshotPanel } from './SnapshotPanel';

export function IndexesWorkspace({ projectId }: { projectId: string }) {
  const read = () =>
    new URLSearchParams(window.location.hash.split('?')[1]).get('mode') === 'snapshots'
      ? 'snapshots'
      : 'indexes';
  const [mode, setMode] = useState<'snapshots' | 'indexes'>(read);
  useEffect(() => {
    const update = () => setMode(read());
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  function change(value: string) {
    const next = value as typeof mode;
    const [path] = window.location.hash.split('?');
    window.location.hash = `${path}?view=indexes&mode=${next}`;
    setMode(next);
  }
  return (
    <div>
      <Tabs value={mode} onValueChange={change}>
        <TabsList className="index-mode-tabs" aria-label="Collection workspace views">
          <TabsTrigger value="indexes">Collections</TabsTrigger>
          <TabsTrigger value="snapshots">Source history</TabsTrigger>
        </TabsList>
      </Tabs>
      {mode === 'snapshots' ? (
        <SnapshotPanel projectId={projectId} />
      ) : (
        <IndexPanel projectId={projectId} />
      )}
    </div>
  );
}
