import { KeyRound, RefreshCw, Save, Trash2 } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { PageHeader } from '../../components/PageHeader';
import { CARD, Callout, Facts, InlineError, Notice, SectionHeading } from '../../components/parts';
import { ErrorState } from '../../components/states/ErrorState';
import { LoadingState } from '../../components/states/LoadingState';
import { StatusBadge } from '../../components/StatusBadge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { cn } from '../../lib/utils';
import * as api from './api';
import { ChatModelSettings } from './ChatModelSettings';

function when(value: string | null) {
  return value ? new Date(value).toLocaleString() : 'Never';
}

function KeyForm({
  replacing,
  busy,
  onSubmit,
}: {
  replacing: boolean;
  busy: boolean;
  onSubmit: (value: string) => Promise<void>;
}) {
  const [value, setValue] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await onSubmit(value.trim());
    } finally {
      // The submitted key must not remain in React state or the rendered control.
      setValue('');
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={(event) => void submit(event)}>
      <Label className="mb-0 flex flex-col items-stretch gap-2">
        {replacing ? 'Replacement OpenRouter API key' : 'OpenRouter API key'}
        <Input
          type="password"
          autoComplete="new-password"
          spellCheck={false}
          placeholder="sk-or-v1-…"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          minLength={20}
          maxLength={512}
          required
        />
      </Label>
      <p className="text-xs text-foreground-muted">
        The key is checked with OpenRouter, then encrypted on the server. It is never shown again;
        only its last four characters are displayed.
      </p>
      <div>
        <Button type="submit" loading={busy} disabled={busy || value.trim().length < 20}>
          <Save aria-hidden="true" />
          {replacing ? 'Replace key' : 'Save key'}
        </Button>
      </div>
    </form>
  );
}

export function ProviderKeySettings() {
  const [key, setKey] = useState<api.ProviderKey | null>(null);
  const [loadError, setLoadError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  async function load() {
    setLoadError('');
    try {
      setKey(await api.getProviderKey());
    } catch (cause) {
      setLoadError((cause as Error).message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function action(work: () => Promise<api.ProviderKey>, done: string) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      setKey(await work());
      setNotice(done);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const header = (
    <PageHeader
      title="Organization settings"
      meta="Model provider key and chat models used by every project in this organization"
    />
  );
  if (loadError) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <ErrorState message={loadError} onRetry={() => void load()} />
      </div>
    );
  }
  if (!key) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <LoadingState label="Loading provider key…" rows={2} />
      </div>
    );
  }
  const owner = key.scope === 'organization' ? 'this organization' : 'this workspace';
  return (
    <div className="flex flex-col gap-6">
      {header}
      <section className={cn(CARD, 'flex flex-col gap-4 p-4 md:p-6')} aria-label="OpenRouter key">
        <SectionHeading
          level="h2"
          title={
            <>
              <KeyRound aria-hidden="true" />
              OpenRouter API key
            </>
          }
          description={`Embeddings, answers and evaluations for ${owner} are billed to this key.`}
          action={
            key.configured ? (
              <StatusBadge status={key.status === 'active' ? 'configured' : 'failed'}>
                {key.status === 'active' ? 'Active' : 'Rejected'}
              </StatusBadge>
            ) : (
              <StatusBadge status="unavailable">Not configured</StatusBadge>
            )
          }
        />
        {key.configured ? (
          <Facts
            className="md:grid-cols-3"
            items={[
              ['Key', <span className="font-mono">{key.redacted_hint}</span>],
              ['Last verified', when(key.last_verified_at)],
              ['Updated by', key.updated_by ?? '—'],
            ]}
          />
        ) : key.environment_fallback ? (
          <Callout tone="info" role="note">
            No key is stored here, so this local workspace uses the server’s OPENROUTER_API_KEY.
          </Callout>
        ) : (
          <Callout tone="warning" role="note" title="Model calls are blocked">
            Indexing, questions and experiments fail until{' '}
            {key.can_manage ? 'you add' : 'an organization admin adds'} an OpenRouter key.
          </Callout>
        )}
        {key.status === 'rejected' && (
          <Callout tone="warning" role="alert" title="OpenRouter rejected this key">
            Model calls are blocked. Replace the key, or test it again if it was re-enabled.
          </Callout>
        )}
        {error && <InlineError>{error}</InlineError>}
        <Notice>{notice}</Notice>
        {!key.can_manage ? (
          <p className="text-sm text-foreground-muted">
            Only organization admins can add, replace or remove this key.
          </p>
        ) : !key.storage_available ? (
          <Callout tone="warning" role="note" title="Encrypted key storage is unavailable">
            The server needs artifact encryption (a local keyring, KMS or Vault) before keys can be
            stored.
          </Callout>
        ) : (
          <>
            <KeyForm
              replacing={key.configured}
              busy={busy}
              onSubmit={(value) =>
                action(
                  () => api.saveProviderKey(value),
                  'The OpenRouter key was verified and saved.',
                )
              }
            />
            {key.configured && (
              <div className="flex flex-col gap-2 border-t border-border pt-4 md:flex-row">
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    void action(() => api.testProviderKey(), 'OpenRouter checked the stored key.')
                  }
                >
                  <RefreshCw aria-hidden="true" /> Test key
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        `Remove the OpenRouter key? Model calls for ${owner} stop until a new key is added.`,
                      )
                    ) {
                      void action(() => api.deleteProviderKey(), 'The OpenRouter key was removed.');
                    }
                  }}
                >
                  <Trash2 aria-hidden="true" /> Remove key
                </Button>
              </div>
            )}
          </>
        )}
      </section>
      <ChatModelSettings />
    </div>
  );
}
