import { useEffect, useState } from 'react';
import { Layers3, Folder, BookOpen, Workflow, MessageSquare, Settings, LayoutDashboard, Menu, X } from 'lucide-react';
import { PipelineEditor } from '../features/pipelines/PipelineEditor';
import { PipelinesPage } from '../features/pipelines/PipelinesPage';
import { Playground } from '../features/playground/Playground';
import { KnowledgeBase } from '../features/documents/KnowledgeBase';
import { ProjectsPage } from '../features/projects/ProjectsPage';
import { ProjectSummary } from '../features/workspace/ProjectSummary';
import { listProjects, type Project } from '../lib/api';
import { getProject } from '../features/documents/api';
import { allPages } from '../features/pipelines/api';
import { useRoute } from './navigation';

const pages = [['overview', 'Overview', LayoutDashboard], ['knowledge-base', 'Knowledge Base', BookOpen], ['pipelines', 'Pipelines', Workflow], ['playground', 'Playground', MessageSquare], ['settings', 'Settings', Settings]] as const;
export function App() {
  const route = useRoute();
  const { projectId, page, detail } = route;
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project>();
  const [error, setError] = useState('');
  const [mobile, setMobile] = useState(false);
  const [revision, setRevision] = useState(0);
  const current = project?.id === projectId ? project : undefined;
  const title = pages.find(p => p[0] === page)?.[1] || (page === 'projects' ? 'Projects' : 'Page not found');
  useEffect(() => {
    let disposed = false;
    void allPages(listProjects).then(p => { if (!disposed) setProjects(p); }).catch(() => { /* Project listing has its own retry UI. */ });
    setError('');
    if (projectId) void getProject(projectId).then(p => { if (!disposed) setProject(p); }).catch(e => { if (!disposed) setError((e as Error).message); });
    return () => { disposed = true; };
  }, [projectId, revision, page]);
  useEffect(() => { setMobile(false); document.title = `${title}${current ? ` · ${current.name}` : ''} · RAG Quality Studio`; document.getElementById('main')?.focus(); }, [projectId, page, detail, title, current]);
  const base = `#/projects/${projectId}`;
  return <div className="app-shell linear-workspace">
    <a className="skip-link" href="#main" onClick={e => { e.preventDefault(); document.getElementById('main')?.focus(); }}>Skip to content</a>
    <aside className={`sidebar ${mobile ? 'sidebar-open' : ''}`}>
      <a className="brand" href="#/" aria-label="RAG Quality Studio home"><Layers3 size={27}/><span>RAG Quality<span className="brand-secondary">Studio</span></span></a>
      <button className="mobile-toggle icon-button" aria-label={mobile ? 'Close navigation' : 'Open navigation'} aria-expanded={mobile} aria-controls="workspace-navigation" onClick={() => setMobile(v => !v)}>{mobile ? <X/> : <Menu/>}</button>
      <div id="workspace-navigation" className="sidebar-content" onKeyDown={e => { if (e.key === 'Escape') { setMobile(false); document.querySelector<HTMLButtonElement>('.mobile-toggle')?.focus(); } }}>
        <label className="project-switcher">Project<select aria-label="Switch project" value={projectId || ''} onChange={e => { window.location.hash = e.target.value ? `/projects/${e.target.value}/${pages.some(p => p[0] === page) ? page : 'overview'}` : '/'; }}><option value="">All projects</option>{current && !projects.some(p => p.id === current.id) && <option value={current.id}>{current.name}</option>}{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <nav aria-label="Project navigation">{projectId ? pages.map(([path, label, Icon]) => <a key={path} href={path === 'playground' ? sessionStorage.getItem(`playground:${projectId}`) || `${base}/${path}` : `${base}/${path}`} className={page === path ? 'nav-active' : ''} aria-current={page === path ? 'page' : undefined}><Icon size={18}/>{label}</a>) : <a href="#/" className="nav-active" aria-current="page"><Folder size={18}/>Projects</a>}</nav>
        {projectId && <a className="all-projects-link" href="#/">Manage projects</a>}
        <div className="sidebar-note"><span className="local-dot"/>Local workspace<p>Sources → pipelines → grounded answers.</p></div>
      </div>
    </aside>
    <div className="workspace"><header className="topbar"><span>{projectId ? current?.name || 'Loading project…' : 'Workspace'} <span aria-hidden="true">/</span> <strong>{title}{page === 'pipelines' && detail ? ' / Editor' : ''}</strong></span></header><main id="main" tabIndex={-1} className={page === 'knowledge-base' ? 'knowledge-main' : page === 'pipelines' && detail ? 'editor-main' : ''}>
      {projectId && !current ? error ? <div role="alert"><h1>Project unavailable</h1><p>{error}</p><button onClick={() => setRevision(v => v + 1)}>Retry</button></div> : <p role="status">Loading project…</p> : <div key={`${projectId}/${page}/${detail || ''}`} className={`page-content ${page}-page`}>{page === 'projects' ? <ProjectsPage/> : page === 'overview' ? <ProjectSummary projectId={projectId!}/> : page === 'settings' ? <ProjectSummary projectId={projectId!} configuration/> : page === 'knowledge-base' ? <KnowledgeBase projectId={projectId!} documentId={route.query.get('document') || ''}/> : page === 'pipelines' ? detail ? <PipelineEditor projectId={projectId!} pipelineId={detail}/> : <PipelinesPage projectId={projectId!}/> : page === 'playground' ? <Playground projectId={projectId!} pipelineId={route.query.get('pipeline') || ''} versionId={route.query.get('version') || ''}/> : <><h1>Page not found</h1><a href="#/">Return to projects</a></>}</div>}
    </main></div>
  </div>;
}
