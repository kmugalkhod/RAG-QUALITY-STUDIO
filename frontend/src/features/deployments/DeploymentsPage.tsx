import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { ArrowLeft, Copy, KeyRound, Pause, Play, Plus, RotateCcw, ShieldCheck } from 'lucide-react';

import { InlineError, Notice } from '../../components/parts';
import { PageHeader } from '../../components/PageHeader';
import { EmptyState } from '../../components/states/EmptyState';
import { ErrorState } from '../../components/states/ErrorState';
import { LoadingState } from '../../components/states/LoadingState';
import { StatusBadge } from '../../components/StatusBadge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../components/ui/native-select';
import { allPages, type Page } from '../../lib/pagination';
import { cn } from '../../lib/utils';
import { listIndexes } from '../documents/indexApi';
import { formatIndexOption, type IndexVersion } from '../documents/model';
import { listPipelines, listPipelineVersions } from '../pipelines/api';
import type { Pipeline, PipelineVersion } from '../pipelines/model';
import * as api from './api';
import { WidgetSettings } from './WidgetSettings';

type Props = { projectId: string; deploymentId?: string };
const short = (id: string) => id.slice(0, 8);
const path = (projectId: string, id?: string) =>
  `#/projects/${projectId}/deployments${id ? `/${id}` : ''}`;

function versionIndex(version: PipelineVersion | undefined): string {
  return version?.execution.nodes.find((node) => node.type === 'retriever')?.index_id || '';
}

function date(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : '—';
}

export function DeploymentsPage({ projectId, deploymentId }: Props) {
  const [permission, setPermission] = useState<api.Permissions>();
  const [items, setItems] = useState<api.Deployment[]>();
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [versions, setVersions] = useState<PipelineVersion[]>([]);
  const [indexes, setIndexes] = useState<IndexVersion[]>([]);
  const [deployment, setDeployment] = useState<api.Deployment>();
  const [releases, setReleases] = useState<api.Release[]>([]);
  const [keys, setKeys] = useState<api.KeyMetadata[]>([]);
  const [runPage, setRunPage] = useState<Page<api.RunSummary>>();
  const [runOffset, setRunOffset] = useState(0);
  const [pipelineId, setPipelineId] = useState('');
  const [versionId, setVersionId] = useState('');
  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  const [keyLabel, setKeyLabel] = useState('');
  const [oneTimeKey, setOneTimeKey] = useState<api.CreatedKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [revision, setRevision] = useState(0);
  const [limitDraft, setLimitDraft] = useState<api.Limits>();

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError('');
    void Promise.all([
      api.permissions(projectId),
      api.list(projectId),
      allPages((offset) => listPipelines(projectId, 'answer', offset)),
      allPages((offset) => listIndexes(projectId, offset)),
    ])
      .then(async ([permissions, page, available, ready]) => {
        const saved = permissions.can_manage
          ? (
              await Promise.all(
                available.map((pipeline) =>
                  allPages((offset) => listPipelineVersions(projectId, pipeline.id, offset)),
                ),
              )
            ).flat()
          : [];
        if (!alive) {
          return;
        }
        setPermission(permissions);
        setItems(page.items);
        setPipelines(available);
        setVersions(saved);
        setIndexes(ready);
      })
      .catch((cause: Error) => {
        if (alive) {
          setError(cause.message);
        }
      })
      .finally(() => {
        if (alive) {
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [projectId, revision]);

  useEffect(() => {
    setOneTimeKey(null);
    setRunOffset(0);
  }, [projectId, deploymentId]);

  useEffect(() => {
    if (!deploymentId) {
      setDeployment(undefined);
      return;
    }
    let alive = true;
    setDetailLoading(true);
    setError('');
    void Promise.all([
      api.detail(projectId, deploymentId),
      allPages((offset) => api.releases(projectId, deploymentId, offset)),
      api.runs(projectId, deploymentId, runOffset),
      ...(permission?.can_manage ? [api.keys(projectId, deploymentId)] : []),
    ])
      .then(([detail, history, runs, keyPage]) => {
        if (!alive) {
          return;
        }
        setDeployment(detail as api.Deployment);
        setLimitDraft((detail as api.Deployment).limits);
        setReleases(history as api.Release[]);
        setRunPage(runs as Page<api.RunSummary>);
        setKeys((keyPage as { items: api.KeyMetadata[] } | undefined)?.items || []);
      })
      .catch((cause: Error) => {
        if (alive) {
          setError(cause.message);
        }
      })
      .finally(() => {
        if (alive) {
          setDetailLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [projectId, deploymentId, runOffset, revision, permission?.can_manage]);

  const chosenVersion = useMemo(
    () => versions.find((version) => version.id === versionId),
    [versionId, versions],
  );
  const indexId = versionIndex(chosenVersion);
  const index = indexes.find((entry) => entry.id === indexId);
  const readyIndex = index?.status === 'succeeded';
  const visibleVersions = versions
    .filter((version) => version.pipeline_id === (deployment?.pipeline_id || pipelineId))
    .sort((a, b) => b.version - a.version);
  const activeRelease = releases.find((release) => release.id === deployment?.active_release_id);
  const canManage = !!permission?.can_manage;

  async function act(work: () => Promise<void>, success: string) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await work();
      setMessage(success);
      setRevision((current) => current + 1);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canManage || !pipelineId || !chosenVersion || !readyIndex || !name.trim()) {
      return;
    }
    void act(async () => {
      const created = await api.create(projectId, {
        name: name.trim(),
        pipeline_id: pipelineId,
        pipeline_version_id: chosenVersion.id,
        index_id: indexId,
        note: note.trim(),
      });
      window.location.hash = path(projectId, created.id);
      setName('');
      setNote('');
    }, 'Paused deployment created with release 1. Review and promote it to accept questions.');
  }

  function stage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!deployment || !chosenVersion || !readyIndex || !canManage) {
      return;
    }
    void act(async () => {
      await api.stage(projectId, deployment.id, {
        pipeline_version_id: chosenVersion.id,
        index_id: indexId,
        note: note.trim(),
      });
      setNote('');
      setVersionId('');
    }, 'Release staged. Traffic remains on the active release until you promote it.');
  }

  function makeKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!deployment || !keyLabel.trim() || !canManage) {
      return;
    }
    void act(async () => {
      const created = await api.createKey(projectId, deployment.id, keyLabel.trim());
      setOneTimeKey(created);
      setKeyLabel('');
    }, 'Key created. Copy it now; it cannot be displayed again.');
  }

  async function copyKey() {
    if (!oneTimeKey) {
      return;
    }
    try {
      await navigator.clipboard.writeText(oneTimeKey.secret);
      setMessage('Key copied to clipboard. Store it in your server-side secret store.');
    } catch {
      setError('Clipboard access failed. Select and copy the key manually before dismissing it.');
    }
  }

  const picker = (
    <>
      {!deployment && (
        <div>
          <Label htmlFor="deployment-pipeline">Answer pipeline</Label>
          <NativeSelect
            id="deployment-pipeline"
            value={pipelineId}
            onChange={(event) => {
              setPipelineId(event.target.value);
              setVersionId('');
            }}
          >
            <NativeSelectOption value="">Select a saved answer pipeline</NativeSelectOption>
            {pipelines.map((pipeline) => (
              <NativeSelectOption key={pipeline.id} value={pipeline.id}>
                {pipeline.name}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
      )}
      <div>
        <Label htmlFor="deployment-version">Saved pipeline version</Label>
        <NativeSelect
          id="deployment-version"
          value={versionId}
          onChange={(event) => setVersionId(event.target.value)}
        >
          <NativeSelectOption value="">Select a version</NativeSelectOption>
          {visibleVersions.map((version) => (
            <NativeSelectOption key={version.id} value={version.id}>
              Version {version.version} · {short(version.id)}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
      <div className="text-sm text-foreground-muted">
        {chosenVersion ? (
          <>
            <span className="block">Pinned index from this saved retriever:</span>
            <span className="block break-all font-mono text-foreground">
              {indexId || 'Missing index'}
            </span>
            <span className="block">
              {index ? formatIndexOption(index) : 'Index is unavailable in this project.'}
            </span>
            {!readyIndex && (
              <span className="text-warning">Select a version with a ready index.</span>
            )}
          </>
        ) : (
          'A saved version determines the exact index. To change indexes, save a new answer pipeline version.'
        )}
      </div>
      <div>
        <Label htmlFor="deployment-note">Release note</Label>
        <Input
          id="deployment-note"
          value={note}
          maxLength={500}
          onChange={(event) => setNote(event.target.value)}
          placeholder="What changed in this release?"
        />
      </div>
    </>
  );

  return (
    <section className="flex flex-col gap-6 pb-16">
      <PageHeader
        title="Answer deployments"
        meta="Pin a saved answer pipeline and ready index, then control when its server endpoint accepts questions."
      />
      {error && !loading && !permission ? (
        <ErrorState
          title="We couldn’t load deployments"
          message={error}
          onRetry={() => setRevision((value) => value + 1)}
        />
      ) : error ? (
        <InlineError onRetry={() => setRevision((value) => value + 1)}>{error}</InlineError>
      ) : null}
      <Notice>{message}</Notice>
      {loading ? (
        <LoadingState label="Loading deployments…" />
      ) : !permission ? null : (
        <div className="grid gap-6 desktop:grid-cols-[var(--spacing-panel)_minmax(0,1fr)]">
          <nav aria-label="Answer deployments" className="min-w-0">
            <div className="mb-4 flex items-center justify-between gap-2">
              <h2 className="text-base font-semibold">Deployments</h2>
              {canManage && (
                <Button variant="outline" size="sm" asChild>
                  <a href={path(projectId)}>
                    <Plus /> New
                  </a>
                </Button>
              )}
            </div>
            {!items?.length ? (
              <EmptyState
                className="p-6"
                title="No answer deployments yet"
                description="Create one to pin a saved pipeline version behind a server endpoint."
              />
            ) : (
              <ul className="flex flex-col gap-1">
                {items.map((item) => (
                  <li key={item.id}>
                    <a
                      href={path(projectId, item.id)}
                      aria-current={deploymentId === item.id ? 'page' : undefined}
                      className={cn(
                        'flex min-h-row flex-col justify-center rounded-control px-4 py-2 text-sm outline-none hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-accent',
                        deploymentId === item.id
                          ? 'bg-surface-hover text-foreground'
                          : 'text-foreground-muted',
                      )}
                    >
                      <span className="block truncate font-medium text-foreground">
                        {item.name}
                      </span>
                      <span className="capitalize">
                        {item.state} · revision {item.revision}
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </nav>
          <div className="min-w-0">
            {!deploymentId ? (
              canManage ? (
                <form
                  onSubmit={create}
                  className="flex flex-col gap-4 rounded-card border border-border bg-surface p-4 md:p-6"
                >
                  <h2 className="text-base font-semibold text-foreground">
                    Create a paused deployment
                  </h2>
                  <p className="text-sm text-foreground-muted">
                    Creation saves release 1. It sends no traffic until you promote it.
                  </p>
                  <div>
                    <Label htmlFor="deployment-name">Deployment name</Label>
                    <Input
                      id="deployment-name"
                      value={name}
                      maxLength={120}
                      required
                      onChange={(event) => setName(event.target.value)}
                      placeholder="Support answers"
                    />
                  </div>
                  {picker}
                  <Button
                    type="submit"
                    disabled={busy || !name.trim() || !chosenVersion || !readyIndex}
                  >
                    Create paused deployment
                  </Button>
                </form>
              ) : (
                <p className="text-sm text-foreground-muted">
                  Only a project owner or admin can create answer deployments.
                </p>
              )
            ) : detailLoading ? (
              <LoadingState label="Loading deployment…" />
            ) : !deployment ? null : (
              <div className="flex flex-col gap-8">
                <div className="flex flex-col items-start gap-2">
                  <Button variant="ghost" size="sm" asChild>
                    <a href={path(projectId)}>
                      <ArrowLeft /> All deployments
                    </a>
                  </Button>
                  <div className="flex w-full flex-wrap items-center justify-between gap-4">
                    <div className="flex min-w-0 flex-col gap-1">
                      <h2 className="text-lg font-semibold text-foreground wrap-anywhere">
                        {deployment.name}
                      </h2>
                      <p className="text-sm text-foreground-muted capitalize">
                        {deployment.state} · revision {deployment.revision}
                      </p>
                    </div>
                    <StatusBadge status={deployment.accepting_questions ? 'succeeded' : 'uploaded'}>
                      {deployment.accepting_questions
                        ? 'Accepting questions'
                        : 'Not accepting questions'}
                    </StatusBadge>
                  </div>
                  <p className="text-xs text-foreground-muted break-all">
                    Pipeline {deployment.pipeline_id}
                  </p>
                </div>

                <WidgetSettings
                  projectId={projectId}
                  deployment={deployment}
                  canManage={canManage}
                  onSaved={() => setRevision((value) => value + 1)}
                />

                <section aria-labelledby="release-heading" className="flex flex-col gap-4">
                  <h3 id="release-heading" className="text-base font-semibold">
                    Release history
                  </h3>
                  <p className="text-sm text-foreground-muted">
                    A saved edit or newly ready index does not change the active release.
                  </p>
                  <ul className="flex flex-col gap-2">
                    {releases.map((release) => {
                      const active = release.id === deployment.active_release_id;
                      const rollback =
                        !!activeRelease && release.release_number < activeRelease.release_number;
                      return (
                        <li
                          key={release.id}
                          className="rounded-card border border-border bg-surface p-4 text-sm"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-4">
                            <div className="flex min-w-0 flex-col gap-1">
                              <p className="flex flex-wrap items-center gap-2 font-semibold">
                                Release {release.release_number}
                                {active && (
                                  <StatusBadge status="succeeded">Active selection</StatusBadge>
                                )}
                              </p>
                              <p className="text-foreground-muted">
                                Saved {date(release.created_at)}{' '}
                                {release.note && `· ${release.note}`}
                              </p>
                              <p className="break-all">
                                Pipeline version <code>{release.pipeline_version_id}</code>
                              </p>
                              <p className="break-all">
                                Index version <code>{release.index_id}</code>
                              </p>
                              <p className="break-all text-xs text-foreground-muted">
                                Execution SHA-256 {release.execution_sha256}
                              </p>
                            </div>
                            {canManage && !active && deployment.state !== 'archived' && (
                              <Button
                                variant="outline"
                                size="sm"
                                disabled={busy || !reason.trim()}
                                onClick={() =>
                                  void act(
                                    async () => {
                                      await api.promote(
                                        projectId,
                                        deployment.id,
                                        release.id,
                                        reason.trim(),
                                        deployment.revision,
                                      );
                                      setReason('');
                                    },
                                    rollback
                                      ? `Rolled back to release ${release.release_number}.`
                                      : `Promoted release ${release.release_number}.`,
                                  )
                                }
                              >
                                {rollback ? <RotateCcw /> : <Play />}{' '}
                                {rollback ? 'Rollback' : 'Promote'}
                              </Button>
                            )}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                  {canManage && deployment.state !== 'archived' && (
                    <div className="flex flex-col gap-4 rounded-card border border-border p-4">
                      <div>
                        <Label htmlFor="deployment-reason">Promotion or rollback reason</Label>
                        <Input
                          id="deployment-reason"
                          value={reason}
                          maxLength={500}
                          onChange={(event) => setReason(event.target.value)}
                          placeholder="Why this release is being selected"
                        />
                      </div>
                      <form
                        onSubmit={stage}
                        className="flex flex-col gap-4 border-t border-border pt-4 [&>[data-slot=button]]:self-start"
                      >
                        <h4 className="text-sm font-semibold text-foreground">
                          Stage another saved version
                        </h4>
                        {picker}
                        <Button
                          type="submit"
                          variant="outline"
                          disabled={busy || !chosenVersion || !readyIndex}
                        >
                          Stage release
                        </Button>
                      </form>
                    </div>
                  )}
                </section>

                {canManage && deployment.state !== 'archived' && (
                  <section
                    aria-labelledby="controls-heading"
                    className="flex flex-col gap-4 border-t border-border pt-6"
                  >
                    <h3 id="controls-heading" className="text-base font-semibold">
                      Traffic controls
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {deployment.state === 'active' ? (
                        <Button
                          variant="outline"
                          disabled={busy}
                          onClick={() =>
                            void act(async () => {
                              await api.pause(projectId, deployment.id, deployment.revision);
                            }, 'Admissions paused. Accepted runs keep their pinned release.')
                          }
                        >
                          <Pause /> Pause
                        </Button>
                      ) : deployment.active_release_id ? (
                        <Button
                          variant="outline"
                          disabled={busy}
                          onClick={() =>
                            void act(async () => {
                              await api.resume(projectId, deployment.id, deployment.revision);
                            }, 'Admissions resumed on the selected release.')
                          }
                        >
                          <Play /> Resume
                        </Button>
                      ) : null}
                    </div>
                    <div>
                      <Label htmlFor="archive-reason">Archive reason</Label>
                      <Input
                        id="archive-reason"
                        value={reason}
                        maxLength={500}
                        onChange={(event) => setReason(event.target.value)}
                        placeholder="Why this endpoint is retired"
                      />
                      <Button
                        variant="destructive"
                        disabled={busy || !reason.trim()}
                        onClick={() =>
                          void act(async () => {
                            await api.archive(
                              projectId,
                              deployment.id,
                              reason.trim(),
                              deployment.revision,
                            );
                            setOneTimeKey(null);
                            setReason('');
                          }, 'Deployment archived. Keys revoked and queued runs cancelled.')
                        }
                      >
                        Archive deployment
                      </Button>
                    </div>
                  </section>
                )}

                <section
                  aria-labelledby="limits-heading"
                  className="flex flex-col gap-4 border-t border-border pt-6"
                >
                  <h3 id="limits-heading" className="text-base font-semibold">
                    Admission limits
                  </h3>
                  <p className="text-sm text-foreground-muted">
                    These limits apply to new questions. Organization and operator ceilings still
                    apply.
                  </p>
                  {limitDraft && (
                    <form
                      className="grid gap-4 md:grid-cols-2"
                      onSubmit={(event) => {
                        event.preventDefault();
                        if (!canManage) {
                          return;
                        }
                        void act(async () => {
                          await api.updateLimits(
                            projectId,
                            deployment.id,
                            limitDraft,
                            deployment.revision,
                          );
                        }, 'Admission limits updated.');
                      }}
                    >
                      {(
                        [
                          ['rate_per_minute', 'Questions per minute'],
                          ['concurrent_runs', 'Concurrent runs'],
                          ['queued_runs', 'Queued runs'],
                          ['daily_budget_usd', 'Daily budget (USD)'],
                          ['monthly_budget_usd', 'Monthly budget (USD)'],
                        ] as const
                      ).map(([field, label]) => (
                        <div key={field}>
                          <Label htmlFor={`deployment-${field}`}>{label}</Label>
                          <Input
                            id={`deployment-${field}`}
                            type="number"
                            min={field.endsWith('usd') ? '0.01' : '1'}
                            step={field.endsWith('usd') ? '0.01' : '1'}
                            value={limitDraft[field]}
                            disabled={!canManage || deployment.state === 'archived'}
                            onChange={(event) =>
                              setLimitDraft(
                                (current) =>
                                  current && {
                                    ...current,
                                    [field]: field.endsWith('usd')
                                      ? event.target.value
                                      : Number(event.target.value),
                                  },
                              )
                            }
                          />
                        </div>
                      ))}
                      {canManage && deployment.state !== 'archived' && (
                        <div className="md:col-span-2">
                          <Button type="submit" variant="outline" disabled={busy}>
                            Save limits
                          </Button>
                        </div>
                      )}
                    </form>
                  )}
                </section>

                {canManage && (
                  <section
                    aria-labelledby="keys-heading"
                    className="flex flex-col gap-4 border-t border-border pt-6"
                  >
                    <h3
                      id="keys-heading"
                      className="flex items-center gap-2 text-base font-semibold"
                    >
                      <KeyRound size={17} /> Server keys
                    </h3>
                    <p className="text-sm text-foreground-muted">
                      Use these keys only on a server. They cannot be recovered after this screen is
                      dismissed.
                    </p>
                    {oneTimeKey && (
                      <div
                        role="status"
                        className="flex flex-col gap-2 rounded-card border border-warning bg-surface p-4"
                      >
                        <p className="font-semibold">Copy this key now</p>
                        <p className="text-sm">
                          Store it in a server-side secret store. This value disappears when you
                          dismiss it or leave the page.
                        </p>
                        <output
                          aria-label="New deployment key"
                          className="block rounded-control border border-border bg-background p-4 font-mono text-sm break-all text-foreground"
                        >
                          {oneTimeKey.secret}
                        </output>
                        <div className="flex flex-wrap gap-2">
                          <Button onClick={() => void copyKey()}>
                            <Copy /> Copy key
                          </Button>
                          <Button variant="outline" onClick={() => setOneTimeKey(null)}>
                            Dismiss key
                          </Button>
                        </div>
                      </div>
                    )}
                    {deployment.state !== 'archived' && (
                      <form
                        onSubmit={makeKey}
                        className="flex flex-col gap-4 md:flex-row md:items-end"
                      >
                        <div className="min-w-0 flex-1">
                          <Label htmlFor="key-label">Key label</Label>
                          <Input
                            id="key-label"
                            value={keyLabel}
                            maxLength={120}
                            required
                            onChange={(event) => setKeyLabel(event.target.value)}
                            placeholder="Customer server"
                          />
                        </div>
                        <Button type="submit" disabled={busy || !keyLabel.trim()}>
                          <Plus /> Create key
                        </Button>
                      </form>
                    )}
                    {!keys.length ? (
                      <p className="text-sm text-foreground-muted">No keys issued.</p>
                    ) : (
                      <ul className="flex flex-col gap-2">
                        {keys.map((key) => (
                          <li
                            key={key.id}
                            className="flex flex-wrap items-center justify-between gap-4 rounded-card border border-border p-4 text-sm"
                          >
                            <div>
                              <p className="font-medium">
                                {key.label}{' '}
                                <code className="text-foreground-muted">{key.prefix}</code>
                              </p>
                              <p className="text-xs text-foreground-muted">
                                {key.revoked_at
                                  ? `Revoked ${date(key.revoked_at)}`
                                  : `Created ${date(key.created_at)} · Expires ${date(key.expires_at)}`}
                              </p>
                            </div>
                            {!key.revoked_at && deployment.state !== 'archived' && (
                              <div className="flex gap-2">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  disabled={busy}
                                  onClick={() =>
                                    void act(async () => {
                                      setOneTimeKey(
                                        await api.rotateKey(projectId, deployment.id, key.id),
                                      );
                                    }, 'Replacement key created. The old key expires after the rotation grace period.')
                                  }
                                >
                                  Rotate
                                </Button>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  disabled={busy}
                                  onClick={() =>
                                    void act(async () => {
                                      await api.revokeKey(projectId, deployment.id, key.id);
                                    }, 'Key revoked immediately.')
                                  }
                                >
                                  Revoke
                                </Button>
                              </div>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>
                )}

                <section
                  aria-labelledby="runs-heading"
                  className="flex flex-col gap-4 border-t border-border pt-6"
                >
                  <h3 id="runs-heading" className="flex items-center gap-2 text-base font-semibold">
                    <ShieldCheck size={17} /> Accepted runs
                  </h3>
                  {!runPage?.items.length ? (
                    <p className="text-sm text-foreground-muted">
                      No customer questions have been accepted.
                    </p>
                  ) : (
                    <ul className="flex flex-col gap-2">
                      {runPage.items.map((run) => (
                        <li
                          key={run.id}
                          className="flex flex-wrap justify-between gap-4 rounded-card border border-border p-4 text-sm"
                        >
                          <div>
                            <p className="font-medium capitalize">
                              {run.status.replaceAll('_', ' ')}{' '}
                              <span className="font-mono text-foreground-muted">
                                {short(run.id)}
                              </span>
                            </p>
                            <p className="text-xs text-foreground-muted">
                              Release {short(run.release_id)} · {date(run.created_at)} · reserved $
                              {run.cost_reservation_usd}
                            </p>
                            {run.error_code && (
                              <p className="text-xs text-warning">{run.error_code}</p>
                            )}
                          </div>
                          {canManage && ['queued', 'running'].includes(run.status) && (
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={busy}
                              onClick={() =>
                                void act(async () => {
                                  await api.cancelRun(projectId, deployment.id, run.id);
                                }, 'Cancellation requested.')
                              }
                            >
                              Cancel
                            </Button>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                  {runPage && runPage.total > runPage.limit && (
                    <div className="flex items-center gap-4 text-sm tabular-nums">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={runOffset === 0}
                        onClick={() => setRunOffset(Math.max(0, runOffset - runPage.limit))}
                      >
                        Previous
                      </Button>
                      <span>
                        {runOffset + 1}–{Math.min(runOffset + runPage.limit, runPage.total)} of{' '}
                        {runPage.total}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={runOffset + runPage.limit >= runPage.total}
                        onClick={() => setRunOffset(runOffset + runPage.limit)}
                      >
                        Next
                      </Button>
                    </div>
                  )}
                </section>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
