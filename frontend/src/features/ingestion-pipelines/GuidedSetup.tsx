import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Database,
  FileStack,
  Globe,
  RefreshCw,
  Rows3,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { ErrorState } from '../../components/states/ErrorState';
import { LoadingState } from '../../components/states/LoadingState';
import { Alert, AlertDescription, AlertTitle } from '../../components/ui/alert';
import { Button } from '../../components/ui/button';
import { Progress } from '../../components/ui/progress';
import { ApiError } from '../../lib/api';
import { cn } from '../../lib/utils';
import { getEmbeddingSettings } from '../documents/indexApi';
import * as api from './api';
import { branchExecution, indexLayout, terminalIngestionStatuses } from './editorModel';
import {
  addSite,
  chunkSettings,
  clearGuidedDraft,
  customStages,
  editStage,
  estimatedChunks,
  guidedSites,
  guidedSteps,
  loadGuidedDraft,
  newGuidedDraft,
  pageTotal,
  removeSite,
  resetSiteToShared,
  setChunk,
  setLayout,
  setSitePages,
  siteHost,
  sourceProblems,
  storeGuidedDraft,
  withIndexNames,
  type GuidedDraft,
  type GuidedStep,
} from './guidedModel';
import type { ExtractionCapabilities, IngestionRun, IngestionRunGroup } from './model';
import {
  OutputStep,
  ProcessingStep,
  ReviewStep,
  RunStep,
  SourcesStep,
  type PreviewState,
  type ReviewEntry,
} from './components/GuidedSetupSteps';

const POLL_DELAY_MS = 2000;
const format = (value: number) => value.toLocaleString('en-US');

const message = (cause: unknown) =>
  cause instanceof Error ? cause.message : 'The request could not be completed.';

function problemsOf(cause: unknown) {
  if (cause instanceof ApiError && cause.status === 422 && cause.issues?.length) {
    return cause.issues.map((issue) => issue.msg);
  }
  return [];
}

type Saved = NonNullable<GuidedDraft['saved']>;

// Spec 0003 guided setup: an extra way to create a Website ingestion pipeline. It saves
// through the same endpoint as the canvas editor, which stays the place to edit afterwards.
export function GuidedSetup({ projectId }: { projectId: string }) {
  const [guided, setGuided] = useState<GuidedDraft>();
  const [capabilities, setCapabilities] = useState<ExtractionCapabilities>();
  const [loadError, setLoadError] = useState('');
  const [revision, setRevision] = useState(0);
  const [stored, setStored] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ text: string; problems: string[] }>();
  const [previews, setPreviews] = useState<Record<string, PreviewState | undefined>>({});
  const [run, setRun] = useState<IngestionRun>();
  const [group, setGroup] = useState<IngestionRunGroup>();
  const previewControllers = useRef(new Map<string, AbortController>());
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    let disposed = false;
    setLoadError('');
    void Promise.all([getEmbeddingSettings(projectId), api.getExtractionCapabilities(projectId)])
      .then(([embedding, extraction]) => {
        if (disposed) {
          return;
        }
        if (!embedding.configured || !embedding.config) {
          throw new Error(
            embedding.error ||
              'Configure an embedding provider before creating ingestion pipelines.',
          );
        }
        setCapabilities(extraction);
        setGuided(loadGuidedDraft(projectId) ?? newGuidedDraft(embedding.config, extraction));
      })
      .catch((cause) => {
        if (!disposed) {
          setLoadError(message(cause));
        }
      });
    return () => {
      disposed = true;
    };
  }, [projectId, revision]);

  useEffect(() => {
    if (guided) {
      setStored(storeGuidedDraft(projectId, guided));
    }
  }, [guided, projectId]);

  useEffect(() => {
    const controllers = previewControllers.current;
    return () => {
      for (const controller of controllers.values()) {
        controller.abort();
      }
    };
  }, []);

  const saved = guided?.saved;

  // Poll the run (or run group) one request at a time until it finishes.
  useEffect(() => {
    if (!saved || (!saved.runId && !saved.groupId)) {
      return;
    }
    let disposed = false;
    let timer: number | undefined;
    async function poll(current: Saved) {
      try {
        let finished: boolean;
        if (current.groupId) {
          const next = await api.getIngestionRunGroup(projectId, current.groupId);
          if (disposed) {
            return;
          }
          setGroup(next);
          finished = !['queued', 'running'].includes(next.status);
        } else {
          const next = await api.getIngestionRun(projectId, current.runId as string);
          if (disposed) {
            return;
          }
          setRun(next);
          finished = terminalIngestionStatuses.has(next.status);
        }
        if (!finished) {
          timer = window.setTimeout(() => void poll(current), POLL_DELAY_MS);
        }
      } catch (cause) {
        if (!disposed) {
          setError({
            text: `Run progress could not be refreshed: ${message(cause)}`,
            problems: [],
          });
          timer = window.setTimeout(() => void poll(current), POLL_DELAY_MS * 5);
        }
      }
    }
    void poll(saved);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [projectId, saved]);

  const step = guided?.step ?? 1;
  useEffect(() => {
    headingRef.current?.focus({ preventScroll: false });
  }, [step]);

  const chunk = guided ? chunkSettings(guided) : undefined;
  const problems = useMemo(() => (guided ? sourceProblems(guided.draft) : []), [guided]);

  if (loadError) {
    return (
      <div className="p-4 md:p-6">
        <ErrorState
          headingLevel="h1"
          title="We couldn’t start the guided setup"
          message={loadError}
          onRetry={() => setRevision((value) => value + 1)}
        />
      </div>
    );
  }
  if (!guided) {
    return (
      <div className="p-4 md:p-6">
        <LoadingState label="Loading guided setup…" />
      </div>
    );
  }

  const current: GuidedDraft = guided;
  const draft = current.draft;
  const sites = guidedSites(draft);
  const perSource = indexLayout(draft) === 'per_source';
  const total = pageTotal(draft);
  const listHref = `#/projects/${projectId}/pipelines?kind=ingestion`;

  function update(change: (value: GuidedDraft) => GuidedDraft) {
    setError(undefined);
    setGuided((value) => (value ? change(value) : value));
  }
  const go = (next: GuidedStep) => update((value) => ({ ...value, step: next }));

  function previewSite(sourceId: string) {
    previewControllers.current.get(sourceId)?.abort();
    const controller = new AbortController();
    previewControllers.current.set(sourceId, controller);
    setPreviews((value) => ({ ...value, [sourceId]: { status: 'running' } }));
    const finish = (state: PreviewState) => {
      if (!controller.signal.aborted) {
        setPreviews((value) => ({ ...value, [sourceId]: state }));
      }
    };
    void (async () => {
      try {
        let preview = await api.previewIngestion(projectId, branchExecution(draft, sourceId));
        while (!terminalIngestionStatuses.has(preview.status) && preview.status !== 'expired') {
          await new Promise((resolve) => window.setTimeout(resolve, POLL_DELAY_MS));
          if (controller.signal.aborted) {
            return;
          }
          preview = await api.getSourcePreview(projectId, preview.id);
        }
        finish(
          preview.status === 'succeeded'
            ? { status: 'succeeded', included: preview.included_count }
            : {
                status: 'failed',
                message: preview.error || `The preview ended as ${preview.status}.`,
              },
        );
      } catch (cause) {
        finish({ status: 'failed', message: message(cause) });
      }
    })();
  }

  function forgetPreview(sourceId: string) {
    previewControllers.current.get(sourceId)?.abort();
    setPreviews((value) => ({ ...value, [sourceId]: undefined }));
  }

  async function saveAndPublish() {
    setBusy(true);
    setError(undefined);
    let version = current.saved;
    try {
      if (!version) {
        const created = await api.createIngestionPipeline(projectId, draft);
        version = { pipelineId: created.pipeline_id, versionId: created.id };
        const kept = version;
        setGuided((value) => (value ? { ...value, saved: kept } : value));
      }
      const pipelineId = version.pipelineId;
      const versionId = version.versionId;
      if (perSource) {
        const started = await api.startIngestionRunGroup(projectId, pipelineId, versionId);
        setGroup(started);
        version = { ...version, groupId: started.id };
      } else {
        const started = await api.startIngestionRun(projectId, pipelineId, versionId, {
          source_input: { kind: 'refresh' },
        });
        setRun(started);
        version = { ...version, runId: started.id };
      }
      const final = version;
      setGuided((value) => (value ? { ...value, saved: final, step: 5 } : value));
    } catch (cause) {
      setError({
        text: version
          ? `Version 1 was saved, but the run could not start: ${message(cause)}`
          : `The pipeline could not be saved: ${message(cause)}`,
        problems: problemsOf(cause),
      });
    } finally {
      setBusy(false);
    }
  }

  function discard() {
    if (!saved && !window.confirm('Discard this guided setup draft?')) {
      return;
    }
    for (const controller of previewControllers.current.values()) {
      controller.abort();
    }
    clearGuidedDraft(projectId);
    setPreviews({});
    setRun(undefined);
    setGroup(undefined);
    setGuided(undefined);
    setRevision((value) => value + 1);
  }

  const extract = draft.execution.nodes.find((node) => node.type === 'extract');
  const clean = draft.execution.nodes.find((node) => node.type === 'clean');
  const embed = draft.execution.nodes.find((node) => node.type === 'embed');
  const overallProgress = group
    ? Math.round(
        group.runs.reduce((sum, entry) => sum + entry.progress, 0) / Math.max(1, group.runs.length),
      )
    : (run?.progress ?? 0);

  const content: {
    heading: string;
    tip: string;
    FigureIcon: LucideIcon;
    figureLabel: string;
    figure: string;
  } = [
    {
      heading: 'Which websites should this pipeline read?',
      tip: 'Sites on different domains are collected at the same time, up to three at once.',
      FigureIcon: FileStack,
      figureLabel: 'Pages per run',
      figure: format(total),
    },
    {
      heading: 'How should these sites be indexed?',
      tip: 'One combined index answers across every site; separate indexes keep each site on its own.',
      FigureIcon: Database,
      figureLabel: 'Indexes',
      figure: perSource ? String(sites.length) : '1',
    },
    {
      heading: 'How should pages be processed?',
      tip: 'Smaller chunks give more precise matches; larger chunks keep more surrounding context.',
      FigureIcon: Rows3,
      figureLabel: 'Est. chunks',
      figure: chunk ? `≈ ${format(estimatedChunks(draft, chunk.size, chunk.overlap))}` : '–',
    },
    {
      heading: 'Review and publish.',
      tip: 'Saving creates version 1. Every run records exactly which version it used.',
      FigureIcon: Globe,
      figureLabel: 'Up to',
      figure: `${format(total)} pages`,
    },
    {
      heading: 'Collecting your sources.',
      tip: 'Each site is checked against its robots.txt and crawl speed before any page is fetched.',
      FigureIcon: RefreshCw,
      figureLabel: 'Progress',
      figure: `${overallProgress}%`,
    },
  ][step - 1];

  const review: ReviewEntry[] = [
    { key: 'Sources', value: sites.map(siteHost).join(', ') || 'None', step: 1 },
    { key: 'Name', value: draft.name.trim() || 'Ingested knowledge', step: 2 },
    {
      key: 'Output',
      value: perSource
        ? `${sites.length} indexes, one per site`
        : `1 index · ${draft.name.trim() || 'Ingested knowledge'}`,
      step: 2,
    },
    {
      key: 'Processing',
      value: [
        extract?.type === 'extract' ? `${extract.strategy ?? 'auto'} extraction` : '',
        clean?.type === 'clean'
          ? clean.profile === 'structure-aware-v1'
            ? 'structure-aware cleaning'
            : 'compatibility cleaning'
          : '',
        chunk ? `${chunk.size}-token chunks, ${chunk.overlap} overlap` : '',
        perSource && sites.some((site) => customStages(current, site.id).length > 0)
          ? 'some sites use their own settings'
          : '',
      ]
        .filter(Boolean)
        .join(' · '),
      step: 3,
    },
    {
      key: 'Embedding',
      value: embed?.type === 'embed' ? `${embed.model} · ${embed.dimensions} dimensions` : '–',
      step: 3,
    },
    {
      key: 'If a site fails',
      value: perSource
        ? 'The other indexes still publish'
        : 'The other sites still publish; the failed site keeps its earlier pages',
      step: 2,
    },
  ];

  const finished = group
    ? !['queued', 'running'].includes(group.status)
    : run
      ? terminalIngestionStatuses.has(run.status)
      : false;
  const blocked = step === 1 ? problems : [];
  const editorHref = saved
    ? `#/projects/${projectId}/pipelines/${saved.pipelineId}?kind=ingestion&version=${saved.versionId}`
    : '';

  return (
    <div className="flex flex-col md:min-h-(--shell-content)">
      <div className="flex flex-wrap items-center gap-2 px-4 pt-4 md:px-6">
        <p className="min-w-0 flex-1 basis-sidebar text-sm font-semibold">
          Guided setup <span className="font-normal text-foreground-muted">by</span> RAG{' '}
          <span className="text-accent">Quality</span> Studio
        </p>
        <Button variant="outline" onClick={discard} disabled={busy}>
          {saved ? 'Start a new setup' : 'Discard draft'}
        </Button>
        <Button variant="ghost" asChild>
          <a href={listHref}>Close</a>
        </Button>
      </div>

      <div className="flex flex-1 flex-col gap-4 px-4 pt-8 pb-6 md:px-6">
        <h1
          ref={headingRef}
          tabIndex={-1}
          className="text-xl font-medium text-heading outline-none"
        >
          {content.heading}
        </h1>
        <div className="flex min-h-row flex-wrap items-center gap-x-6 gap-y-2 rounded-card border border-banner-border bg-banner px-4 py-2">
          <Zap aria-hidden="true" className="size-4 shrink-0 text-highlight" />
          <p className="min-w-0 flex-1 basis-sidebar text-sm">{content.tip}</p>
          <p className="flex items-center gap-2 text-sm font-medium">
            <content.FigureIcon aria-hidden="true" className="size-4 text-foreground-muted" />
            {content.figureLabel}
            <span className="text-lg font-semibold text-accent tabular-nums">{content.figure}</span>
          </p>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertTitle>{error.text}</AlertTitle>
            {error.problems.length > 0 && (
              <AlertDescription>
                <ul className="list-disc pl-4">
                  {error.problems.map((problem) => (
                    <li key={problem}>{problem}</li>
                  ))}
                </ul>
              </AlertDescription>
            )}
          </Alert>
        )}

        {step === 1 && (
          <SourcesStep
            guided={current}
            previews={previews}
            busy={busy}
            onAdd={(url) => update((value) => ({ ...value, draft: addSite(value, url).draft }))}
            onRemove={(sourceId) => {
              forgetPreview(sourceId);
              update((value) => {
                const next = { ...value, draft: removeSite(value.draft, sourceId) };
                return { ...next, customized: dropSource(next.customized, sourceId) };
              });
            }}
            onPages={(sourceId, pages) => {
              forgetPreview(sourceId);
              update((value) => ({ ...value, draft: setSitePages(value.draft, sourceId, pages) }));
            }}
            onPreview={previewSite}
          />
        )}
        {step === 2 && (
          <OutputStep
            guided={current}
            onName={(name) =>
              update((value) => ({ ...value, draft: withIndexNames({ ...value.draft, name }) }))
            }
            onLayout={(layout) =>
              update((value) => ({ ...value, draft: setLayout(value, layout), customized: {} }))
            }
          />
        )}
        {step === 3 && (
          <ProcessingStep
            guided={current}
            capabilities={capabilities}
            onExtract={(strategy) =>
              update((value) =>
                editStage(value, 'extract', (node) =>
                  node.type === 'extract' ? { ...node, strategy } : node,
                ),
              )
            }
            onClean={(structureAware) =>
              update((value) =>
                editStage(value, 'clean', (node) => {
                  const profile = capabilities?.cleaning_profiles?.[0];
                  if (node.type !== 'clean') {
                    return node;
                  }
                  return structureAware && profile
                    ? {
                        ...node,
                        profile: profile.id,
                        config_version: profile.config_version,
                        steps: structuredClone(profile.steps),
                        normalize_whitespace: true,
                        repeated_boilerplate: [],
                      }
                    : {
                        ...node,
                        profile: 'standard-v1',
                        config_version: 'deterministic-clean-v1',
                        steps: [],
                      };
                }),
              )
            }
            onChunk={(size, overlap, sourceId) =>
              update((value) => setChunk(value, size, overlap, sourceId))
            }
            onUseShared={(sourceId) => update((value) => resetSiteToShared(value, sourceId))}
          />
        )}
        {step === 4 && (
          <ReviewStep
            entries={review}
            onEdit={saved ? undefined : (next) => go(next as GuidedStep)}
          />
        )}
        {step === 5 && <RunStep guided={current} run={run} group={group} />}
      </div>

      <div className="sticky bottom-0 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border bg-surface px-4 py-3 max-md:bottom-(--tabbar-height) md:px-6">
        <div className="flex min-w-0 flex-1 basis-sidebar flex-wrap items-center gap-x-4 gap-y-1">
          <Progress
            aria-label="Setup progress"
            value={(step / guidedSteps.length) * 100}
            className="h-1 w-16 bg-track"
          />
          <span className="text-xs font-semibold">
            Step {step} of {guidedSteps.length}
          </span>
          <span className="text-xs text-foreground-muted">{guidedSteps[step - 1]}</span>
          <span
            className={cn(
              'flex items-center gap-1 text-xs',
              stored ? 'text-foreground-muted' : 'text-warning',
            )}
          >
            {stored && <Check aria-hidden="true" className="size-3" />}
            {saved
              ? 'Saved as version 1'
              : stored
                ? 'Draft saved'
                : 'Draft not saved in this browser'}
          </span>
          {blocked.length > 0 && (
            <span className="w-full text-xs text-foreground-muted">{blocked.join(' ')}</span>
          )}
        </div>
        {step > 1 && step < 5 && (
          <Button
            variant="outline"
            className="max-md:flex-1"
            disabled={busy}
            onClick={() => go((step - 1) as GuidedStep)}
          >
            <ChevronLeft aria-hidden="true" />
            Previous
          </Button>
        )}
        {step < 4 && (
          <Button
            className="max-md:flex-1"
            disabled={blocked.length > 0}
            onClick={() => go((step + 1) as GuidedStep)}
          >
            Next: {guidedSteps[step as 1 | 2 | 3]}
            <ChevronRight aria-hidden="true" />
          </Button>
        )}
        {step === 4 && (
          <Button
            className="max-md:flex-1"
            loading={busy}
            disabled={problems.length > 0}
            onClick={() => void saveAndPublish()}
          >
            {saved
              ? 'Start the run'
              : perSource
                ? `Save and publish ${sites.length} indexes`
                : 'Save and publish'}
            <ChevronRight aria-hidden="true" />
          </Button>
        )}
        {step === 5 && (
          <Button variant={finished ? 'primary' : 'outline'} className="max-md:flex-1" asChild>
            <a href={editorHref}>
              Open in editor
              <ChevronRight aria-hidden="true" />
            </a>
          </Button>
        )}
      </div>
    </div>
  );
}

function dropSource(customized: GuidedDraft['customized'], sourceId: string) {
  return Object.fromEntries(
    Object.entries(customized).map(([stage, ids]) => [
      stage,
      (ids ?? []).filter((id) => id !== sourceId),
    ]),
  ) as GuidedDraft['customized'];
}
