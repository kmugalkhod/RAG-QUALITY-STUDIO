import { Bot, Plus, Search, Star, Trash2, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { CARD, Callout, InlineError, Notice, SectionHeading } from '../../components/parts';
import { ErrorState } from '../../components/states/ErrorState';
import { LoadingState } from '../../components/states/LoadingState';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { cn } from '../../lib/utils';
import * as api from './api';

const PAGE = 25;

function price(value: number | null) {
  return value === null
    ? 'unknown'
    : `$${value.toLocaleString(undefined, { maximumFractionDigits: 4 })}`;
}

function priceLine(prompt: number | null, completion: number | null) {
  return prompt === null && completion === null
    ? 'Price unknown'
    : `${price(prompt)} in / ${price(completion)} out per 1M tokens`;
}

function ApprovedList({
  data,
  busy,
  onDefault,
  onRemove,
}: {
  data: api.ChatModels;
  busy: boolean;
  onDefault: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  if (!data.models.length) {
    return (
      <Callout tone="warning" role="note" title="No chat models are available">
        Answer pipelines cannot run until {data.can_manage ? 'you approve' : 'an admin approves'} a
        model below.
      </Callout>
    );
  }
  return (
    <ul
      className="flex flex-col divide-y divide-border rounded-card border border-border"
      aria-label="Available chat models"
    >
      {data.models.map((model) => (
        <li
          key={model.id}
          className="flex flex-col gap-2 p-4 md:flex-row md:items-center md:justify-between"
        >
          <div className="flex min-w-0 flex-col gap-1">
            <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
              <span className="wrap-anywhere">{model.label}</span>
              {model.id === data.default_model && <Badge>Default</Badge>}
              {model.source === 'server' && <Badge variant="secondary">Set on the server</Badge>}
            </p>
            <p className="text-xs text-foreground-muted wrap-anywhere">
              <span className="font-mono">{model.id}</span> ·{' '}
              <span className="tabular-nums">{model.context_tokens.toLocaleString()}</span> token
              budget ·{' '}
              {model.source === 'server'
                ? 'price not recorded'
                : priceLine(model.prompt_usd_per_mtok, model.completion_usd_per_mtok)}
            </p>
          </div>
          {data.can_manage && model.source === 'organization' && (
            <div className="flex shrink-0 flex-wrap gap-2">
              {model.id !== data.default_model && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => onDefault(model.id)}
                >
                  <Star aria-hidden="true" />
                  Make default
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                aria-label={`Remove ${model.id}`}
                onClick={() => onRemove(model.id)}
              >
                <Trash2 aria-hidden="true" />
                Remove
              </Button>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function CatalogSearch({
  busy,
  version,
  onApprove,
}: {
  busy: boolean;
  // Changes after each approval so the "Approved" marks refresh.
  version: number;
  onApprove: (id: string) => void;
}) {
  const [query, setQuery] = useState('');
  const [term, setTerm] = useState('');
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<api.CatalogPage | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setTerm(query.trim());
      setOffset(0);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let stale = false;
    setLoading(true);
    setError('');
    api
      .searchCatalog(term, offset, PAGE)
      .then((value) => !stale && setPage(value))
      .catch((cause) => !stale && setError((cause as Error).message))
      .finally(() => !stale && setLoading(false));
    return () => {
      stale = true;
    };
  }, [term, offset, version, attempt]);

  return (
    <div className="flex flex-col gap-4 border-t border-border pt-4">
      <Label className="mb-0 flex flex-col items-stretch gap-2">
        Search the OpenRouter catalog
        <span className="relative flex items-center">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-3 size-4 text-foreground-muted"
          />
          <Input
            type="search"
            className="pl-8"
            placeholder="Model or provider, for example gpt mini"
            value={query}
            maxLength={100}
            onChange={(event) => setQuery(event.target.value)}
          />
        </span>
      </Label>
      <p className="text-xs text-foreground-muted">
        Text models only. Prices are OpenRouter estimates and can change; each approval records the
        catalog values at that time.
      </p>
      {error ? (
        <ErrorState message={error} onRetry={() => setAttempt((value) => value + 1)} />
      ) : !page ? (
        <LoadingState label="Loading the model catalog…" rows={3} />
      ) : (
        <>
          <p role="status" className="text-xs text-foreground-muted tabular-nums">
            {loading
              ? 'Searching…'
              : page.total
                ? `Showing ${page.offset + 1}–${page.offset + page.items.length} of ${page.total} models`
                : 'No models match this search.'}
          </p>
          {page.items.length > 0 && (
            <ul
              className="flex flex-col divide-y divide-border rounded-card border border-border"
              aria-label="Catalog results"
            >
              {page.items.map((model) => (
                <li
                  key={model.id}
                  className="flex flex-col gap-2 p-4 md:flex-row md:items-center md:justify-between"
                >
                  <div className="flex min-w-0 flex-col gap-1">
                    <p className="text-sm font-medium text-foreground wrap-anywhere">
                      {model.name}
                    </p>
                    <p className="text-xs text-foreground-muted wrap-anywhere">
                      <span className="font-mono">{model.id}</span> ·{' '}
                      <span className="tabular-nums">{model.context_length.toLocaleString()}</span>{' '}
                      context ·{' '}
                      {priceLine(model.prompt_usd_per_mtok, model.completion_usd_per_mtok)}
                    </p>
                  </div>
                  {model.approved ? (
                    <Badge variant="secondary" className="self-start md:self-center">
                      Approved
                    </Badge>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      className="self-start md:self-center"
                      disabled={busy}
                      aria-label={`Approve ${model.id}`}
                      onClick={() => onApprove(model.id)}
                    >
                      <Plus aria-hidden="true" />
                      Approve
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {page.total > PAGE && (
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={loading || offset === 0}
                onClick={() => setOffset(Math.max(offset - PAGE, 0))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={loading || offset + PAGE >= page.total}
                onClick={() => setOffset(offset + PAGE)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function ChatModelSettings() {
  const [data, setData] = useState<api.ChatModels | null>(null);
  const [loadError, setLoadError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [version, setVersion] = useState(0);

  async function load() {
    setLoadError('');
    try {
      setData(await api.getChatModels());
    } catch (cause) {
      setLoadError((cause as Error).message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function action(work: () => Promise<api.ChatModels>, done: string) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      setData(await work());
      setVersion((value) => value + 1);
      setNotice(done);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={cn(CARD, 'flex flex-col gap-4 p-4 md:p-6')} aria-label="Chat models">
      <SectionHeading
        level="h2"
        title={
          <>
            <Bot aria-hidden="true" />
            Chat models
          </>
        }
        description="Models that answer pipelines in every project may use. Each model's prompt budget is capped by the server."
        action={
          data?.can_manage && (
            <Button
              variant={adding ? 'ghost' : 'outline'}
              size="sm"
              aria-expanded={adding}
              onClick={() => setAdding((value) => !value)}
            >
              {adding ? <X aria-hidden="true" /> : <Plus aria-hidden="true" />}
              {adding ? 'Close catalog' : 'Add models'}
            </Button>
          )
        }
      />
      {loadError ? (
        <ErrorState message={loadError} onRetry={() => void load()} />
      ) : !data ? (
        <LoadingState label="Loading chat models…" rows={2} />
      ) : (
        <>
          <ApprovedList
            data={data}
            busy={busy}
            onDefault={(id) =>
              void action(() => api.setDefaultChatModel(id), `${id} is now the default model.`)
            }
            onRemove={(id) => {
              if (
                window.confirm(
                  `Remove ${id}? Saved pipeline versions that use it cannot run or be saved again until it is approved again.`,
                )
              ) {
                void action(() => api.removeChatModel(id), `${id} was removed.`);
              }
            }}
          />
          {error && <InlineError>{error}</InlineError>}
          <Notice>{notice}</Notice>
          {!data.can_manage && (
            <p className="text-sm text-foreground-muted">
              Only organization admins can approve or remove chat models.
            </p>
          )}
          {data.can_manage && adding && (
            <CatalogSearch
              busy={busy}
              version={version}
              onApprove={(id) => void action(() => api.approveChatModel(id), `${id} was approved.`)}
            />
          )}
        </>
      )}
    </section>
  );
}
