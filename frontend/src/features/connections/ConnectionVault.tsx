import { KeyRound, Plus, RefreshCw, RotateCcw, ShieldCheck } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import {
  CARD,
  InlineError,
  LINK,
  LIST,
  LIST_ROW,
  SELECT_ROW,
  SectionHeading,
} from '../../components/parts';
import { LoadingState } from '../../components/states/LoadingState';
import { StatusBadge } from '../../components/StatusBadge';
import { Alert, AlertDescription, AlertTitle } from '../../components/ui/alert';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../components/ui/native-select';
import { allPages } from '../../lib/pagination';
import { docsHref } from '../../lib/docs';
import { cn } from '../../lib/utils';
import * as api from './api';
import type { ConnectionKind, ConnectionSettings, Credentials, SourceConnection } from './model';

const labels: Record<ConnectionKind, string> = {
  s3: 'Amazon S3',
  notion: 'Notion',
  confluence: 'Confluence',
};

type SecretDraft = {
  accessKey: string;
  secretKey: string;
  sessionToken: string;
  notionToken: string;
  siteUrl: string;
  email: string;
  apiToken: string;
};

const emptySecrets = (): SecretDraft => ({
  accessKey: '',
  secretKey: '',
  sessionToken: '',
  notionToken: '',
  siteUrl: '',
  email: '',
  apiToken: '',
});

function credentials(kind: ConnectionKind, draft: SecretDraft): Credentials {
  if (kind === 's3') {
    return {
      kind,
      access_key_id: draft.accessKey,
      secret_access_key: draft.secretKey,
      ...(draft.sessionToken ? { session_token: draft.sessionToken } : {}),
    };
  }
  if (kind === 'notion') {
    return { kind, integration_token: draft.notionToken };
  }
  return { kind, site_url: draft.siteUrl, email: draft.email, api_token: draft.apiToken };
}

function CredentialFields({
  kind,
  draft,
  setDraft,
}: {
  kind: ConnectionKind;
  draft: SecretDraft;
  setDraft: React.Dispatch<React.SetStateAction<SecretDraft>>;
}) {
  const field = (key: keyof SecretDraft) => ({
    value: draft[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setDraft((current) => ({ ...current, [key]: event.target.value })),
  });
  if (kind === 's3') {
    return (
      <>
        <Label>
          Access key ID
          <Input {...field('accessKey')} type="password" autoComplete="new-password" required />
        </Label>
        <Label>
          Secret access key
          <Input {...field('secretKey')} type="password" autoComplete="new-password" required />
        </Label>
        <Label>
          Session token <span className="font-normal">(optional)</span>
          <Input {...field('sessionToken')} type="password" autoComplete="new-password" />
        </Label>
      </>
    );
  }
  if (kind === 'notion') {
    return (
      <Label>
        Integration token
        <Input {...field('notionToken')} type="password" autoComplete="new-password" required />
      </Label>
    );
  }
  return (
    <>
      <Label>
        Site URL
        <Input
          {...field('siteUrl')}
          type="url"
          placeholder="https://workspace.atlassian.net"
          autoComplete="off"
          required
        />
      </Label>
      <Label>
        Account email
        <Input {...field('email')} type="email" autoComplete="off" required />
      </Label>
      <Label>
        API token
        <Input {...field('apiToken')} type="password" autoComplete="new-password" required />
      </Label>
    </>
  );
}

function ConnectionForm({
  mode,
  kind,
  busy,
  onCancel,
  onSubmit,
}: {
  mode: 'create' | 'rotate';
  kind?: ConnectionKind;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (name: string, kind: ConnectionKind, credentials: Credentials) => Promise<void>;
}) {
  const [name, setName] = useState('');
  const [selectedKind, setSelectedKind] = useState<ConnectionKind>(kind || 's3');
  const [draft, setDraft] = useState(emptySecrets);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await onSubmit(name, selectedKind, credentials(selectedKind, draft));
      setName('');
    } finally {
      // Submitted credentials must not remain in React state or rendered controls.
      setDraft(emptySecrets());
    }
  }

  return (
    <form
      className="flex flex-col gap-4 [&>label]:mb-0 [&>label>input]:mt-2 [&>label>[data-slot=native-select-wrapper]]:mt-2"
      onSubmit={(event) => void submit(event)}
    >
      {mode === 'create' ? (
        <>
          <Label>
            Connection name
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={120}
              required
            />
          </Label>
          <Label>
            Provider
            <NativeSelect
              aria-label="Connection provider"
              value={selectedKind}
              onChange={(event) => {
                setSelectedKind(event.target.value as ConnectionKind);
                setDraft(emptySecrets());
              }}
            >
              {Object.entries(labels).map(([value, label]) => (
                <NativeSelectOption key={value} value={value}>
                  {label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Label>
        </>
      ) : (
        <p className="text-sm text-foreground-muted">
          Replace every credential field for this {labels[selectedKind]} connection.
        </p>
      )}
      <CredentialFields kind={selectedKind} draft={draft} setDraft={setDraft} />
      <div className="flex flex-col gap-2 md:flex-row-reverse md:justify-end">
        <Button type="submit" loading={busy} disabled={busy}>
          {mode === 'create' ? <Plus aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}
          {mode === 'create' ? 'Save encrypted connection' : 'Rotate credentials'}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function ConnectionVault({
  projectId,
  settings,
}: {
  projectId: string;
  settings: ConnectionSettings;
}) {
  const [items, setItems] = useState<SourceConnection[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [form, setForm] = useState<'create' | 'rotate' | ''>('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(settings.enabled);
  const [error, setError] = useState('');
  const selected = items.find((item) => item.id === selectedId);

  async function load() {
    if (!settings.enabled) {
      return;
    }
    setLoading(true);
    try {
      const values = await allPages((offset) => api.listConnections(projectId, offset));
      setItems(values);
      setSelectedId((current) =>
        values.some((item) => item.id === current) ? current : values[0]?.id || '',
      );
      setError('');
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // The project/settings identity owns this catalog refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, settings.enabled]);

  async function action(work: () => Promise<SourceConnection>) {
    setBusy(true);
    setError('');
    try {
      const updated = await work();
      setItems((current) => {
        const rest = current.filter((item) => item.id !== updated.id);
        return [updated, ...rest];
      });
      setSelectedId(updated.id);
      setForm('');
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!settings.enabled) {
    return (
      <Alert>
        <KeyRound />
        <AlertTitle>Encrypted connections are disabled</AlertTitle>
        <AlertDescription>
          Configure a versioned 32-byte server key and explicitly enable the local connection vault.
          Credentialed connectors remain unavailable until then.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="grid gap-6 desktop:grid-cols-3">
      <div className="flex min-w-0 flex-col gap-4">
        <SectionHeading
          title="Saved connections"
          description={
            <>
              {items.length} encrypted connection{items.length === 1 ? '' : 's'}
            </>
          }
          action={
            <Button variant="outline" size="sm" onClick={() => setForm('create')} disabled={busy}>
              <Plus aria-hidden="true" /> Add connection
            </Button>
          }
        />
        <div className="flex flex-wrap gap-x-4">
          <a
            className={LINK}
            href={docsHref('ingestion/connections')}
            target="_blank"
            rel="noopener noreferrer"
          >
            Source connection guide
          </a>
          <a
            className={LINK}
            href={docsHref('operate/security')}
            target="_blank"
            rel="noopener noreferrer"
          >
            Credential security boundary
          </a>
        </div>
        {loading && <LoadingState label="Loading encrypted connections…" rows={2} />}
        {!loading && !items.length && (
          <p className={cn(CARD, 'p-4 text-sm text-foreground-muted')}>
            No credentials are stored for this project.
          </p>
        )}
        {items.length > 0 && (
          <ul className={LIST} aria-label="Source connections">
            {items.map((item) => (
              <li key={item.id} className={LIST_ROW}>
                <Button
                  variant="ghost"
                  className={cn(SELECT_ROW, 'rounded-none')}
                  aria-pressed={item.id === selectedId}
                  onClick={() => {
                    setSelectedId(item.id);
                    setForm('');
                  }}
                >
                  <span className="flex items-center justify-between gap-2">
                    <strong className="min-w-0 text-sm font-medium wrap-anywhere">
                      {item.name}
                    </strong>
                    <StatusBadge status={item.status}>{item.status}</StatusBadge>
                  </span>
                  <small className="text-xs font-normal text-foreground-muted wrap-anywhere">
                    {labels[item.kind]} · {item.redacted_summary.join(' · ')}
                  </small>
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {(form || items.length > 0 || error) && (
        <div className={cn(CARD, 'flex min-w-0 flex-col gap-4 p-4 md:p-6 desktop:col-span-2')}>
          {error && <InlineError>{error}</InlineError>}
          {form === 'create' ? (
            <>
              <SectionHeading
                title="Add an encrypted connection"
                description="Credentials are submitted once and replaced by redacted metadata."
              />
              <ConnectionForm
                mode="create"
                busy={busy}
                onCancel={() => setForm('')}
                onSubmit={async (name, _kind, value) =>
                  action(() => api.createConnection(projectId, name, value))
                }
              />
            </>
          ) : selected ? (
            <>
              <SectionHeading
                title={
                  <>
                    <ShieldCheck aria-hidden="true" />
                    {selected.name}
                  </>
                }
                description={
                  <>
                    {labels[selected.kind]} · {selected.redacted_summary.join(' · ')}
                  </>
                }
              />
              {selected.last_error && (
                <p className="text-sm text-foreground-muted wrap-anywhere">{selected.last_error}</p>
              )}
              {selected.last_tested_at && (
                <p className="text-xs text-foreground-muted">
                  Last checked {new Date(selected.last_tested_at).toLocaleString()}
                </p>
              )}
              {form === 'rotate' ? null : (
                <div className="flex flex-col gap-2 md:flex-row-reverse md:justify-end">
                  <Button
                    loading={busy}
                    onClick={() => void action(() => api.testConnection(projectId, selected.id))}
                    disabled={busy}
                  >
                    <RefreshCw aria-hidden="true" /> Test connection
                  </Button>
                  <Button variant="outline" onClick={() => setForm('rotate')} disabled={busy}>
                    <RotateCcw aria-hidden="true" /> Rotate credentials
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => void action(() => api.rewrapConnection(projectId, selected.id))}
                    disabled={busy}
                  >
                    <KeyRound aria-hidden="true" /> Re-encrypt with active key
                  </Button>
                </div>
              )}
              {form === 'rotate' && (
                <ConnectionForm
                  mode="rotate"
                  kind={selected.kind}
                  busy={busy}
                  onCancel={() => setForm('')}
                  onSubmit={async (_name, _kind, value) =>
                    action(() => api.rotateConnection(projectId, selected.id, value))
                  }
                />
              )}
            </>
          ) : (
            <p className="text-sm text-foreground-muted">
              Select a connection to inspect its safe metadata.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
