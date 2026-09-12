import { KeyRound, Plus, RefreshCw, RotateCcw, ShieldCheck } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { StatusBadge } from '../../components/StatusBadge';
import { Alert, AlertDescription, AlertTitle } from '../../components/ui/alert';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../components/ui/native-select';
import { allPages } from '../../lib/pagination';
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
          Session token <span className="quiet-label">Optional</span>
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
    <form className="connection-form grid gap-4" onSubmit={(event) => void submit(event)}>
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
        <p>Replace every credential field for this {labels[selectedKind]} connection.</p>
      )}
      <CredentialFields kind={selectedKind} draft={draft} setDraft={setDraft} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy}>
          {mode === 'create' ? <Plus /> : <RotateCcw />}
          {busy
            ? 'Submitting…'
            : mode === 'create'
              ? 'Save encrypted connection'
              : 'Rotate credentials'}
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
    <div className="connection-vault grid grid-cols-[minmax(240px,0.8fr)_minmax(300px,1.2fr)] gap-8">
      <div>
        <div className="section-heading flex items-center justify-between gap-3">
          <div>
            <h3>Saved connections</h3>
            <p>
              {items.length} encrypted connection{items.length === 1 ? '' : 's'}
            </p>
          </div>
          <Button variant="outline" onClick={() => setForm('create')} disabled={busy}>
            <Plus /> Add connection
          </Button>
        </div>
        {loading && <p role="status">Loading encrypted connections…</p>}
        {!loading && !items.length && (
          <p className="inline-empty">No credentials are stored for this project.</p>
        )}
        <ul
          className="connection-list compact-list m-0 list-none p-0"
          aria-label="Source connections"
        >
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={
                  item.id === selectedId ? 'connection-choice selected' : 'connection-choice'
                }
                aria-pressed={item.id === selectedId}
                onClick={() => {
                  setSelectedId(item.id);
                  setForm('');
                }}
              >
                <span>
                  <strong>{item.name}</strong>
                  <small>
                    {labels[item.kind]} · {item.redacted_summary.join(' · ')}
                  </small>
                </span>
                <StatusBadge status={item.status}>{item.status}</StatusBadge>
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="connection-detail">
        {error && (
          <p role="alert" className="error-message">
            {error}
          </p>
        )}
        {form === 'create' ? (
          <>
            <h3>Add an encrypted connection</h3>
            <p>Credentials are submitted once and replaced by redacted metadata.</p>
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
            <div className="connection-identity flex items-start justify-between gap-4">
              <div>
                <h3>{selected.name}</h3>
                <p>
                  {labels[selected.kind]} · {selected.redacted_summary.join(' · ')}
                </p>
              </div>
              <ShieldCheck aria-hidden="true" />
            </div>
            {selected.last_error && <p className="field-hint">{selected.last_error}</p>}
            {selected.last_tested_at && (
              <p className="field-hint">
                Last checked {new Date(selected.last_tested_at).toLocaleString()}
              </p>
            )}
            {form === 'rotate' ? null : (
              <div className="flex flex-wrap gap-2 mt-5">
                <Button
                  onClick={() => void action(() => api.testConnection(projectId, selected.id))}
                  disabled={busy}
                >
                  <RefreshCw /> {busy ? 'Checking…' : 'Test connection'}
                </Button>
                <Button variant="outline" onClick={() => setForm('rotate')} disabled={busy}>
                  <RotateCcw /> Rotate credentials
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => void action(() => api.rewrapConnection(projectId, selected.id))}
                  disabled={busy}
                >
                  <KeyRound /> Re-encrypt with active key
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
          <div className="inline-empty">Select a connection to inspect its safe metadata.</div>
        )}
      </div>
    </div>
  );
}
