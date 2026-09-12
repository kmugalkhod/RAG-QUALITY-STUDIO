import { Button } from '../components/ui/button';
import { NativeSelect, NativeSelectOption } from '../components/ui/native-select';
import { Label } from '../components/ui/label';
import { Folder, Layers3, Menu, X } from 'lucide-react';
import type { Dispatch, SetStateAction } from 'react';
import type { Project } from '../features/projects/api';
import { pages } from './pages';
type WorkspaceSidebarProps = {
  projectId?: string;
  page: string;
  current?: Project;
  projects: Project[];
  mobile: boolean;
  setMobile: Dispatch<SetStateAction<boolean>>;
};
export function WorkspaceSidebar({
  projectId,
  page,
  current,
  projects,
  mobile,
  setMobile,
}: WorkspaceSidebarProps) {
  const base = `#/projects/${projectId}`;
  return (
    <aside
      className={`sidebar border-r flex flex-col shrink-0 bg-secondary sticky top-0 h-dvh w-58 border-border py-5.5 px-3.5 ${mobile ? 'sidebar-open' : ''}`}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          setMobile(false);
          document.querySelector<HTMLButtonElement>('.mobile-toggle')?.focus();
        }
      }}
    >
      <a
        className="brand flex gap-2.5 items-center text-[15px] font-semibold leading-snug py-0 px-2"
        href="#/"
        aria-label="RAG Quality Studio home"
      >
        <Layers3 size={27} />
        <span>
          RAG Quality
          <span className="brand-secondary block font-normal text-[11px] text-muted-foreground mt-0.25">
            Studio
          </span>
        </span>
      </a>
      <Button
        variant="ghost"
        size="icon"
        className="mobile-toggle hidden max-[760px]:inline-flex icon-button p-1.25 border-0 bg-transparent items-center justify-center text-muted-foreground rounded-sm min-w-7.5 min-h-7.5"
        aria-label={mobile ? 'Close navigation' : 'Open navigation'}
        aria-expanded={mobile}
        aria-controls="workspace-navigation"
        onClick={() => setMobile((v) => !v)}
      >
        {mobile ? <X /> : <Menu />}
      </Button>
      <div id="workspace-navigation" className="sidebar-content flex flex-col flex-1 min-h-0">
        <Label className="project-switcher block text-muted-foreground mt-7 mx-1.5 mb-0 text-[11px] font-medium">
          Project
          <NativeSelect
            aria-label="Switch project"
            value={projectId || ''}
            onChange={(e) => {
              const destination = e.target.value;
              window.location.hash = destination
                ? ((page === 'knowledge-base' || page === 'playground' || page === 'pipelines') &&
                    sessionStorage.getItem(`${page}:${destination}`)) ||
                  `/projects/${destination}/${pages.some((p) => p[0] === page) ? page : 'overview'}`
                : '/';
            }}
          >
            <NativeSelectOption value="">All projects</NativeSelectOption>
            {current && !projects.some((p) => p.id === current.id) && (
              <NativeSelectOption value={current.id}>{current.name}</NativeSelectOption>
            )}
            {projects.map((p) => (
              <NativeSelectOption key={p.id} value={p.id}>
                {p.name}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Label>
        <nav aria-label="Project navigation">
          {projectId ? (
            pages.map(([path, label, Icon]) => (
              <a
                key={path}
                href={
                  path === 'playground' || path === 'knowledge-base' || path === 'pipelines'
                    ? sessionStorage.getItem(`${path}:${projectId}`) || `${base}/${path}`
                    : `${base}/${path}`
                }
                className={
                  page === path
                    ? 'nav-active flex items-center gap-3 p-3 bg-sidebar-accent rounded-md text-sm font-semibold'
                    : ''
                }
                aria-current={page === path ? 'page' : undefined}
              >
                <Icon size={18} />
                {label}
              </a>
            ))
          ) : (
            <a
              href="#/"
              className="nav-active flex items-center gap-3 p-3 bg-sidebar-accent rounded-md text-sm font-semibold"
              aria-current="page"
            >
              <Folder size={18} />
              Projects
            </a>
          )}
        </nav>
        {projectId && (
          <a
            className="all-projects-link text-[11px] no-underline underline-offset-4 text-muted-foreground my-6.25 mx-2.5"
            href="#/"
          >
            Manage projects
          </a>
        )}
        <div className="sidebar-note mt-auto text-muted-foreground text-[11px] py-3 px-2.25">
          <span className="local-dot inline-block w-1.5 h-1.5 rounded-full bg-muted-foreground mr-1.75" />
          Local workspace<p>Sources → pipelines → grounded answers.</p>
        </div>
      </div>
    </aside>
  );
}
