import { useEffect, useState } from 'react';
import { Workflow, Plus } from 'lucide-react';
import { Button } from '../../components/ui/button';
import * as api from './api';
export function PipelinesPage({ projectId }: { projectId: string }) {
  const [pipelines, setPipelines] = useState<api.Pipeline[]>();
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => { let disposed = false; void api.allPages(o => api.list(projectId, o)).then(p => { if (!disposed) { setPipelines(p); setError(''); } }).catch(e => { if (!disposed) setError((e as Error).message); }); return () => { disposed = true; }; }, [projectId, revision]);
  return <><div className="page-heading"><div><h1>Pipelines</h1><p>Saved configurations for answering questions with evidence.</p></div><Button asChild><a href={`#/projects/${projectId}/pipelines/new`}><Plus size={14}/>New pipeline</a></Button></div>{error ? <p role="alert">{error}<Button variant="outline" onClick={() => setRevision(v => v + 1)}>Retry</Button></p> : !pipelines ? <p role="status">Loading pipelines…</p> : !pipelines.length ? <div className="empty-state"><h2>Build your first answer pipeline</h2><p>Create a pipeline, choose the documents to search, and save a version to test in Playground.</p></div> : <ul className="project-list pipeline-list">{pipelines.map(p => <li key={p.id}><Workflow className="list-symbol" size={20}/><div className="project-content"><h2>{p.name}</h2><p>Versioned question → retrieval → answer pipeline</p></div><Button variant="outline" asChild><a href={`#/projects/${projectId}/pipelines/${p.id}`}>Open<span className="sr-only"> {p.name}</span></a></Button></li>)}</ul>}</>;
}
