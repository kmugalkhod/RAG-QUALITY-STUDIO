import { StatusBadge } from '../../../components/StatusBadge';
import { Separator } from '../../../components/ui/separator';
import type { ProjectSettingsData } from '../data';
import { ConnectionVault } from '../../connections/ConnectionVault';
import { docsHref } from '../../../lib/docs';

function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <Separator />
      <section className="settings-section grid grid-cols-[230px_minmax(0,1fr)] gap-10 py-7">
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <dl className="settings-list grid grid-cols-[150px_1fr] gap-5">{children}</dl>
      </section>
    </>
  );
}

export function ProjectSettings({
  projectId,
  data,
}: {
  projectId: string;
  data: ProjectSettingsData;
}) {
  return (
    <>
      <div className="page-heading mb-8 flex items-start justify-between gap-6">
        <div>
          <h1>Settings</h1>
          <p>Project identity and server configuration.</p>
          <nav aria-label="Settings help" className="flex flex-wrap gap-4">
            <a href={docsHref('start/configure')} target="_blank" rel="noopener noreferrer">
              Provider setup and costs
            </a>
            <a href={docsHref('operate/security')} target="_blank" rel="noopener noreferrer">
              Security and permissions
            </a>
            <a href={docsHref('reference/limits-faq')} target="_blank" rel="noopener noreferrer">
              Limits and FAQ
            </a>
          </nav>
        </div>
        <span className="quiet-label">Project configuration</span>
      </div>
      <SettingsSection title="Project" description="Identity shared across this workspace.">
        <dt>Name</dt>
        <dd>{data.project.name}</dd>
        <dt>Description</dt>
        <dd>{data.project.description || 'No description added.'}</dd>
        <dt>Project ID</dt>
        <dd className="technical-value">{projectId}</dd>
      </SettingsSection>
      <SettingsSection title="Documents" description="Supported uploads and processing.">
        <dt>File types</dt>
        <dd>PDF, TXT, Markdown, HTML, DOCX, PPTX, CSV, TSV, and XLSX</dd>
        <dt>Upload limit</dt>
        <dd>{(data.upload.max_upload_bytes / 1048576).toFixed(0)} MB per file</dd>
        <dt>Processing</dt>
        <dd>
          Document preparation uses versioned character chunks. Ingestion pipelines also offer
          section-token and parent-child chunks. Scanned PDFs need OCR support and an enabled
          extraction policy.
        </dd>
      </SettingsSection>
      <SettingsSection title="Models" description="Configured on the server.">
        <dt>Embeddings</dt>
        <dd>
          <StatusBadge status={data.embedding.configured ? 'configured' : 'unavailable'} />
          {!data.embedding.configured && <p>{data.embedding.error || 'Not configured'}</p>}
        </dd>
        <dt>Embedding model</dt>
        <dd>
          {data.embedding.config?.model || 'Unavailable'}
          {data.embedding.config && (
            <span className="quiet-label"> · {data.embedding.config.dimensions} dimensions</span>
          )}
        </dd>
        <dt>Answer models</dt>
        <dd>{data.generation.error || data.generation.models.join(', ') || 'Unavailable'}</dd>
        <dt>Context budget</dt>
        <dd>{data.generation.context_tokens.toLocaleString()} tokens</dd>
      </SettingsSection>
      <Separator />
      <section className="connection-settings py-7">
        <div className="settings-section-intro mb-6 max-w-2xl">
          <h2>Source connections</h2>
          <p>
            Credentials are encrypted on the server. Reads expose only intentionally redacted
            metadata.
          </p>
          <p>Available connections depend on server configuration and provider access.</p>
        </div>
        <ConnectionVault projectId={projectId} settings={data.connections} />
      </section>
      <p className="field-hint settings-note">
        Source credentials never enter pipeline versions or browser storage. Shared deployments
        require configured OIDC authentication and encrypted artifact storage.
      </p>
      <a href={docsHref('operate/troubleshooting')} target="_blank" rel="noopener noreferrer">
        Troubleshoot unavailable settings
      </a>
    </>
  );
}
