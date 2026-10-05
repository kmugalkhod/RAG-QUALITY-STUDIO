import { useEffect, useState, type CSSProperties } from 'react';
import { Check, FileText, Square, X } from 'lucide-react';

import { Pagination } from '../../../components/Pagination';
import { CARD, LINK, LIST, LIST_ROW, META, PRE } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import type { Page } from '../../../lib/pagination';
import { docsHref } from '../../../lib/docs';
import { cn } from '../../../lib/utils';
import { terminalIngestionStatuses } from '../editorModel';
import * as api from '../api';
import type {
  ContentBlock,
  ContentDerivation,
  CleaningDiff,
  ChunkInspectionPage,
  IngestionRun,
  IngestionRunItem,
  SourcePreview,
  SourcePreviewItem,
  SourcePreviewRepresentation,
  WebsiteFetchPolicy,
} from '../model';
import { describeFetchPolicy } from '../model';

// Result sections on the spec 0002 tokens and grid.
const SECTION = 'flex flex-col gap-6 border-t border-border px-4 py-6 md:px-6';
const HEADING_ROW = 'flex flex-wrap items-start justify-between gap-4';
const HEADING_COPY =
  'flex min-w-0 flex-col gap-1 [&>h2]:text-base [&>h2]:font-semibold [&>h2]:text-foreground [&>h3]:text-base [&>h3]:font-semibold [&>h3]:text-foreground [&>p]:text-sm [&>p]:text-foreground-muted [&>small]:text-xs [&>small]:text-foreground-muted';
/** Item rows: an icon, a title with detail lines, and one action. */
const ITEM = cn(
  LIST_ROW,
  'flex flex-col gap-3 p-4 md:flex-row md:items-start [&>svg]:size-4 [&>svg]:shrink-0 [&>svg]:text-foreground-subtle [&>div]:flex [&>div]:min-w-0 [&>div]:flex-1 [&>div]:flex-col [&>div]:gap-1 [&_p]:text-sm [&_p]:text-foreground-muted [&_small]:text-xs [&_small]:wrap-anywhere [&_small:not([role=alert])]:text-foreground-muted [&_strong]:text-sm [&_strong]:font-medium [&_strong]:wrap-anywhere',
);
const INSPECTOR = cn(
  CARD,
  'flex flex-col gap-4 p-4 md:p-6 [&>p]:text-sm [&>p]:text-foreground-muted',
);
const TAB = 'aria-selected:border-accent aria-selected:text-accent';
const QUALITY =
  'grid grid-cols-2 gap-x-4 gap-y-2 text-sm text-foreground [&_dd]:wrap-anywhere [&_dt]:text-foreground-muted';
/** Stacked record cards: a heading block, labeled text and optional detail. */
const RECORDS =
  'flex flex-col gap-2 [&>li]:flex [&>li]:min-w-0 [&>li]:flex-col [&>li]:gap-2 [&>li]:rounded-control [&>li]:border [&>li]:border-border [&>li]:bg-background [&>li]:p-4 [&>li[data-selected=true]]:border-accent [&_section]:flex [&_section]:min-w-0 [&_section]:flex-col [&_section]:gap-1 [&_small]:text-xs [&_small]:text-foreground-muted [&_span]:text-sm [&_span]:text-foreground-muted [&_strong]:text-sm [&_strong]:font-medium [&_strong]:text-foreground [&>li>div:first-child]:flex [&>li>div:first-child]:flex-col [&>li>div:first-child]:gap-1';
const ERROR_TEXT = 'text-sm text-danger wrap-anywhere';

/** The exact server-recorded Website limits a preview or run used. */
function FetchLimits({ policies }: { policies?: Record<string, WebsiteFetchPolicy> }) {
  const entries = Object.entries(policies ?? {});
  return entries.map(([nodeId, policy]) => (
    <small key={nodeId}>
      Fetch limits used{entries.length > 1 ? ` (${nodeId})` : ''}: {describeFetchPolicy(policy)}
    </small>
  ));
}

function previewLanguage(metrics: Record<string, unknown>) {
  const value = metrics.language;
  if (!value || typeof value !== 'object') {
    return null;
  }
  const language = (value as Record<string, unknown>).language;
  const confidence = (value as Record<string, unknown>).confidence;
  return typeof language === 'string'
    ? `${language}${typeof confidence === 'number' ? ` · ${Math.round(confidence * 100)}%` : ''}`
    : null;
}

function blockOrigin(block: ContentBlock): 'Native' | 'Layout' | 'OCR' | null {
  const origin = block.attributes.origin;
  return origin === 'native'
    ? 'Native'
    : origin === 'layout'
      ? 'Layout'
      : origin === 'ocr'
        ? 'OCR'
        : null;
}

function tableRows(block: ContentBlock): string[][] | null {
  const value = block.attributes.table;
  if (!value || typeof value !== 'object' || !('rows' in value) || !Array.isArray(value.rows)) {
    return null;
  }
  const rows = value.rows
    .filter(Array.isArray)
    .map((row) => row.map((cell) => (typeof cell === 'string' ? cell : String(cell ?? ''))));
  return rows.length ? rows : null;
}

function overlayStyle(block: ContentBlock) {
  const box = block.bounding_box;
  if (!box || !['left', 'top', 'right', 'bottom'].every((key) => typeof box[key] === 'number')) {
    return undefined;
  }
  return {
    '--box-left': `${box.left * 100}%`,
    '--box-top': `${box.top * 100}%`,
    '--box-width': `${(box.right - box.left) * 100}%`,
    '--box-height': `${(box.bottom - box.top) * 100}%`,
  } as CSSProperties;
}

function sourceSpanLabel(span: Record<string, unknown>) {
  if (span.kind === 'provider_block') {
    return `${String(span.provider)} block · ${String(span.external_id)}`;
  }
  if (span.kind === 'artifact_text') {
    const page = span.page_number ? `page ${String(span.page_number)} · ` : '';
    return `${page}characters ${String(span.start_char)}–${String(span.end_char)}`;
  }
  if (span.kind === 'derived') {
    return `${Array.isArray(span.parent_block_ids) ? span.parent_block_ids.length : 0} parent blocks`;
  }
  return 'Source provenance unavailable';
}

function transformMetric(derivation: ContentDerivation, transform: string, metric: string): number {
  const value = derivation.transforms.find((item) => item.transform === transform)?.metrics?.[
    metric
  ];
  return typeof value === 'number' ? value : 0;
}

export function IngestionPreviewResults({
  projectId,
  preview,
  page,
  busy,
  onCancel,
  onRetry,
  onPageChange,
}: {
  projectId: string;
  preview: SourcePreview;
  page: Page<SourcePreviewItem>;
  busy: boolean;
  onCancel: () => void;
  onRetry: () => void;
  onPageChange: (offset: number) => void;
}) {
  const [selectedOrdinal, setSelectedOrdinal] = useState<number | null>(null);
  const [stage, setStage] = useState<SourcePreviewRepresentation['stage']>('raw');
  const [representations, setRepresentations] = useState<Page<SourcePreviewRepresentation> | null>(
    null,
  );
  const [inspectionBusy, setInspectionBusy] = useState(false);
  const [inspectionError, setInspectionError] = useState('');
  const selectedItem = page.items.find((item) => item.ordinal === selectedOrdinal);

  useEffect(() => {
    if (selectedOrdinal === null || preview.status === 'expired') {
      return;
    }
    let current = true;
    setInspectionBusy(true);
    setInspectionError('');
    api
      .listSourcePreviewRepresentations(projectId, preview.id, selectedOrdinal, stage)
      .then((result) => {
        if (current) {
          setRepresentations(result);
        }
      })
      .catch((reason: Error) => {
        if (current) {
          setInspectionError(reason.message);
        }
      })
      .finally(() => {
        if (current) {
          setInspectionBusy(false);
        }
      });
    return () => {
      current = false;
    };
  }, [projectId, preview.id, preview.status, selectedOrdinal, stage]);

  async function pageRepresentations(offset: number) {
    if (selectedOrdinal === null) {
      return;
    }
    setInspectionBusy(true);
    setInspectionError('');
    try {
      setRepresentations(
        await api.listSourcePreviewRepresentations(
          projectId,
          preview.id,
          selectedOrdinal,
          stage,
          offset,
        ),
      );
    } catch (reason) {
      setInspectionError((reason as Error).message);
    } finally {
      setInspectionBusy(false);
    }
  }

  return (
    <section id="ingestion-preview" className={SECTION} aria-live="polite">
      <div className={HEADING_ROW}>
        <div className={HEADING_COPY}>
          <p className={META}>Processing preview</p>
          <a
            className={LINK}
            href={docsHref('ingestion/previews')}
            target="_blank"
            rel="noopener noreferrer"
          >
            Preview and stage guide
          </a>
          <h2>
            {preview.included_count} included · {preview.excluded_count} excluded
          </h2>
          <p>
            {preview.status} · {preview.progress}% · {preview.duplicate_count} duplicate ·{' '}
            {preview.failed_count} failed
          </p>
          <p>
            Quality: {preview.pass_count} pass · {preview.warn_count} warn · {preview.exclude_count}{' '}
            exclude · {preview.quality_fail_count} fail
          </p>
          <a
            className={LINK}
            href={docsHref('ingestion/quality')}
            target="_blank"
            rel="noopener noreferrer"
          >
            Interpret quality findings
          </a>
          <small>
            {preview.fetch_mode.replace('-', ' ')} · exact config{' '}
            {preview.configuration_hash.slice(0, 12)} · {preview.known_compute_ms} ms known local
            compute · monetary cost unknown
          </small>
          <FetchLimits policies={preview.fetch_policies} />
          {preview.protected_content && (
            <small>
              Sensitive-data policy active · protected stages require owner or admin access
            </small>
          )}
        </div>
        {!terminalIngestionStatuses.has(preview.status) && (
          <Button variant="outline" onClick={onCancel}>
            <Square size={14} />
            Cancel preview
          </Button>
        )}
        {terminalIngestionStatuses.has(preview.status) && preview.status !== 'succeeded' && (
          <Button variant="outline" onClick={onRetry}>
            Retry preview
          </Button>
        )}
      </div>
      {preview.error && (
        <p role="alert" className={ERROR_TEXT}>
          {preview.error}
        </p>
      )}
      <ul className={LIST}>
        {page.items.map((item) => (
          <li key={`${item.source_node_id}-${item.ordinal}`} className={ITEM}>
            {item.status === 'included' ? <Check aria-hidden="true" /> : <X aria-hidden="true" />}
            <div>
              <strong>{item.display_name}</strong>
              <p>
                {item.status} · {item.reason}
                {item.depth !== null ? ` · depth ${item.depth}` : ''}
                {item.size_bytes !== null ? ` · ${item.size_bytes} bytes` : ''}
                {(item.attempts ?? 0) > 1 ? ` · ${item.attempts} attempts` : ''}
              </p>
              {item.canonical_location && <small>{item.canonical_location}</small>}
              {item.provider_revision && <small>Provider revision: {item.provider_revision}</small>}
              <small>
                {item.fetch_mode.replace('-', ' ')} · processing {item.processing_status}
                {item.quality_decision ? ` · quality ${item.quality_decision}` : ''}
              </small>
              {previewLanguage(item.metrics) && (
                <small>Language {previewLanguage(item.metrics)} · no translation</small>
              )}
              {item.duplicate_decision && (
                <small>
                  Duplicate decision {item.duplicate_decision.outcome} ·{' '}
                  {item.duplicate_decision.method} · retained{' '}
                  {item.duplicate_decision.retained_identity}
                </small>
              )}
              {Object.keys(item.stage_timings).length > 0 && (
                <small>
                  Extract {item.stage_timings.extract_ms ?? 0} ms · clean{' '}
                  {item.stage_timings.clean_ms ?? 0} ms · chunk {item.stage_timings.chunk_ms ?? 0}{' '}
                  ms
                </small>
              )}
              {item.findings.map((finding, findingIndex) => (
                <small key={`${finding.code ?? finding.entity_class}-${findingIndex}`}>
                  {finding.entity_class
                    ? `${finding.action} · ${finding.entity_class.replaceAll('_', ' ')} · ${finding.detector_version ?? 'detector version unavailable'} · block ${
                        (finding.block_ordinal ?? 0) + 1
                      }${finding.page_number ? ` · page ${finding.page_number}` : ''}`
                    : `${finding.severity} · ${finding.message}`}
                  {finding.remediation ? ` ${finding.remediation}` : ''}
                </small>
              ))}
            </div>
            {item.processing_status !== 'skipped' && preview.status !== 'expired' && (
              <Button
                variant="outline"
                size="sm"
                aria-pressed={selectedOrdinal === item.ordinal}
                onClick={() => {
                  setSelectedOrdinal(item.ordinal);
                  setStage('raw');
                  setRepresentations(null);
                }}
              >
                Inspect stages
              </Button>
            )}
          </li>
        ))}
      </ul>
      {selectedItem && (
        <section className={INSPECTOR} aria-busy={inspectionBusy}>
          <div className={HEADING_ROW}>
            <div className={HEADING_COPY}>
              <p className={META}>Exact processing preview</p>
              <h3>{selectedItem.display_name}</h3>
            </div>
            <div className="flex flex-wrap gap-1" role="tablist" aria-label="Preview stage">
              {(['raw', 'extracted', 'cleaned', 'diff', 'chunks'] as const).map((value) => (
                <Button
                  key={value}
                  role="tab"
                  size="sm"
                  variant="outline"
                  className={TAB}
                  aria-selected={stage === value}
                  onClick={() => {
                    setStage(value);
                    setRepresentations(null);
                  }}
                >
                  {value === 'diff' ? 'Changes' : value.slice(0, 1).toUpperCase() + value.slice(1)}
                </Button>
              ))}
            </div>
          </div>
          {inspectionError && (
            <p role="alert" className={ERROR_TEXT}>
              {inspectionError}
            </p>
          )}
          {!inspectionBusy && representations?.total === 0 && (
            <p>No {stage} preview records are available for this item.</p>
          )}
          <ol className={RECORDS}>
            {representations?.items.map((item) => (
              <li key={`${item.stage}-${item.ordinal}`}>
                <div>
                  <strong>
                    {item.ordinal + 1}. {item.block_type}
                  </strong>
                  {item.metadata.text_truncated === true && <small>Bounded preview text</small>}
                </div>
                {stage === 'diff' && typeof item.metadata.before_text === 'string' && (
                  <section aria-label={`Preview record ${item.ordinal + 1} before`}>
                    <small>Before · {String(item.metadata.action)}</small>
                    <pre className={PRE}>{item.metadata.before_text}</pre>
                  </section>
                )}
                <section aria-label={`Preview record ${item.ordinal + 1} ${stage}`}>
                  <small>{stage === 'diff' ? 'After' : stage}</small>
                  <pre className={PRE}>{item.text || 'Binary artifact metadata only'}</pre>
                </section>
                {stage === 'chunks' && typeof item.metadata.embedding_prefix === 'string' && (
                  <small>
                    {item.metadata.token_count == null
                      ? 'Legacy size'
                      : `${String(item.metadata.token_count)} tokens`}
                    {item.metadata.parent_ordinal == null
                      ? ''
                      : ` · parent ${Number(item.metadata.parent_ordinal) + 1}`}
                  </small>
                )}
              </li>
            ))}
          </ol>
          {representations && (
            <Pagination
              offset={representations.offset}
              total={representations.total}
              pageSize={representations.limit}
              busy={inspectionBusy}
              label={`${stage} preview pages`}
              onChange={pageRepresentations}
            />
          )}
        </section>
      )}
      {terminalIngestionStatuses.has(preview.status) && page.total === 0 && (
        <p>No preview items were discovered.</p>
      )}
      <Pagination
        offset={page.offset}
        total={page.total}
        pageSize={page.limit}
        busy={busy}
        label="Source preview pages"
        onChange={onPageChange}
      />
    </section>
  );
}

export function IngestionRunResults({
  projectId,
  run,
  items,
}: {
  projectId: string;
  run: IngestionRun;
  items: IngestionRunItem[];
}) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [derivations, setDerivations] = useState<ContentDerivation[]>([]);
  const [kind, setKind] = useState<'extracted' | 'cleaned' | 'diff' | 'chunks'>('extracted');
  const [blocks, setBlocks] = useState<Page<ContentBlock> | null>(null);
  const [diff, setDiff] = useState<Page<CleaningDiff> | null>(null);
  const [chunks, setChunks] = useState<ChunkInspectionPage | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<number | null>(null);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }
    let current = true;
    setBusy(true);
    setError(null);
    setBlocks(null);
    setDiff(null);
    setChunks(null);
    setSelectedPage(null);
    setSelectedBlockId(null);
    api
      .listContentDerivations(projectId, selectedRunId)
      .then((result) => {
        if (current) {
          setDerivations(result.items);
        }
      })
      .catch((reason: Error) => {
        if (current) {
          setError(reason.message);
        }
      })
      .finally(() => {
        if (current) {
          setBusy(false);
        }
      });
    return () => {
      current = false;
    };
  }, [projectId, selectedRunId]);

  const selectedDerivation = derivations.find((item) => item.kind === kind) ?? null;

  useEffect(() => {
    if (!selectedDerivation) {
      return;
    }
    let current = true;
    setBusy(true);
    setError(null);
    api
      .listContentBlocks(projectId, selectedDerivation.id)
      .then((result) => {
        if (current) {
          setBlocks(result);
          setError(null);
        }
      })
      .catch((reason: Error) => {
        if (current) {
          setError(reason.message);
        }
      })
      .finally(() => {
        if (current) {
          setBusy(false);
        }
      });
    return () => {
      current = false;
    };
  }, [projectId, selectedDerivation]);

  useEffect(() => {
    if (!selectedRunId || kind !== 'diff') {
      return;
    }
    let current = true;
    setBusy(true);
    setError(null);
    api
      .listCleaningDiff(projectId, selectedRunId)
      .then((result) => {
        if (current) {
          setDiff(result);
        }
      })
      .catch((reason: Error) => {
        if (current) {
          setError(reason.message);
        }
      })
      .finally(() => {
        if (current) {
          setBusy(false);
        }
      });
    return () => {
      current = false;
    };
  }, [kind, projectId, selectedRunId]);

  useEffect(() => {
    if (!selectedRunId || kind !== 'chunks') {
      return;
    }
    let current = true;
    setBusy(true);
    setError(null);
    api
      .listProcessingChunks(projectId, selectedRunId)
      .then((result) => {
        if (current) {
          setChunks(result);
        }
      })
      .catch((reason: Error) => {
        if (current) {
          setError(reason.message);
        }
      })
      .finally(() => {
        if (current) {
          setBusy(false);
        }
      });
    return () => {
      current = false;
    };
  }, [kind, projectId, selectedRunId]);

  const visiblePages = selectedDerivation?.pages.length
    ? selectedDerivation.pages.map((page) => page.page_number)
    : Array.from(
        new Set(
          blocks?.items.flatMap((block) => (block.page_number ? [block.page_number] : [])) ?? [],
        ),
      ).sort((left, right) => left - right);
  const previewPage = selectedPage ?? visiblePages[0] ?? null;
  const pageDetail = selectedDerivation?.pages.find((page) => page.page_number === previewPage);

  function processingRunId(item: IngestionRunItem) {
    return item.processing_run_id;
  }

  async function pageBlocks(offset: number) {
    if (!selectedDerivation) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setBlocks(await api.listContentBlocks(projectId, selectedDerivation.id, offset));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function pageDiff(offset: number) {
    if (!selectedRunId) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setDiff(await api.listCleaningDiff(projectId, selectedRunId, offset));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function pageChunks(offset: number) {
    if (!selectedRunId) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setChunks(await api.listProcessingChunks(projectId, selectedRunId, offset));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={SECTION} aria-labelledby="ingestion-run-details-heading">
      <div className={HEADING_ROW}>
        <div className={HEADING_COPY}>
          <h2 id="ingestion-run-details-heading">Run details</h2>
          <FetchLimits policies={run.fetch_policies} />
        </div>
        <div className="flex flex-wrap gap-x-4">
          <a
            className={LINK}
            href={docsHref('ingestion/runs')}
            target="_blank"
            rel="noopener noreferrer"
          >
            Run and failure guide
          </a>
          <a
            className={LINK}
            href={docsHref('operate/operations')}
            target="_blank"
            rel="noopener noreferrer"
          >
            Jobs and recovery
          </a>
          {run.source_snapshot_id && (
            <a
              className={LINK}
              href={`#/projects/${projectId}/knowledge-base?view=indexes&mode=snapshots&snapshot=${run.source_snapshot_id}`}
            >
              Inspect source snapshot
            </a>
          )}
        </div>
      </div>
      {(run.source_outcomes?.length ?? 0) > 0 && (
        <section aria-labelledby="run-sources-heading" className="flex flex-col gap-2">
          <h3 id="run-sources-heading" className="text-sm font-semibold text-foreground">
            Sources
          </h3>
          <ul className={LIST}>
            {run.source_outcomes?.map((outcome, index) => (
              <li key={outcome.source_node_id} className={ITEM}>
                <FileText aria-hidden="true" />
                <div>
                  <strong>
                    Website {index + 1} ·{' '}
                    {outcome.status === 'failed'
                      ? 'Failed'
                      : outcome.status === 'partial'
                        ? 'Some pages failed'
                        : outcome.status === 'skipped'
                          ? 'Not refreshed'
                          : 'Collected'}
                  </strong>
                  <p>
                    {outcome.included_count} included · {outcome.failed_count} failed ·{' '}
                    {outcome.carried_forward_count} kept from earlier
                    {outcome.message ? ` · ${outcome.message}` : ''}
                  </p>
                  {outcome.location && <small>{outcome.location}</small>}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
      <ul className={LIST}>
        {/* Failed items lead, so the reason a run failed is the first thing in the list. */}
        {[...items]
          .sort(
            (left, right) => Number(right.status === 'failed') - Number(left.status === 'failed'),
          )
          .map((item) => (
            <li
              key={item.source_kind !== 'existing_files' ? item.ordinal : item.document_id}
              className={ITEM}
            >
              <FileText aria-hidden="true" />
              <div>
                {item.source_kind !== 'existing_files' ? (
                  <>
                    <strong>{item.display_name}</strong>
                    <p>
                      {item.outcome === 'carried_forward' ? 'kept from earlier' : item.outcome} ·{' '}
                      {item.status} · {item.chunk_count} chunks · {item.reason}
                      {(item.attempts ?? 0) > 1 ? ` · ${item.attempts} attempts` : ''}
                    </p>
                    {item.warnings?.map((warning, index) => (
                      <small key={`${warning.code}-${index}`}>
                        {warning.severity} · {warning.message}
                        {warning.remediation ? ` ${warning.remediation}` : ''}
                      </small>
                    ))}
                    {item.canonical_location && <small>{item.canonical_location}</small>}
                    {item.processing_versions && (
                      <small>
                        Extractor {item.processing_versions.extractor} · cleaner{' '}
                        {item.processing_versions.cleaner} · chunker{' '}
                        {item.processing_versions.chunker}
                      </small>
                    )}
                    {item.duplicate_decision && (
                      <small>
                        Duplicate {item.duplicate_decision.outcome} ·{' '}
                        {item.duplicate_decision.method}
                        {' · '}retained {item.duplicate_decision.retained_identity}
                      </small>
                    )}
                    {item.error && (
                      <small role="alert" className={ERROR_TEXT}>
                        {item.error}
                      </small>
                    )}
                  </>
                ) : (
                  <>
                    <strong>{item.filename}</strong>
                    <p>
                      {item.status} · processing v{item.processing_version} · {item.chunk_count}{' '}
                      chunks · {item.content_hash.slice(0, 12)}
                    </p>
                    {item.is_optional && <small>Optional source</small>}
                    {item.processing_versions && (
                      <small>
                        Extractor {item.processing_versions.extractor} · cleaner{' '}
                        {item.processing_versions.cleaner} · chunker{' '}
                        {item.processing_versions.chunker}
                      </small>
                    )}
                    {item.duplicate_decision && (
                      <small>
                        Duplicate {item.duplicate_decision.outcome} ·{' '}
                        {item.duplicate_decision.method}
                        {' · '}retained {item.duplicate_decision.retained_identity}
                      </small>
                    )}
                    {item.error && (
                      <small role="alert" className={ERROR_TEXT}>
                        {item.error}
                      </small>
                    )}
                  </>
                )}
              </div>
              {processingRunId(item) && (
                <Button
                  variant="outline"
                  size="sm"
                  aria-pressed={selectedRunId === processingRunId(item)}
                  onClick={() => {
                    setDerivations([]);
                    setKind('extracted');
                    setSelectedRunId(processingRunId(item));
                  }}
                >
                  Inspect content
                </Button>
              )}
            </li>
          ))}
      </ul>
      {selectedRunId && (
        <section className={INSPECTOR} aria-busy={busy}>
          <div className={HEADING_ROW}>
            <div className={HEADING_COPY}>
              <p className={META}>Canonical processing record</p>
              <h3>Extracted and cleaned content</h3>
            </div>
            <div className="flex flex-wrap gap-1" role="tablist" aria-label="Content stage">
              {(['extracted', 'cleaned', 'diff', 'chunks'] as const).map((value) => (
                <Button
                  key={value}
                  role="tab"
                  size="sm"
                  variant="outline"
                  className={TAB}
                  aria-selected={kind === value}
                  onClick={() => {
                    setKind(value);
                    setBlocks(null);
                    setDiff(null);
                    setChunks(null);
                  }}
                >
                  {value === 'extracted'
                    ? 'Extracted'
                    : value === 'cleaned'
                      ? 'Cleaned'
                      : value === 'diff'
                        ? 'Changes'
                        : 'Chunks'}
                </Button>
              ))}
            </div>
          </div>
          {error && (
            <p role="alert" className={ERROR_TEXT}>
              {error}
            </p>
          )}
          {!busy && derivations.length === 0 && !error && (
            <p>
              {items.find((item) => processingRunId(item) === selectedRunId)?.status === 'failed'
                ? 'Canonical content is unavailable because processing failed before it could be saved.'
                : 'Canonical content is unavailable for this legacy processing version.'}
            </p>
          )}
          {selectedDerivation && (
            <>
              <p>
                {selectedDerivation.measurements.block_count} blocks ·{' '}
                {selectedDerivation.measurements.character_count} characters · engine{' '}
                {selectedDerivation.engine_version}
              </p>
              <dl className={QUALITY}>
                <dt>Quality decision</dt>
                <dd>{selectedDerivation.measurements.quality_decision ?? 'not recorded'}</dd>
                <dt>Language</dt>
                <dd>
                  {selectedDerivation.language
                    ? `${selectedDerivation.language.language} · ${Math.round(selectedDerivation.language.confidence * 100)}% · ${selectedDerivation.language.model_version}${selectedDerivation.language.mixed ? ' · mixed' : ''}`
                    : 'not recorded'}
                </dd>
                <dt>Page origins</dt>
                <dd>
                  {selectedDerivation.measurements.native_page_count ?? 0} Native ·{' '}
                  {selectedDerivation.measurements.layout_page_count ?? 0} Layout ·{' '}
                  {selectedDerivation.measurements.ocr_page_count ?? 0} OCR
                </dd>
                <dt>Tables</dt>
                <dd>{selectedDerivation.measurements.table_count ?? 0}</dd>
                <dt>Extraction time</dt>
                <dd>{selectedDerivation.measurements.extraction_duration_ms ?? 0} ms</dd>
              </dl>
              {selectedDerivation.findings.length > 0 && (
                <ul className={RECORDS} aria-label="Extraction findings">
                  {selectedDerivation.findings.map((finding) => (
                    <li key={`${finding.code}-${finding.page_numbers?.join('-') ?? 'document'}`}>
                      <strong>
                        {finding.severity} · {finding.code.replaceAll('_', ' ')}
                      </strong>
                      <span>
                        {finding.message}
                        {finding.page_numbers?.length
                          ? ` Pages ${finding.page_numbers.join(', ')}.`
                          : ''}
                      </span>
                      {finding.remediation && <small>{finding.remediation}</small>}
                    </li>
                  ))}
                </ul>
              )}
              {(selectedDerivation.sensitive_findings?.length ?? 0) > 0 && (
                <ul className={RECORDS} aria-label="Sensitive-data findings">
                  {selectedDerivation.sensitive_findings?.map((finding, index) => (
                    <li
                      key={`${finding.entity_class}-${finding.block_ordinal}-${finding.start_char}-${index}`}
                    >
                      <strong>
                        {finding.action} · {finding.entity_class.replaceAll('_', ' ')}
                      </strong>
                      <span>
                        {finding.detector_version} · block {finding.block_ordinal + 1}
                        {finding.page_number ? ` · page ${finding.page_number}` : ''} · location{' '}
                        {finding.start_char}–{finding.end_char}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {kind === 'cleaned' && selectedDerivation.transforms.length > 0 && (
                <>
                  <dl className={QUALITY}>
                    <dt>Repeated margins removed</dt>
                    <dd>
                      {selectedDerivation.transforms.find(
                        (item) => item.transform === 'remove_repeated_headers_footers',
                      )?.removed_blocks ?? 0}
                    </dd>
                    <dt>Lines joined</dt>
                    <dd>
                      {transformMetric(selectedDerivation, 'reflow_pdf_lines', 'change_count')}
                    </dd>
                    <dt>Words dehyphenated</dt>
                    <dd>{transformMetric(selectedDerivation, 'dehyphenate', 'change_count')}</dd>
                    <dt>Protected blocks retained</dt>
                    <dd>
                      {transformMetric(
                        selectedDerivation,
                        'remove_empty_blocks',
                        'protected_blocks_retained',
                      )}
                    </dd>
                  </dl>
                  <ol className={RECORDS} aria-label="Cleaning transform audit">
                    {selectedDerivation.transforms.map((transform, index) => (
                      <li key={`${transform.transform}-${index}`}>
                        <strong>
                          {index + 1}. {transform.transform.replaceAll('_', ' ')}
                        </strong>
                        <span>
                          {transform.changed_blocks} changed · {transform.removed_blocks} removed ·{' '}
                          {transform.duration_ms ?? 0} ms
                        </span>
                        {typeof transform.metrics?.protected_blocks_retained === 'number' && (
                          <small>
                            {transform.metrics.protected_blocks_retained} protected blocks retained
                          </small>
                        )}
                      </li>
                    ))}
                  </ol>
                </>
              )}
              {kind === 'extracted' &&
                selectedDerivation.media_type === 'application/pdf' &&
                previewPage && (
                  <div className="grid gap-4 desktop:grid-cols-3">
                    <Label>
                      Preview page
                      <NativeSelect
                        value={previewPage}
                        onChange={(event) => {
                          setSelectedPage(Number(event.target.value));
                          setSelectedBlockId(null);
                        }}
                      >
                        {visiblePages.map((page) => (
                          <NativeSelectOption key={page} value={page}>
                            Page {page}
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                    </Label>
                    {pageDetail && (
                      <dl className={QUALITY}>
                        <dt>Page origin</dt>
                        <dd>{pageDetail.origin.toUpperCase()}</dd>
                        <dt>Fallback reason</dt>
                        <dd>{pageDetail.fallback_reason?.replaceAll('_', ' ') ?? 'None'}</dd>
                        <dt>Rotation</dt>
                        <dd>{pageDetail.rotation_degrees}° applied</dd>
                        <dt>OCR engine confidence</dt>
                        <dd>
                          {pageDetail.ocr_confidence === null
                            ? 'Not reported'
                            : `${pageDetail.ocr_confidence.toFixed(1)} / 100`}
                        </dd>
                      </dl>
                    )}
                    <figure className="m-0 flex min-w-0 flex-col gap-2 desktop:col-span-2">
                      <div className="relative w-full overflow-hidden rounded-card border border-border bg-background">
                        <img
                          className="block h-auto w-full"
                          src={api.contentPageThumbnailUrl(projectId, selectedRunId, previewPage)}
                          alt={`Rendered PDF page ${previewPage}`}
                        />
                        <div className="absolute inset-0" aria-label="Extracted block overlays">
                          {blocks?.items
                            .filter(
                              (block) =>
                                block.page_number === previewPage &&
                                overlayStyle(block) !== undefined,
                            )
                            .map((block) => (
                              <Button
                                type="button"
                                variant="ghost"
                                key={block.block_id}
                                style={overlayStyle(block)}
                                aria-pressed={selectedBlockId === block.block_id}
                                className="absolute top-(--box-top) left-(--box-left) h-(--box-height) w-(--box-width) rounded-none border border-accent p-0 not-aria-disabled:hover:bg-accent/30 aria-pressed:border-2 aria-pressed:bg-accent/30 pointer-coarse:h-(--box-height)"
                                aria-label={`Select ${blockOrigin(block) ?? ''} ${block.block_type} block ${block.ordinal + 1}`}
                                onClick={() => setSelectedBlockId(block.block_id)}
                              />
                            ))}
                        </div>
                      </div>
                      <figcaption className={META}>
                        Select an overlay to match normalized geometry with the extracted block.
                      </figcaption>
                    </figure>
                  </div>
                )}
              <ul className={RECORDS}>
                {blocks?.items.map((block) => (
                  <li key={block.block_id} data-selected={selectedBlockId === block.block_id}>
                    <div>
                      <strong>
                        {block.ordinal + 1}. {block.block_type}
                        {block.page_number ? ` · page ${block.page_number}` : ''}
                        {blockOrigin(block) ? ` · ${blockOrigin(block)}` : ''}
                      </strong>
                      {block.heading_path.length > 0 && (
                        <small>{block.heading_path.join(' / ')}</small>
                      )}
                      <small>Source: {sourceSpanLabel(block.source_span)}</small>
                    </div>
                    <pre className={PRE}>{block.text}</pre>
                    {tableRows(block) && (
                      <div
                        className="overflow-x-auto rounded-control border border-border"
                        tabIndex={0}
                        role="region"
                        aria-label={`Table cells for block ${block.ordinal + 1}`}
                      >
                        <table className="w-full border-collapse text-xs [&_td]:border-t [&_td]:border-border [&_td]:p-2 [&_td]:align-top [&_th]:p-2 [&_th]:text-left [&_th]:font-medium">
                          <caption className="p-2 text-left text-foreground-muted">
                            Structured table cells for block {block.ordinal + 1}
                          </caption>
                          <thead>
                            <tr>
                              {tableRows(block)?.[0].map((cell, index) => (
                                <th key={`${block.block_id}-head-${index}`} scope="col">
                                  {cell || `Column ${index + 1}`}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {tableRows(block)
                              ?.slice(1)
                              .map((row, rowIndex) => (
                                <tr key={`${block.block_id}-row-${rowIndex}`}>
                                  {row.map((cell, columnIndex) => (
                                    <td key={`${block.block_id}-${rowIndex}-${columnIndex}`}>
                                      {cell}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
              {blocks?.total === 0 && <p>This derivation contains no text blocks.</p>}
              {blocks && (
                <Pagination
                  offset={blocks.offset}
                  total={blocks.total}
                  pageSize={blocks.limit}
                  busy={busy}
                  label={`${kind} content pages`}
                  onChange={pageBlocks}
                />
              )}
            </>
          )}
          {kind === 'diff' && diff && (
            <>
              <p>
                {diff.items.filter((item) => item.action !== 'unchanged').length} changed or removed
                blocks on this page · reconstructed from immutable derivations
              </p>
              <ol className={RECORDS}>
                {diff.items.map((item) => (
                  <li key={item.block_id}>
                    <div>
                      <strong>
                        {item.block_type}
                        {item.page_number ? ` · page ${item.page_number}` : ''}
                      </strong>
                      <span>{item.action}</span>
                    </div>
                    <div className="grid gap-4 md:grid-cols-2">
                      <section aria-label="Before cleaning">
                        <small>Before</small>
                        <pre className={PRE}>{item.before_text}</pre>
                      </section>
                      <section aria-label="After cleaning">
                        <small>After</small>
                        <pre className={PRE}>{item.after_text ?? 'Removed'}</pre>
                      </section>
                    </div>
                    <small>
                      {item.transforms.length
                        ? `${item.transforms.join(' → ')} · ${item.reasons.join(', ')}`
                        : 'No text change'}
                    </small>
                  </li>
                ))}
              </ol>
              {diff.total === 0 && (
                <p>Cleaning changes are unavailable for this legacy processing version.</p>
              )}
              <Pagination
                offset={diff.offset}
                total={diff.total}
                pageSize={diff.limit}
                busy={busy}
                label="Cleaning diff pages"
                onChange={pageDiff}
              />
            </>
          )}
          {kind === 'chunks' && chunks && (
            <>
              <dl className={QUALITY}>
                <dt>Indexed chunks</dt>
                <dd>{chunks.summary.indexed_count}</dd>
                <dt>Saved parents</dt>
                <dd>{chunks.summary.parent_count}</dd>
                <dt>Token distribution</dt>
                <dd>
                  {chunks.summary.minimum ?? '—'} min · {chunks.summary.median ?? '—'} median ·{' '}
                  {chunks.summary.p95 ?? '—'} p95 · {chunks.summary.maximum ?? '—'} max
                </dd>
                <dt>Oversize findings</dt>
                <dd>{chunks.summary.oversize_finding_count}</dd>
              </dl>
              <ol className={RECORDS}>
                {chunks.items.map((chunk) => (
                  <li key={chunk.ordinal}>
                    <div>
                      <strong>
                        Chunk {chunk.ordinal + 1} · {chunk.chunk_role} ·{' '}
                        {chunk.token_count ?? 'legacy'} tokens
                      </strong>
                      {chunk.parent_ordinal !== null && (
                        <small>Supplies saved parent {chunk.parent_ordinal + 1}</small>
                      )}
                      {chunk.section_path.length > 0 && (
                        <small>{chunk.section_path.join(' / ')}</small>
                      )}
                      <small>
                        {chunk.spans.length} source span{chunk.spans.length === 1 ? '' : 's'}
                        {chunk.page_number ? ` · page ${chunk.page_number}` : ''}
                      </small>
                    </div>
                    <section aria-label={`Chunk ${chunk.ordinal + 1} evidence text`}>
                      <small>Evidence text</small>
                      <pre className={PRE}>{chunk.evidence_text}</pre>
                    </section>
                    {chunk.embedding_prefix && (
                      <section aria-label={`Chunk ${chunk.ordinal + 1} embedding prefix`}>
                        <small>
                          Embedding-only prefix · {chunk.embedding_token_count ?? 'unknown'} total
                          tokens
                        </small>
                        <pre className={PRE}>{chunk.embedding_prefix}</pre>
                      </section>
                    )}
                    {chunk.findings.length > 0 && (
                      <ul className={RECORDS}>
                        {chunk.findings.map((finding, index) => (
                          <li key={`${finding.code}-${index}`}>
                            <strong>{finding.code.replaceAll('_', ' ')}</strong>
                            <span>{finding.message}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ol>
              {chunks.total === 0 && <p>This processing version contains no chunks.</p>}
              <Pagination
                offset={chunks.offset}
                total={chunks.total}
                pageSize={chunks.limit}
                busy={busy}
                label="Chunk inspector pages"
                onChange={pageChunks}
              />
            </>
          )}
        </section>
      )}
    </section>
  );
}
