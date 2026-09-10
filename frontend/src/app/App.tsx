import { Playground } from '../features/playground/Playground';
import { useEffect, useState } from 'react';
import { KnowledgeBase } from '../features/documents/KnowledgeBase';
import { Layers3, Folder, ArrowUpRight } from 'lucide-react';
import { ProjectsPage } from '../features/projects/ProjectsPage';

export function App() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => { const update = () => setHash(window.location.hash); window.addEventListener('hashchange', update); return () => window.removeEventListener('hashchange', update); }, []);
  const playgroundId = /^#\/projects\/([a-f0-9-]{36})\/playground$/.exec(hash)?.[1];
  const projectId = /^#\/projects\/([a-f0-9-]{36})$/.exec(hash)?.[1];
  return <div className="app-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="RAG Quality Studio home"><Layers3 size={27} /><span>RAG Quality<span className="brand-secondary">Studio</span></span></a>
      <nav aria-label="Main navigation"><a className="nav-active" href="/" aria-current="page"><Folder size={18} />Projects</a></nav>
      <div className="sidebar-note"><span className="local-dot"/> Local workspace<p>Upload and process documents, build versioned indexes and inspect retrieved evidence. Ask independent questions with citations and inspect saved answers. Evaluation is not yet available.</p></div>
    </aside>
    <div className="workspace"><header className="topbar"><span>Workspace / <strong>{playgroundId ? 'RAG playground' : projectId ? 'Knowledge Base' : 'Projects'}</strong></span><a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">API reference <ArrowUpRight size={14}/></a></header><main id="main"><>{playgroundId ? <Playground key={playgroundId} projectId={playgroundId}/> : projectId ? <KnowledgeBase key={projectId} projectId={projectId}/> : <ProjectsPage />}</></main><footer>RAG Quality Studio <span>Grounded answers · Milestone 3</span></footer></div>
  </div>;
}
