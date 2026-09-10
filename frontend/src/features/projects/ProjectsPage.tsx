import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowRight, FolderPlus, Plus, RotateCw, X } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { createProject, listProjects, type ProjectPage } from '../../lib/api';

export function ProjectsPage() {
  const [page, setPage] = useState<ProjectPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const nameInput = useRef<HTMLInputElement>(null);
  const newButton = useRef<HTMLButtonElement>(null);
  const requestId = useRef(0);

  const load = useCallback(async (nextOffset: number) => {
    const id = ++requestId.current;
    setLoading(true); setError('');
    try { const result = await listProjects(nextOffset); if (id === requestId.current) setPage(result); }
    catch (err) { if (id === requestId.current) setError((err as Error).message); }
    finally { if (id === requestId.current) setLoading(false); }
  }, []);
  const invalidateRequest = useCallback(() => { requestId.current++; }, []);
  useEffect(() => { void load(offset); return invalidateRequest; }, [offset, load, invalidateRequest]);
  useEffect(() => { if (showForm) nameInput.current?.focus(); }, [showForm]);
  function closeForm() { setShowForm(false); setFormError(''); newButton.current?.focus(); }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    if (!name.trim() || name.trim().length > 120 || description.trim().length > 2000) {
      setFormError('Enter a project name of 1–120 characters and a description of up to 2,000 characters.'); nameInput.current?.focus(); return;
    }
    setSaving(true); setFormError(''); setNotice('');
    try {
      const project = await createProject({ name: name.trim(), description: description.trim() });
      setName(''); setDescription(''); closeForm(); setNotice(`Project “${project.name}” created.`);
      if (offset === 0) await load(0); else setOffset(0);
    } catch (err) { setFormError(`${(err as Error).message} If the connection was interrupted, refresh the project list before retrying to avoid a duplicate.`); }
    finally { setSaving(false); }
  }
  return <>
    <div className="page-heading"><div><h1>Projects</h1><p>Manage your sources, pipelines and answers.</p></div><Button ref={newButton} onClick={() => { setShowForm(true); setNotice(''); }} disabled={showForm}><Plus size={17}/>New project</Button></div>
    <div role="status" className="success-message">{notice}</div>
    {showForm && <section className="create-panel" aria-labelledby="create-title"><div className="section-heading"><h2 id="create-title">Create a project</h2><button className="icon-button" aria-label="Close project form" disabled={saving} onClick={closeForm}><X size={20}/></button></div>
      <form onSubmit={submit} noValidate aria-busy={saving}>
        <div className="form-grid"><div><label htmlFor="project-name">Project name <span>Required</span></label><input ref={nameInput} id="project-name" value={name} onChange={e => setName(e.target.value)} maxLength={120} required disabled={saving} aria-invalid={!!formError} aria-describedby={formError ? 'form-error' : 'name-hint'} placeholder="e.g. Customer support knowledge"/><p className="field-hint" id="name-hint">Choose a name you’ll recognize. Up to 120 characters.</p></div>
        <div><label htmlFor="project-description">Description <span>Optional</span></label><textarea id="project-description" value={description} onChange={e => setDescription(e.target.value)} maxLength={2000} rows={3} disabled={saving} placeholder="What would you like to explore?"/></div></div>
        {formError && <p id="form-error" role="alert" className="error-message">{formError}</p>}
        <div className="form-actions"><Button type="button" variant="outline" disabled={saving} onClick={closeForm}>Cancel</Button><Button type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create project'}<ArrowRight size={16}/></Button></div>
      </form></section>}
    <section className="project-section" aria-labelledby="all-projects"><div className="section-heading"><h2 id="all-projects">All projects {page && !loading && !error && <span className="count">{page.total}</span>}</h2><Button variant="outline" size="sm" disabled={loading} onClick={() => void load(offset)}><RotateCw size={14}/>Refresh</Button></div>
      {loading ? <div className="loading-state" role="status">Loading projects…<div className="skeleton"/><div className="skeleton"/></div> : error ? <div className="error-state"><h3>Projects couldn’t be loaded</h3><p role="alert">{error}</p><Button variant="outline" onClick={() => void load(offset)}>Try again</Button></div> : page?.items.length === 0 ? <div className="empty-state"><FolderPlus size={36} strokeWidth={1.4}/><h3>{offset ? 'No projects on this page' : 'Your first project starts here'}</h3><p>{offset ? 'Return to the previous page to see your projects.' : 'Give your work a home. Create a project to start organizing your RAG research.'}</p>{!offset && !showForm && <Button variant="outline" onClick={() => setShowForm(true)}><Plus size={16}/>Create your first project</Button>}</div> : <ul className="project-list">{page?.items.map(project => <li key={project.id}><div className="project-initial" aria-hidden="true">{project.name.slice(0, 1).toUpperCase()}</div><div className="project-content"><h3><a className="project-link" href={`#/projects/${project.id}/overview`}>{project.name}<ArrowRight size={16}/></a></h3><p>{project.description || 'No description added.'}</p></div><div className="project-date"><span>Created</span><time dateTime={project.created_at}>{new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(project.created_at))}</time></div></li>)}</ul>}
      {!loading && !error && page && (page.total > page.limit || offset > 0) && <div className="pagination"><Button variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous</Button><span>Page {Math.floor(offset / 20) + 1}</span><Button variant="outline" disabled={offset + page.limit >= page.total} onClick={() => setOffset(offset + 20)}>Next</Button></div>}
    </section>
  </>;
}
