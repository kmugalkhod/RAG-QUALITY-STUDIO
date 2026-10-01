import { LINK } from '../../../components/parts';
import { PageHeader } from '../../../components/PageHeader';
import { StatusBadge } from '../../../components/StatusBadge';
import type { ProjectSettingsData } from '../data';
import { ConnectionVault } from '../../connections/ConnectionVault';
import { docsHref } from '../../../lib/docs';
import { ProjectMembers } from './ProjectMembers';
import { SETTINGS_INTRO, SETTINGS_SECTION } from './settingsLayout';

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
    <section className={SETTINGS_SECTION}>
      <div className={SETTINGS_INTRO}>
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        <p className="text-sm text-foreground-muted">{description}</p>
      </div>
      <dl className="grid gap-x-6 gap-y-2 text-sm text-foreground desktop:col-span-2 md:grid-cols-3 md:gap-y-4 [&>dd]:wrap-anywhere md:[&>dd]:col-span-2 [&>dt]:text-foreground-muted max-md:[&>dt:not(:first-child)]:mt-2">
        {children}
      </dl>
    </section>
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
    <div className="flex flex-col">
      <PageHeader
        className="pb-6"
        title="Settings"
        meta="Project identity and server configuration."
      />
      <nav aria-label="Settings help" className="flex flex-wrap gap-x-6 pb-6">
        <a
          className={LINK}
          href={docsHref('start/configure')}
          target="_blank"
          rel="noopener noreferrer"
        >
          Provider setup and costs
        </a>
        <a
          className={LINK}
          href={docsHref('operate/security')}
          target="_blank"
          rel="noopener noreferrer"
        >
          Security and permissions
        </a>
        <a
          className={LINK}
          href={docsHref('reference/limits-faq')}
          target="_blank"
          rel="noopener noreferrer"
        >
          Limits and FAQ
        </a>
      </nav>
      <SettingsSection title="Project" description="Identity shared across this workspace.">
        <dt>Name</dt>
        <dd>{data.project.name}</dd>
        <dt>Description</dt>
        <dd>{data.project.description || 'No description added.'}</dd>
        <dt>Project ID</dt>
        <dd className="font-mono text-xs">{projectId}</dd>
      </SettingsSection>
      <SettingsSection title="Documents" description="Supported uploads and processing.">
        <dt>File types</dt>
        <dd>PDF, TXT, Markdown, HTML, DOCX, PPTX, CSV, TSV, and XLSX</dd>
        <dt>Upload limit</dt>
        <dd className="tabular-nums">
          {(data.upload.max_upload_bytes / 1048576).toFixed(0)} MB per file
        </dd>
        <dt>Processing</dt>
        <dd>
          Document preparation uses versioned character chunks. Ingestion pipelines also offer
          section-token and parent-child chunks. Scanned PDFs need OCR support and an enabled
          extraction policy.
        </dd>
      </SettingsSection>
      <SettingsSection title="Models" description="Configured on the server.">
        <dt>Embeddings</dt>
        <dd className="flex flex-col items-start gap-1">
          <StatusBadge status={data.embedding.configured ? 'configured' : 'unavailable'} />
          {!data.embedding.configured && (
            <p className="text-foreground-muted">{data.embedding.error || 'Not configured'}</p>
          )}
        </dd>
        <dt>Embedding model</dt>
        <dd>
          {data.embedding.config?.model || 'Unavailable'}
          {data.embedding.config && (
            <span className="text-foreground-muted tabular-nums">
              {' '}
              · {data.embedding.config.dimensions} dimensions
            </span>
          )}
        </dd>
        <dt>Answer models</dt>
        <dd>{data.generation.error || data.generation.models.join(', ') || 'Unavailable'}</dd>
        <dt>Context budget</dt>
        <dd className="tabular-nums">{data.generation.context_tokens.toLocaleString()} tokens</dd>
      </SettingsSection>
      {import.meta.env.VITE_CLERK_PUBLISHABLE_KEY && <ProjectMembers projectId={projectId} />}
      <section
        id="settings-connections"
        className="flex scroll-mt-16 flex-col gap-6 border-t border-border py-8"
        aria-labelledby="settings-connections-heading"
      >
        <div className={SETTINGS_INTRO}>
          <h2 id="settings-connections-heading" className="text-base font-semibold text-foreground">
            Source connections
          </h2>
          <p className="text-sm text-foreground-muted">
            Credentials are encrypted on the server. Reads expose only intentionally redacted
            metadata. Available connections depend on server configuration and provider access.
          </p>
        </div>
        <ConnectionVault projectId={projectId} settings={data.connections} />
      </section>
      <footer className="flex flex-col gap-2 border-t border-border pt-6">
        <p className="text-xs text-foreground-muted">
          Source credentials never enter pipeline versions or browser storage. Shared deployments
          require configured OIDC authentication and encrypted artifact storage.
        </p>
        <a
          className={LINK}
          href={docsHref('operate/troubleshooting')}
          target="_blank"
          rel="noopener noreferrer"
        >
          Troubleshoot unavailable settings
        </a>
      </footer>
    </div>
  );
}
