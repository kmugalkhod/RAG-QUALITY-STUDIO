import { useEffect, useState } from 'react';
import { ArrowRight, Check, FileText, Square, X } from 'lucide-react';

import { Pagination } from '../../../components/Pagination';
import { Button } from '../../../components/ui/button';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import type { Page } from '../../../lib/pagination';
import { terminalIngestionStatuses } from '../editorModel';
import * as api from '../api';
import type {
  ContentBlock,
  ContentDerivation,
  CleaningDiff,
  IngestionRun,
  IngestionRunItem,
  SourcePreview,
  SourcePreviewItem,
} from '../model';

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
    left: `${box.left * 100}%`,
    top: `${box.top * 100}%`,
    width: `${(box.right - box.left) * 100}%`,
    height: `${(box.bottom - box.top) * 100}%`,
  };
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
  preview,
  page,
  busy,
  onCancel,
  onPageChange,
}: {
  preview: SourcePreview;
  page: Page<SourcePreviewItem>;
  busy: boolean;
  onCancel: () => void;
  onPageChange: (offset: number) => void;
}) {
  return (
    <section
      id="ingestion-preview"
      className="surface-section ingestion-results"
      aria-live="polite"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Source preview</p>
          <h2>
            {preview.included_count} included · {preview.excluded_count} excluded
          </h2>
          <p>
            {preview.status} · {preview.progress}% · {preview.duplicate_count} duplicate ·{' '}
            {preview.failed_count} failed
          </p>
        </div>
        {!terminalIngestionStatuses.has(preview.status) && (
          <Button variant="outline" onClick={onCancel}>
            <Square size={14} />
            Cancel preview
          </Button>
        )}
      </div>
      {preview.error && (
        <p role="alert" className="error-message">
          {preview.error}
        </p>
      )}
      <ul className="project-list">
        {page.items.map((item) => (
          <li key={`${item.source_node_id}-${item.ordinal}`}>
            {item.status === 'included' ? <Check size={18} /> : <X size={18} />}
            <div>
              <strong>{item.display_name}</strong>
              <p>
                {item.status} · {item.reason}
                {item.depth !== null ? ` · depth ${item.depth}` : ''}
                {item.size_bytes !== null ? ` · ${item.size_bytes} bytes` : ''}
              </p>
              {item.canonical_location && <small>{item.canonical_location}</small>}
              {item.provider_revision && <small>Provider revision: {item.provider_revision}</small>}
            </div>
          </li>
        ))}
      </ul>
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
  const [kind, setKind] = useState<'extracted' | 'cleaned' | 'diff'>('extracted');
  const [blocks, setBlocks] = useState<Page<ContentBlock> | null>(null);
  const [diff, setDiff] = useState<Page<CleaningDiff> | null>(null);
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
    api
      .listContentBlocks(projectId, selectedDerivation.id)
      .then((result) => {
        if (current) {
          setBlocks(result);
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

  const visiblePages = Array.from(
    new Set(blocks?.items.flatMap((block) => (block.page_number ? [block.page_number] : [])) ?? []),
  ).sort((left, right) => left - right);
  const previewPage = selectedPage ?? visiblePages[0] ?? null;

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

  return (
    <section
      className="surface-section ingestion-results ingestion-run-details"
      aria-labelledby="ingestion-run-details-heading"
    >
      <div className="section-heading">
        <div>
          <h2 id="ingestion-run-details-heading">Run details</h2>
          {(run.new_count > 0 ||
            run.changed_count > 0 ||
            run.unchanged_count > 0 ||
            run.removed_count > 0) && (
            <p>
              {run.new_count} new · {run.changed_count} changed · {run.unchanged_count} unchanged ·{' '}
              {run.removed_count} removed
            </p>
          )}
        </div>
      </div>
      {run.error && (
        <p role="alert" className="error-message">
          {run.error}
        </p>
      )}
      {run.status === 'succeeded' && run.published_index_id && (
        <div className="ingestion-published-index">
          <div>
            <strong>Index version {run.published_index_version} is ready to use</strong>
            <p>
              Select this same version in an answer pipeline. It will not ingest the source or embed
              these passages again.
            </p>
          </div>
          <div className="ingestion-published-index-actions">
            <Button asChild>
              <a href={`#/projects/${projectId}/pipelines/new?index=${run.published_index_id}`}>
                Use in answer pipeline
                <ArrowRight size={15} aria-hidden="true" />
              </a>
            </Button>
            <Button asChild variant="outline">
              <a
                href={`#/projects/${projectId}/knowledge-base?view=indexes&index=${run.published_index_id}`}
              >
                Inspect published index
              </a>
            </Button>
            {run.source_snapshot_id && (
              <Button asChild variant="ghost">
                <a
                  href={`#/projects/${projectId}/knowledge-base?view=indexes&mode=snapshots&snapshot=${run.source_snapshot_id}`}
                >
                  Inspect source snapshot
                </a>
              </Button>
            )}
          </div>
        </div>
      )}
      <ul className="project-list">
        {items.map((item) => (
          <li key={item.source_kind !== 'existing_files' ? item.ordinal : item.document_id}>
            <FileText size={18} />
            <div>
              {item.source_kind !== 'existing_files' ? (
                <>
                  <strong>{item.display_name}</strong>
                  <p>
                    {item.outcome} · {item.status} · {item.chunk_count} chunks · {item.reason}
                  </p>
                  {item.canonical_location && <small>{item.canonical_location}</small>}
                  {item.processing_versions && (
                    <small>
                      Extractor {item.processing_versions.extractor} · cleaner{' '}
                      {item.processing_versions.cleaner} · chunker{' '}
                      {item.processing_versions.chunker}
                    </small>
                  )}
                  {item.error && (
                    <small role="alert" className="error-message">
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
                  {item.processing_versions && (
                    <small>
                      Extractor {item.processing_versions.extractor} · cleaner{' '}
                      {item.processing_versions.cleaner} · chunker{' '}
                      {item.processing_versions.chunker}
                    </small>
                  )}
                  {item.error && (
                    <small role="alert" className="error-message">
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
        <section className="content-derivation-inspector" aria-busy={busy}>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Canonical processing record</p>
              <h3>Extracted and cleaned content</h3>
            </div>
            <div className="content-derivation-tabs" role="tablist" aria-label="Content stage">
              {(['extracted', 'cleaned', 'diff'] as const).map((value) => (
                <Button
                  key={value}
                  role="tab"
                  size="sm"
                  variant={kind === value ? 'default' : 'outline'}
                  aria-selected={kind === value}
                  onClick={() => {
                    setKind(value);
                    setBlocks(null);
                    setDiff(null);
                  }}
                >
                  {value === 'extracted'
                    ? 'Extracted'
                    : value === 'cleaned'
                      ? 'Cleaned'
                      : 'Changes'}
                </Button>
              ))}
            </div>
          </div>
          {error && (
            <p role="alert" className="error-message">
              {error}
            </p>
          )}
          {!busy && derivations.length === 0 && !error && (
            <p>Canonical content is unavailable for this legacy processing version.</p>
          )}
          {selectedDerivation && (
            <>
              <p>
                {selectedDerivation.measurements.block_count} blocks ·{' '}
                {selectedDerivation.measurements.character_count} characters · engine{' '}
                {selectedDerivation.engine_version}
              </p>
              <dl className="ingestion-stage-facts content-quality-summary">
                <dt>Quality decision</dt>
                <dd>{selectedDerivation.measurements.quality_decision ?? 'not recorded'}</dd>
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
                <ul className="content-quality-findings" aria-label="Extraction findings">
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
              {kind === 'cleaned' && selectedDerivation.transforms.length > 0 && (
                <>
                  <dl className="ingestion-stage-facts content-quality-summary">
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
                  <ol className="cleaning-audit-list" aria-label="Cleaning transform audit">
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
                  <div className="content-page-inspector">
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
                    <figure>
                      <div className="content-page-canvas">
                        <img
                          src={api.contentPageThumbnailUrl(projectId, selectedRunId, previewPage)}
                          alt={`Rendered PDF page ${previewPage}`}
                        />
                        <div
                          className="content-page-overlays"
                          aria-label="Extracted block overlays"
                        >
                          {blocks?.items
                            .filter(
                              (block) =>
                                block.page_number === previewPage &&
                                overlayStyle(block) !== undefined,
                            )
                            .map((block) => (
                              <button
                                type="button"
                                key={block.block_id}
                                style={overlayStyle(block)}
                                className={selectedBlockId === block.block_id ? 'is-selected' : ''}
                                aria-label={`Select ${blockOrigin(block) ?? ''} ${block.block_type} block ${block.ordinal + 1}`}
                                onClick={() => setSelectedBlockId(block.block_id)}
                              />
                            ))}
                        </div>
                      </div>
                      <figcaption>
                        Select an overlay to match normalized geometry with the extracted block.
                      </figcaption>
                    </figure>
                  </div>
                )}
              <ul className="content-block-list">
                {blocks?.items.map((block) => (
                  <li
                    key={block.block_id}
                    className={selectedBlockId === block.block_id ? 'is-selected' : ''}
                  >
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
                    <pre>{block.text}</pre>
                    {tableRows(block) && (
                      <div className="content-table-scroll" tabIndex={0}>
                        <table>
                          <caption>Structured table cells for block {block.ordinal + 1}</caption>
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
              <ol className="cleaning-diff-list">
                {diff.items.map((item) => (
                  <li key={item.block_id}>
                    <div className="cleaning-diff-heading">
                      <strong>
                        {item.block_type}
                        {item.page_number ? ` · page ${item.page_number}` : ''}
                      </strong>
                      <span>{item.action}</span>
                    </div>
                    <div className="cleaning-diff-columns">
                      <section aria-label="Before cleaning">
                        <small>Before</small>
                        <pre>{item.before_text}</pre>
                      </section>
                      <section aria-label="After cleaning">
                        <small>After</small>
                        <pre>{item.after_text ?? 'Removed'}</pre>
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
        </section>
      )}
    </section>
  );
}
