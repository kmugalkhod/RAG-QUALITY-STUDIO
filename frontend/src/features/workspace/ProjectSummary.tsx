import { useEffect, useState } from 'react';
import { FileText, Workflow, ArrowRight } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { getProject, getSettings, listDocuments } from '../documents/api';
import { embeddingSettings, listIndexes } from '../documents/indexApi';
import { allPages, list, options } from '../pipelines/api';

async function summary(id: string) {
  const [project, documents, indexes, pipelines] = await Promise.all([getProject(id), allPages(o => listDocuments(id, o)), allPages(o => listIndexes(id, o)), allPages(o => list(id, o))]);
  return { project, documents, indexes, pipelines };
}
async function settings(id: string) {
  const [project, upload, embedding, generation] = await Promise.all([getProject(id), getSettings(id), embeddingSettings(id), options(id)]);
  return { project, upload, embedding, generation };
}
export function ProjectSummary({ projectId, configuration = false }: { projectId: string; configuration?: boolean }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof summary>>>();
  const [config, setConfig] = useState<Awaited<ReturnType<typeof settings>>>();
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let disposed = false;
    const load = configuration ? settings(projectId).then(v => { if (!disposed) setConfig(v); }) : summary(projectId).then(v => { if (!disposed) setData(v); });
    void load.catch(e => { if (!disposed) setError((e as Error).message); });
    return () => { disposed = true; };
  }, [projectId, configuration, revision]);
  if (error) return <div role="alert">{error}<Button variant="outline" onClick={() => { setError(''); setRevision(v => v + 1); }}>Retry</Button></div>;
  if (configuration && config) return <><div className="page-heading"><div><h1>Settings</h1><p>Project identity and server configuration.</p></div><span className="quiet-label">Read only</span></div>
    <section className="settings-section"><div><h2>Project</h2><p>Identity shared across this workspace.</p></div><dl className="settings-list"><dt>Name</dt><dd>{config.project.name}</dd><dt>Description</dt><dd>{config.project.description || 'No description added.'}</dd><dt>Project ID</dt><dd className="technical-value">{projectId}</dd></dl></section>
    <section className="settings-section"><div><h2>Documents</h2><p>Supported uploads and processing.</p></div><dl className="settings-list"><dt>File types</dt><dd>Text-based PDF and UTF-8 TXT</dd><dt>Upload limit</dt><dd>{(config.upload.max_upload_bytes / 1048576).toFixed(0)} MB per file</dd><dt>Processing</dt><dd>Versioned character chunks. Scanned PDFs require OCR and are unsupported.</dd></dl></section>
    <section className="settings-section"><div><h2>Models</h2><p>Configured by your server administrator.</p></div><dl className="settings-list"><dt>Embeddings</dt><dd><span className={`run-status ${config.embedding.configured ? 'status-succeeded' : 'status-failed'}`}>{config.embedding.configured ? 'Configured' : 'Unavailable'}</span>{!config.embedding.configured && <p>{config.embedding.error || 'Not configured'}</p>}</dd><dt>Embedding model</dt><dd>{config.embedding.config?.model || 'Unavailable'} {config.embedding.config && <span className="quiet-label"> · {config.embedding.config.dimensions} dimensions</span>}</dd><dt>Answer models</dt><dd>{config.generation.error || config.generation.models.join(', ') || 'Unavailable'}</dd><dt>Context budget</dt><dd>{config.generation.context_tokens.toLocaleString()} tokens</dd></dl></section>
    <p className="field-hint settings-note">Availability reflects server configuration, not a provider connectivity check. Credentials stay on the server. The current API does not support editing project settings.</p></>;
  if (!data) return <p role="status">Loading project {configuration ? 'settings' : 'status'}…</p>;
  const ready = data.indexes.filter(i => i.status === 'succeeded');
  const processed = data.documents.filter(d => d.latest_run?.status === 'succeeded');
  const processing = data.documents.filter(d => ['queued', 'running'].includes(d.latest_run?.status || ''));
  const failed = data.documents.filter(d => d.latest_run?.status === 'failed');
  const indexing = data.indexes.filter(i => ['queued', 'running'].includes(i.status));
  const next = !data.documents.length ? ['Add your first source', 'Upload a PDF or TXT document to begin.', 'knowledge-base', 'Upload documents'] : !processed.length ? ['Prepare your documents', 'Process uploaded text into inspectable chunks.', 'knowledge-base', 'Process documents'] : !ready.length ? ['Make your sources searchable', indexing.length ? 'An index is building. Inspect its progress in the Knowledge Base.' : 'Build an index from your processed documents.', 'knowledge-base', 'View indexing'] : !data.pipelines.length ? ['Configure your first pipeline', 'A ready index is available. Connect it to a saved answer pipeline.', 'pipelines/new', 'Create pipeline'] : ['Ask your sources a question', 'Choose a saved pipeline and inspect the evidence behind its answer.', 'playground', 'Open Playground'];
  return <><div className="page-heading"><div><h1>Overview</h1><p>{data.project.description || 'Sources and saved configurations for this project.'}</p></div><Button asChild><a href={`#/projects/${projectId}/${next[2]}`}>{next[3]}<ArrowRight size={14}/></a></Button></div>
    <div className="overview-layout"><div className="overview-content"><section className="project-readiness"><h2>{next[0]}</h2><p>{next[1]}</p><div className="readiness-line"><span>{processed.length} processed documents</span><span>{ready.length} ready indexes</span><span>{data.pipelines.length} saved pipelines</span></div></section>
    <section className="overview-section"><div className="section-heading"><h2>Recent documents <span className="count">{data.documents.length}</span></h2><a className="text-link" href={`#/projects/${projectId}/knowledge-base`}>View all</a></div>{!data.documents.length ? <p className="inline-empty">Add a PDF or TXT source to start building your knowledge base.</p> : <ul className="compact-list">{data.documents.slice(0, 5).map(doc => <li key={doc.id}><FileText size={16}/><a href={`#/projects/${projectId}/knowledge-base?document=${doc.id}`}>{doc.filename}</a><span className={`run-status status-${doc.latest_run?.status || 'uploaded'}`}>{doc.latest_run?.status === 'succeeded' ? 'Processed' : doc.latest_run?.status === 'running' || doc.latest_run?.status === 'queued' ? 'Processing' : doc.latest_run?.status || 'Uploaded'}</span></li>)}</ul>}</section>
    <section className="overview-section"><div className="section-heading"><h2>Saved pipelines <span className="count">{data.pipelines.length}</span></h2><a className="text-link" href={`#/projects/${projectId}/pipelines`}>View all</a></div>{!data.pipelines.length ? <p className="inline-empty">Create a pipeline after an index is ready to search.</p> : <ul className="compact-list">{data.pipelines.slice(0, 5).map(p => <li key={p.id}><Workflow size={16}/><a href={`#/projects/${projectId}/pipelines/${p.id}`}>{p.name}</a><ArrowRight size={14}/></li>)}</ul>}</section></div>
    <aside className="project-properties"><h2>Project details</h2><dl><dt>Created</dt><dd>{new Date(data.project.created_at).toLocaleDateString()}</dd><dt>Documents</dt><dd>{data.documents.length} uploaded</dd><dt>Processing</dt><dd>{processing.length} active · {failed.length} failed</dd><dt>Indexing</dt><dd>{indexing.length} active · {data.indexes.filter(i => i.status === 'failed').length} failed</dd><dt>Project ID</dt><dd className="technical-value">{projectId}</dd></dl></aside></div></>;
}
