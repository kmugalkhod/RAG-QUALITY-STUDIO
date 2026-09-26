import { CircleAlert, Database } from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import type { ConnectionSettings, SourceConnection } from '../../connections/model';
import type { Document, KnowledgeSet } from '../../documents/model';
import {
  defaultDuplicatePolicy,
  defaultLanguagePolicy,
  defaultSensitiveDataPolicy,
  fallbackQualityPolicy,
  ingestionStageLabels as labels,
} from '../editorModel';
import type {
  ExistingFilesConfig,
  ExtractionCapabilities,
  IngestionNode,
  IngestionPipelineVersion,
  QualityPolicy,
  QualityPolicyId,
} from '../model';
import { ConfluenceSettings, NotionSettings, S3Settings, WebsiteSettings } from './SourceSettings';
import { CleaningTransformSettings } from './CleaningTransformSettings';

type SourceKind = 'existing_files' | 'website' | 's3' | 'notion' | 'confluence';

export function IngestionNodeSettings({
  projectId,
  selected,
  selectedNode,
  nodes,
  dirty,
  saved,
  validation,
  serverFieldErrors = {},
  connectionSettings,
  connections,
  documents,
  knowledgeSets,
  websiteSource,
  extractionCapabilities,
  schemaVersion,
  updateNode,
  changeSourceKind,
}: {
  projectId: string;
  selected?: IngestionNode;
  selectedNode: string;
  nodes: IngestionNode[];
  dirty: boolean;
  saved?: IngestionPipelineVersion;
  validation: string[];
  serverFieldErrors?: Record<string, string>;
  connectionSettings?: ConnectionSettings;
  connections: SourceConnection[];
  documents: Document[];
  knowledgeSets: KnowledgeSet[];
  websiteSource: boolean;
  extractionCapabilities?: ExtractionCapabilities;
  schemaVersion: 1 | 2;
  updateNode: (id: string, update: (node: IngestionNode) => IngestionNode) => void;
  changeSourceKind: (nodeId: string, kind: SourceKind) => void;
}) {
  const selectedOcr =
    selected?.type === 'extract'
      ? (selected.ocr ?? {
          mode: 'off' as const,
          languages: ['eng'],
          rotate_pages: true,
          deskew: true,
          dpi: 200,
          max_pages: 50,
          timeout_seconds: 30,
        })
      : null;
  const selectedQualityId: QualityPolicyId =
    selected?.type === 'extract'
      ? typeof selected.quality_policy === 'string'
        ? selected.quality_policy
        : (selected.quality_policy?.id ?? 'default-v1')
      : 'default-v1';
  const selectedQuality: QualityPolicy =
    selected?.type === 'extract' &&
    selected.quality_policy &&
    typeof selected.quality_policy !== 'string'
      ? selected.quality_policy
      : structuredClone(
          extractionCapabilities?.quality_policies.find((value) => value.id === selectedQualityId)
            ?.settings ?? fallbackQualityPolicy(selectedQualityId),
        );
  const selectedLanguage =
    selected?.type === 'extract'
      ? (selected.language_policy ?? structuredClone(defaultLanguagePolicy))
      : structuredClone(defaultLanguagePolicy);
  const selectedDuplicate =
    selected?.type === 'clean'
      ? (selected.duplicate_policy ?? structuredClone(defaultDuplicatePolicy))
      : structuredClone(defaultDuplicatePolicy);
  const selectedSensitive =
    selected?.type === 'clean'
      ? (selected.sensitive_data_policy ?? structuredClone(defaultSensitiveDataPolicy))
      : structuredClone(defaultSensitiveDataPolicy);

  function updateExtract(values: Partial<Extract<IngestionNode, { type: 'extract' }>>) {
    if (selected?.type !== 'extract') {
      return;
    }
    updateNode(selected.id, (node) => (node.type === 'extract' ? { ...node, ...values } : node));
  }

  function selectChunkAlgorithm(algorithm: 'character_window' | 'section_token' | 'parent_child') {
    if (selected?.type !== 'chunk') {
      return;
    }
    const id = selected.id;
    updateNode(id, () => {
      if (algorithm === 'section_token') {
        return {
          id,
          type: 'chunk',
          algorithm,
          unit: 'tokens',
          tokenizer_version: 'utf8-byte-v1',
          target_tokens: 600,
          maximum_tokens: 800,
          overlap_tokens: 80,
          add_heading_context: true,
          config_version: 'section-token-v1',
        };
      }
      if (algorithm === 'parent_child') {
        return {
          id,
          type: 'chunk',
          algorithm,
          unit: 'tokens',
          tokenizer_version: 'utf8-byte-v1',
          child_target_tokens: 240,
          child_maximum_tokens: 320,
          child_overlap_tokens: 40,
          parent_target_tokens: 900,
          parent_maximum_tokens: 1200,
          add_heading_context: true,
          config_version: 'parent-child-v1',
        };
      }
      return {
        id,
        type: 'chunk',
        algorithm,
        unit: 'characters',
        size: 1000,
        overlap: 100,
        config_version: 'character-window-v1',
      };
    });
  }

  return (
    <aside
      id="node-settings"
      className="node-settings"
      aria-labelledby="ingestion-settings-heading"
    >
      <div className="ingestion-settings-header">
        <h2 id="ingestion-settings-heading">
          {selected
            ? `${selected.type === 'source' ? (selected.config.kind === 'website' ? 'Website' : selected.config.kind === 's3' ? 'Amazon S3' : selected.config.kind === 'notion' ? 'Notion' : selected.config.kind === 'confluence' ? 'Confluence' : 'Existing files') : labels[selected.type]} settings`
            : 'Node settings'}
        </h2>
        <p>
          Stage {nodes.findIndex((node) => node.id === selectedNode) + 1} of {nodes.length} ·{' '}
          {dirty
            ? 'Draft configuration'
            : saved
              ? `Version ${saved.version}`
              : 'Draft configuration'}
        </p>
      </div>
      <div
        id="ingestion-settings-body"
        className="ingestion-settings-body"
        tabIndex={0}
        role="region"
        aria-label="Stage settings"
      >
        {validation.length > 0 && (
          <div className="pipeline-validation" role="status">
            <strong>Complete the configuration</strong>
            <ul>
              {validation.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        )}
        {selected?.type === 'source' && (
          <div className="field-stack">
            <Label>
              Source type
              <NativeSelect
                value={selected.config.kind}
                onChange={(event) =>
                  changeSourceKind(
                    selected.id,
                    event.target.value as
                      | 'existing_files'
                      | 'website'
                      | 's3'
                      | 'notion'
                      | 'confluence',
                  )
                }
              >
                <NativeSelectOption value="existing_files">Existing files</NativeSelectOption>
                <NativeSelectOption value="website">Website</NativeSelectOption>
                <NativeSelectOption value="s3">
                  Amazon S3{connectionSettings?.enabled ? '' : ' · setup required'}
                </NativeSelectOption>
                <NativeSelectOption value="notion">
                  Notion{connectionSettings?.enabled ? '' : ' · setup required'}
                </NativeSelectOption>
                <NativeSelectOption value="confluence">
                  Confluence{connectionSettings?.enabled ? '' : ' · setup required'}
                </NativeSelectOption>
              </NativeSelect>
            </Label>
            {!connectionSettings?.enabled && (
              <div className="website-preview-notice" role="note">
                <CircleAlert size={17} aria-hidden="true" />
                <p>
                  Amazon S3, Notion, and Confluence need the local encrypted connection vault.{' '}
                  <a href={`#/projects/${projectId}/settings`}>Review setup in project settings</a>.
                </p>
              </div>
            )}
            {selected.config.kind === 'existing_files' ? (
              <>
                <p className="field-hint">
                  {schemaVersion === 2
                    ? 'Choose explicit project files. The saved extraction settings process new or failed uploads when the run starts.'
                    : 'Choose explicit project files. Legacy pipelines require a successful processing version.'}
                </p>
                {documents.map((document) => {
                  const sourceConfig = selected.config as ExistingFilesConfig;
                  const checked = sourceConfig.document_ids.includes(document.id);
                  const processingActive = ['queued', 'running'].includes(
                    document.latest_run?.status ?? '',
                  );
                  const disabled =
                    processingActive ||
                    (schemaVersion === 1 && document.latest_run?.status !== 'succeeded');
                  const statusCopy = processingActive
                    ? `Processing ${document.latest_run?.status}`
                    : document.latest_run?.status === 'succeeded'
                      ? `${document.latest_run.chunk_count} chunks ready`
                      : schemaVersion === 2
                        ? document.latest_run
                          ? 'Will retry with saved extraction settings'
                          : 'Will process with saved extraction settings'
                        : `Processing ${document.latest_run?.status ?? 'required'}`;
                  return (
                    <div key={document.id}>
                      <label className="ingestion-document-option">
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={disabled}
                        onChange={(event) =>
                          updateNode(selected.id, (node) =>
                            node.type === 'source' && node.config.kind === 'existing_files'
                              ? {
                                  ...node,
                                  config: {
                                    ...node.config,
                                    document_ids: event.target.checked
                                      ? [...node.config.document_ids, document.id]
                                      : node.config.document_ids.filter(
                                          (id: string) => id !== document.id,
                                        ),
                                    optional_document_ids: event.target.checked
                                      ? node.config.optional_document_ids ?? []
                                      : (node.config.optional_document_ids ?? []).filter(
                                          (id: string) => id !== document.id,
                                        ),
                                  },
                                }
                              : node,
                          )
                        }
                      />
                      <span>
                        <strong>{document.filename}</strong>
                        <small>{statusCopy}</small>
                      </span>
                      </label>
                      {schemaVersion === 2 && checked && (
                        <label className="ingestion-document-option">
                        <input
                          type="checkbox"
                          checked={(sourceConfig.optional_document_ids ?? []).includes(document.id)}
                          onChange={(event) =>
                            updateNode(selected.id, (node) =>
                              node.type === 'source' && node.config.kind === 'existing_files'
                                ? {
                                    ...node,
                                    config: {
                                      ...node.config,
                                      optional_document_ids: event.target.checked
                                        ? [...(node.config.optional_document_ids ?? []), document.id]
                                        : (node.config.optional_document_ids ?? []).filter(
                                            (id: string) => id !== document.id,
                                          ),
                                    },
                                  }
                                : node,
                            )
                          }
                        />
                          <span>
                            <strong>Optional source for {document.filename}</strong>
                            <small>
                              Exclude this file after a processing failure only when the saved
                              quality policy permits it.
                            </small>
                          </span>
                        </label>
                      )}
                    </div>
                  );
                })}
                {documents.length === 0 && (
                  <p>No uploaded documents. Add files in Knowledge Base first.</p>
                )}
              </>
            ) : selected.config.kind === 'website' ? (
              <WebsiteSettings
                config={selected.config}
                update={(config) =>
                  updateNode(selected.id, (node) =>
                    node.type === 'source' ? { ...node, config } : node,
                  )
                }
              />
            ) : selected.config.kind === 's3' ? (
              <S3Settings
                config={selected.config}
                connections={connections}
                projectId={projectId}
                update={(config) =>
                  updateNode(selected.id, (node) =>
                    node.type === 'source' ? { ...node, config } : node,
                  )
                }
              />
            ) : selected.config.kind === 'notion' ? (
              <NotionSettings
                config={selected.config}
                connections={connections}
                projectId={projectId}
                update={(config) =>
                  updateNode(selected.id, (node) =>
                    node.type === 'source' ? { ...node, config } : node,
                  )
                }
              />
            ) : (
              <ConfluenceSettings
                config={selected.config}
                connections={connections}
                projectId={projectId}
                update={(config) =>
                  updateNode(selected.id, (node) =>
                    node.type === 'source' ? { ...node, config } : node,
                  )
                }
              />
            )}
          </div>
        )}
        {selected?.type === 'chunk' && (
          <div className="field-stack">
            <p className="field-hint">
              Choose the saved chunking algorithm used for this index variant. Token limits use the
              stable UTF-8 byte tokenizer, a conservative model-independent upper bound.
            </p>
            {websiteSource && (
              <div className="website-preview-notice">
                <Database size={17} />
                <p>
                  To try new chunk settings without another Website request: save a new version,
                  choose an exact ready snapshot, then select{' '}
                  <strong>Reprocess saved source</strong>.
                </p>
              </div>
            )}
            <Label>
              Chunking algorithm
              <NativeSelect
                value={selected.algorithm ?? 'character_window'}
                onChange={(event) =>
                  selectChunkAlgorithm(
                    event.target.value as 'character_window' | 'section_token' | 'parent_child',
                  )
                }
              >
                <NativeSelectOption value="section_token">Section-aware tokens</NativeSelectOption>
                <NativeSelectOption value="parent_child">Parent and child</NativeSelectOption>
                <NativeSelectOption value="character_window">
                  Character window (compatibility)
                </NativeSelectOption>
              </NativeSelect>
            </Label>
            {selected.algorithm === 'section_token' ? (
              <>
                <Label>
                  Target tokens
                  <Input
                    type="number"
                    min={64}
                    max={8192}
                    value={selected.target_tokens}
                    onChange={(event) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'chunk' && node.algorithm === 'section_token'
                          ? { ...node, target_tokens: Number(event.target.value) }
                          : node,
                      )
                    }
                  />
                </Label>
                <Label>
                  Hard maximum tokens
                  <Input
                    type="number"
                    min={64}
                    max={16384}
                    value={selected.maximum_tokens}
                    onChange={(event) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'chunk' && node.algorithm === 'section_token'
                          ? { ...node, maximum_tokens: Number(event.target.value) }
                          : node,
                      )
                    }
                  />
                </Label>
                <Label>
                  Overlap tokens
                  <Input
                    type="number"
                    min={0}
                    max={4096}
                    value={selected.overlap_tokens}
                    onChange={(event) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'chunk' && node.algorithm === 'section_token'
                          ? { ...node, overlap_tokens: Number(event.target.value) }
                          : node,
                      )
                    }
                  />
                </Label>
              </>
            ) : selected.algorithm === 'parent_child' ? (
              <>
                {(
                  [
                    ['Child target tokens', 'child_target_tokens', 64, 4096],
                    ['Child hard maximum tokens', 'child_maximum_tokens', 64, 8192],
                    ['Child overlap tokens', 'child_overlap_tokens', 0, 2048],
                    ['Parent target tokens', 'parent_target_tokens', 128, 16384],
                    ['Parent hard maximum tokens', 'parent_maximum_tokens', 128, 32768],
                  ] as const
                ).map(([label, key, minimum, maximum]) => (
                  <Label key={key}>
                    {label}
                    <Input
                      type="number"
                      min={minimum}
                      max={maximum}
                      value={selected[key]}
                      onChange={(event) =>
                        updateNode(selected.id, (node) =>
                          node.type === 'chunk' && node.algorithm === 'parent_child'
                            ? { ...node, [key]: Number(event.target.value) }
                            : node,
                        )
                      }
                    />
                  </Label>
                ))}
                <p className="field-hint">
                  Child chunks are embedded. Retrieval supplies their saved parent text as evidence.
                </p>
              </>
            ) : (
              <>
                <div className="chunk-presets" aria-label="Chunking presets">
                  {(
                    [
                      ['Precise', 600, 80],
                      ['Balanced', 1000, 120],
                      ['Broad context', 1600, 200],
                    ] as const
                  ).map(([label, size, overlap]) => (
                    <Button
                      key={label}
                      type="button"
                      size="sm"
                      variant={
                        selected.size === size && selected.overlap === overlap
                          ? 'default'
                          : 'outline'
                      }
                      onClick={() =>
                        updateNode(selected.id, (node) =>
                          node.type === 'chunk' &&
                          (node.algorithm ?? 'character_window') === 'character_window'
                            ? { ...node, size: Number(size), overlap: Number(overlap) }
                            : node,
                        )
                      }
                    >
                      {label}
                    </Button>
                  ))}
                </div>
                <Label>
                  Chunk size (characters)
                  <Input
                    type="number"
                    min={100}
                    max={10000}
                    value={selected.size}
                    onChange={(event) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'chunk' &&
                        (node.algorithm ?? 'character_window') === 'character_window'
                          ? { ...node, size: Number(event.target.value) }
                          : node,
                      )
                    }
                  />
                </Label>
                <Label>
                  Overlap (characters)
                  <Input
                    type="number"
                    min={0}
                    value={selected.overlap}
                    onChange={(event) =>
                      updateNode(selected.id, (node) =>
                        node.type === 'chunk' &&
                        (node.algorithm ?? 'character_window') === 'character_window'
                          ? { ...node, overlap: Number(event.target.value) }
                          : node,
                      )
                    }
                  />
                </Label>
              </>
            )}
            {'add_heading_context' in selected && (
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={selected.add_heading_context}
                  onChange={(event) =>
                    updateNode(selected.id, (node) =>
                      node.type === 'chunk' && 'add_heading_context' in node
                        ? { ...node, add_heading_context: event.target.checked }
                        : node,
                    )
                  }
                />
                Add heading context to embedding text only
              </label>
            )}
          </div>
        )}
        {selected?.type === 'publish_index' && (
          <div className="field-stack">
            <p className="field-hint">
              Make the embedded passages available as an immutable, reusable index version.
              Publishing does not embed the passages again.
            </p>
            <Label>
              Reusable index collection
              <NativeSelect
                value={selected.knowledge_set_id ?? ''}
                onChange={(event) => {
                  const set = knowledgeSets.find((item) => item.id === event.target.value);
                  updateNode(selected.id, (node) =>
                    node.type === 'publish_index'
                      ? {
                          ...node,
                          knowledge_set_id: set?.id ?? null,
                          knowledge_set_name: set?.name ?? node.knowledge_set_name,
                        }
                      : node,
                  );
                }}
              >
                <NativeSelectOption value="">Create a new knowledge set</NativeSelectOption>
                {knowledgeSets.map((set) => (
                  <NativeSelectOption key={set.id} value={set.id}>
                    {set.name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Label>
            {!selected.knowledge_set_id && (
              <Label>
                New knowledge set name
                <Input
                  value={selected.knowledge_set_name}
                  maxLength={120}
                  onChange={(event) =>
                    updateNode(selected.id, (node) =>
                      node.type === 'publish_index'
                        ? { ...node, knowledge_set_name: event.target.value }
                        : node,
                    )
                  }
                />
              </Label>
            )}
          </div>
        )}
        {selected?.type === 'extract' && (
          <div className="field-stack">
            <p className="field-hint">
              Extract readable text with page-level provenance. PDF layout and OCR fallbacks run
              offline inside bounded workers.
            </p>
            {schemaVersion === 1 || selected.config_version !== 'layout-ocr-v1' ? (
              <>
                <dl className="ingestion-stage-facts">
                  <dt>Strategy</dt>
                  <dd>
                    {schemaVersion === 1
                      ? 'Legacy character extraction'
                      : 'Native text · Phase 1 compatibility'}
                  </dd>
                  <dt>Configuration version</dt>
                  <dd>{selected.config_version ?? '1'}</dd>
                </dl>
                {schemaVersion === 2 && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() =>
                      updateExtract({
                        strategy: 'auto',
                        ocr: {
                          mode: extractionCapabilities?.ocr.available ? 'auto' : 'off',
                          languages: extractionCapabilities?.ocr.languages.slice(0, 1) ?? ['eng'],
                          rotate_pages: true,
                          deskew: true,
                          dpi: 200,
                          max_pages: Math.min(extractionCapabilities?.ocr.max_pages ?? 50, 50),
                          timeout_seconds: 30,
                        },
                        tables: 'preserve',
                        quality_policy: structuredClone(
                          extractionCapabilities?.quality_policies.find(
                            (value) => value.id === 'default-v1',
                          )?.settings ?? fallbackQualityPolicy('default-v1'),
                        ),
                        language_policy: structuredClone(defaultLanguagePolicy),
                        config_version: 'layout-ocr-v1',
                      })
                    }
                  >
                    Enable robust extraction
                  </Button>
                )}
              </>
            ) : (
              <>
                <Label>
                  Extraction strategy
                  <NativeSelect
                    value={selected.strategy ?? 'auto'}
                    onChange={(event) =>
                      updateExtract({
                        strategy: event.target.value as 'auto' | 'native' | 'layout_aware',
                      })
                    }
                  >
                    <NativeSelectOption value="auto">Auto · page-level fallback</NativeSelectOption>
                    <NativeSelectOption value="native">Native text</NativeSelectOption>
                    <NativeSelectOption value="layout_aware">Layout-aware</NativeSelectOption>
                  </NativeSelect>
                </Label>
                <Label>
                  OCR policy
                  <NativeSelect
                    value={selectedOcr?.mode ?? 'off'}
                    onChange={(event) =>
                      selectedOcr &&
                      updateExtract({
                        ocr: {
                          ...selectedOcr,
                          mode: event.target.value as 'off' | 'auto' | 'always',
                        },
                      })
                    }
                  >
                    <NativeSelectOption value="off">Off</NativeSelectOption>
                    <NativeSelectOption
                      value="auto"
                      disabled={!extractionCapabilities?.ocr.available}
                    >
                      Automatic fallback
                    </NativeSelectOption>
                    <NativeSelectOption
                      value="always"
                      disabled={!extractionCapabilities?.ocr.available}
                    >
                      Always
                    </NativeSelectOption>
                  </NativeSelect>
                </Label>
                {!extractionCapabilities?.ocr.available && (
                  <div className="website-preview-notice" role="note">
                    <CircleAlert size={17} aria-hidden="true" />
                    <p>
                      {extractionCapabilities?.ocr.reason ??
                        'OCR capability information is unavailable.'}
                    </p>
                  </div>
                )}
                {selectedOcr && selectedOcr.mode !== 'off' && (
                  <>
                    <fieldset className="ingestion-inline-fieldset">
                      <legend>OCR languages</legend>
                      {(extractionCapabilities?.ocr.languages ?? []).map((language) => {
                        const checked = selectedOcr.languages.includes(language);
                        return (
                          <label className="ingestion-document-option" key={language}>
                            <input
                              type="checkbox"
                              checked={checked}
                              disabled={checked && selectedOcr.languages.length === 1}
                              onChange={(event) =>
                                updateExtract({
                                  ocr: {
                                    ...selectedOcr,
                                    languages: event.target.checked
                                      ? [...selectedOcr.languages, language].slice(0, 3)
                                      : selectedOcr.languages.filter((value) => value !== language),
                                  },
                                })
                              }
                            />
                            <span>
                              <strong>{language}</strong>
                              <small>Installed local language pack</small>
                            </span>
                          </label>
                        );
                      })}
                    </fieldset>
                    <label className="ingestion-document-option">
                      <input
                        type="checkbox"
                        checked={selectedOcr.rotate_pages}
                        onChange={(event) =>
                          updateExtract({
                            ocr: { ...selectedOcr, rotate_pages: event.target.checked },
                          })
                        }
                      />
                      <span>
                        <strong>Detect page rotation</strong>
                        <small>Apply only bounded 90-degree orientation correction.</small>
                      </span>
                    </label>
                    <label className="ingestion-document-option">
                      <input
                        type="checkbox"
                        checked={selectedOcr.deskew}
                        onChange={(event) =>
                          updateExtract({ ocr: { ...selectedOcr, deskew: event.target.checked } })
                        }
                      />
                      <span>
                        <strong>Deskew scans</strong>
                        <small>Search a bounded ±3-degree correction before OCR.</small>
                      </span>
                    </label>
                    <Label>
                      OCR resolution (DPI)
                      <Input
                        type="number"
                        min={150}
                        max={300}
                        aria-invalid={!!serverFieldErrors['ocr.dpi']}
                        value={selectedOcr.dpi}
                        onChange={(event) =>
                          updateExtract({
                            ocr: { ...selectedOcr, dpi: Number(event.target.value) },
                          })
                        }
                      />
                      {serverFieldErrors['ocr.dpi'] && (
                        <small role="alert" className="error-message">{serverFieldErrors['ocr.dpi']}</small>
                      )}
                    </Label>
                    <Label>
                      Maximum OCR pages
                      <Input
                        type="number"
                        min={1}
                        max={extractionCapabilities?.ocr.max_pages ?? 100}
                        aria-invalid={!!serverFieldErrors['ocr.max_pages']}
                        value={selectedOcr.max_pages}
                        onChange={(event) =>
                          updateExtract({
                            ocr: { ...selectedOcr, max_pages: Number(event.target.value) },
                          })
                        }
                      />
                      {serverFieldErrors['ocr.max_pages'] && (
                        <small role="alert" className="error-message">{serverFieldErrors['ocr.max_pages']}</small>
                      )}
                    </Label>
                    <Label>
                      Per-page timeout (seconds)
                      <Input
                        type="number"
                        min={5}
                        max={60}
                        aria-invalid={!!serverFieldErrors['ocr.timeout_seconds']}
                        value={selectedOcr.timeout_seconds}
                        onChange={(event) =>
                          updateExtract({
                            ocr: {
                              ...selectedOcr,
                              timeout_seconds: Number(event.target.value),
                            },
                          })
                        }
                      />
                      {serverFieldErrors['ocr.timeout_seconds'] && (
                        <small role="alert" className="error-message">
                          {serverFieldErrors['ocr.timeout_seconds']}
                        </small>
                      )}
                    </Label>
                  </>
                )}
                <Label>
                  Table evidence
                  <NativeSelect
                    value={selected.tables ?? 'preserve'}
                    onChange={(event) =>
                      updateExtract({
                        tables: event.target.value as 'preserve' | 'markdown' | 'plain_text',
                      })
                    }
                  >
                    <NativeSelectOption value="preserve">Structured + Markdown</NativeSelectOption>
                    <NativeSelectOption value="markdown">Markdown</NativeSelectOption>
                    <NativeSelectOption value="plain_text">Plain text</NativeSelectOption>
                  </NativeSelect>
                </Label>
                <Label>
                  Quality policy
                  <NativeSelect
                    value={selectedQualityId}
                    onChange={(event) => {
                      const id = event.target.value as QualityPolicyId;
                      updateExtract({
                        quality_policy: structuredClone(
                          extractionCapabilities?.quality_policies.find((value) => value.id === id)
                            ?.settings ?? fallbackQualityPolicy(id),
                        ),
                      });
                    }}
                  >
                    {(extractionCapabilities?.quality_policies ?? []).map((policy) => (
                      <NativeSelectOption key={policy.id} value={policy.id}>
                        {policy.name}
                      </NativeSelectOption>
                    ))}
                    {!extractionCapabilities && (
                      <>
                        <NativeSelectOption value="default-v1">Balanced</NativeSelectOption>
                        <NativeSelectOption value="strict-v1">Strict</NativeSelectOption>
                        <NativeSelectOption value="warn-v1">Review warnings</NativeSelectOption>
                      </>
                    )}
                  </NativeSelect>
                </Label>
                <p className="field-hint">
                  {extractionCapabilities?.quality_policies.find(
                    (value) => value.id === selectedQualityId,
                  )?.description ?? 'Saved extraction thresholds control publication.'}
                </p>
                <Label>
                  Warning publication
                  <NativeSelect
                    value={selectedQuality.warning_action}
                    onChange={(event) =>
                      updateExtract({
                        quality_policy: {
                          ...selectedQuality,
                          warning_action: event.target.value as 'publish' | 'fail',
                        },
                      })
                    }
                  >
                    <NativeSelectOption value="fail">Block publication</NativeSelectOption>
                    <NativeSelectOption value="publish">
                      Publish with visible warning
                    </NativeSelectOption>
                  </NativeSelect>
                </Label>
                <Label>
                  Failed optional items
                  <NativeSelect
                    value={selectedQuality.failed_item_action}
                    onChange={(event) =>
                      updateExtract({
                        quality_policy: {
                          ...selectedQuality,
                          failed_item_action: event.target.value as 'fail' | 'exclude',
                        },
                      })
                    }
                  >
                    <NativeSelectOption value="fail">Fail the run</NativeSelectOption>
                    <NativeSelectOption value="exclude">Exclude and report</NativeSelectOption>
                  </NativeSelect>
                </Label>
                <details>
                  <summary>Quality thresholds</summary>
                  <div className="field-stack">
                    <Label>
                      Maximum empty-page ratio
                      <Input
                        type="number"
                        min={0}
                        max={1}
                        step={0.01}
                        value={selectedQuality.thresholds.maximum_empty_page_ratio}
                        onChange={(event) =>
                          updateExtract({
                            quality_policy: {
                              ...selectedQuality,
                              thresholds: {
                                ...selectedQuality.thresholds,
                                maximum_empty_page_ratio: Number(event.target.value),
                              },
                            },
                          })
                        }
                      />
                    </Label>
                    <Label>
                      Maximum replacement-character ratio
                      <Input
                        type="number"
                        min={0}
                        max={1}
                        step={0.0001}
                        value={selectedQuality.thresholds.maximum_replacement_character_ratio}
                        onChange={(event) =>
                          updateExtract({
                            quality_policy: {
                              ...selectedQuality,
                              thresholds: {
                                ...selectedQuality.thresholds,
                                maximum_replacement_character_ratio: Number(event.target.value),
                              },
                            },
                          })
                        }
                      />
                    </Label>
                    <Label>
                      Maximum control-character ratio
                      <Input
                        type="number"
                        min={0}
                        max={1}
                        step={0.0001}
                        value={selectedQuality.thresholds.maximum_control_character_ratio}
                        onChange={(event) =>
                          updateExtract({
                            quality_policy: {
                              ...selectedQuality,
                              thresholds: {
                                ...selectedQuality.thresholds,
                                maximum_control_character_ratio: Number(event.target.value),
                              },
                            },
                          })
                        }
                      />
                    </Label>
                    <Label>
                      Minimum OCR engine confidence
                      <Input
                        type="number"
                        min={0}
                        max={100}
                        value={selectedQuality.thresholds.minimum_ocr_confidence}
                        onChange={(event) =>
                          updateExtract({
                            quality_policy: {
                              ...selectedQuality,
                              thresholds: {
                                ...selectedQuality.thresholds,
                                minimum_ocr_confidence: Number(event.target.value),
                              },
                            },
                          })
                        }
                      />
                    </Label>
                    <Label>
                      <input
                        type="checkbox"
                        checked={selectedQuality.thresholds.fail_on_suspicious_reading_order}
                        onChange={(event) =>
                          updateExtract({
                            quality_policy: {
                              ...selectedQuality,
                              thresholds: {
                                ...selectedQuality.thresholds,
                                fail_on_suspicious_reading_order: event.target.checked,
                              },
                            },
                          })
                        }
                      />
                      Fail on suspicious reading order
                    </Label>
                    <Label>
                      <input
                        type="checkbox"
                        checked={selectedQuality.thresholds.fail_on_malformed_tables}
                        onChange={(event) =>
                          updateExtract({
                            quality_policy: {
                              ...selectedQuality,
                              thresholds: {
                                ...selectedQuality.thresholds,
                                fail_on_malformed_tables: event.target.checked,
                              },
                            },
                          })
                        }
                      />
                      Fail on malformed tables
                    </Label>
                  </div>
                </details>
                <details>
                  <summary>Language policy</summary>
                  <div className="field-stack">
                    <p className="field-hint">
                      Detection records model/version and confidence. Source text is never
                      translated.
                    </p>
                    <Label>
                      Allowed language tags
                      <Input
                        value={selectedLanguage.allowlist.join(', ')}
                        placeholder="Empty allows all; for example en, fr"
                        onChange={(event) =>
                          updateExtract({
                            language_policy: {
                              ...selectedLanguage,
                              allowlist: event.target.value
                                .split(',')
                                .map((value) => value.trim().toLowerCase())
                                .filter(Boolean),
                            },
                          })
                        }
                      />
                    </Label>
                    <Label>
                      Minimum detection confidence
                      <Input
                        type="number"
                        min={0}
                        max={1}
                        step={0.05}
                        value={selectedLanguage.minimum_confidence}
                        onChange={(event) =>
                          updateExtract({
                            language_policy: {
                              ...selectedLanguage,
                              minimum_confidence: Number(event.target.value),
                            },
                          })
                        }
                      />
                    </Label>
                    <Label>
                      Disallowed language
                      <NativeSelect
                        value={selectedLanguage.disallowed_action}
                        onChange={(event) =>
                          updateExtract({
                            language_policy: {
                              ...selectedLanguage,
                              disallowed_action: event.target.value as 'fail' | 'exclude',
                            },
                          })
                        }
                      >
                        <NativeSelectOption value="fail">Fail the run</NativeSelectOption>
                        <NativeSelectOption value="exclude">Exclude and report</NativeSelectOption>
                      </NativeSelect>
                    </Label>
                    <Label>
                      Mixed-language documents
                      <NativeSelect
                        value={selectedLanguage.mixed_language_action}
                        onChange={(event) =>
                          updateExtract({
                            language_policy: {
                              ...selectedLanguage,
                              mixed_language_action: event.target.value as
                                | 'allow'
                                | 'warn'
                                | 'fail',
                            },
                          })
                        }
                      >
                        <NativeSelectOption value="allow">Allow</NativeSelectOption>
                        <NativeSelectOption value="warn">Warn</NativeSelectOption>
                        <NativeSelectOption value="fail">Fail</NativeSelectOption>
                      </NativeSelect>
                    </Label>
                  </div>
                </details>
              </>
            )}
          </div>
        )}
        {selected?.type === 'clean' && (
          <div className="field-stack">
            <p className="field-hint">
              Prepare extracted text before splitting it into searchable passages. These settings
              are recorded with the saved version.
            </p>
            {schemaVersion === 1 ? (
              <dl className="ingestion-stage-facts">
                <dt>Normalize whitespace</dt>
                <dd>{selected.normalize_whitespace === false ? 'Off' : 'On'}</dd>
                <dt>Exact-content deduplication</dt>
                <dd>{selected.exact_content_deduplication === false ? 'Off' : 'On'}</dd>
                <dt>Minimum text length</dt>
                <dd>{selected.minimum_text_chars ?? 1} characters</dd>
                <dt>Maximum text length</dt>
                <dd>{(selected.maximum_text_chars ?? 2_000_000).toLocaleString()} characters</dd>
                <dt>Boilerplate rules</dt>
                <dd>{selected.repeated_boilerplate?.length ?? 0}</dd>
              </dl>
            ) : (
              <>
                <CleaningTransformSettings
                  node={selected}
                  capabilities={extractionCapabilities}
                  update={(value) =>
                    updateNode(selected.id, (node) => (node.type === 'clean' ? value : node))
                  }
                />
                <details>
                  <summary>Duplicate policy</summary>
                  <div className="field-stack">
                    {(
                      [
                        ['exact_raw', 'Exact raw-content hash'],
                        ['exact_cleaned', 'Exact cleaned-content hash'],
                        ['normalized_sections', 'Normalized section fingerprint'],
                        ['near_duplicate', 'Near-duplicate SimHash'],
                      ] as const
                    ).map(([key, label]) => (
                      <Label key={key}>
                        <input
                          type="checkbox"
                          checked={selectedDuplicate[key]}
                          onChange={(event) =>
                            updateNode(selected.id, (node) =>
                              node.type === 'clean'
                                ? {
                                    ...node,
                                    duplicate_policy: {
                                      ...selectedDuplicate,
                                      [key]: event.target.checked,
                                    },
                                  }
                                : node,
                            )
                          }
                        />
                        {label}
                      </Label>
                    ))}
                    {selectedDuplicate.near_duplicate && (
                      <Label>
                        Near-duplicate similarity threshold
                        <Input
                          type="number"
                          min={0.75}
                          max={1}
                          step={0.01}
                          value={selectedDuplicate.near_duplicate_threshold}
                          onChange={(event) =>
                            updateNode(selected.id, (node) =>
                              node.type === 'clean'
                                ? {
                                    ...node,
                                    duplicate_policy: {
                                      ...selectedDuplicate,
                                      near_duplicate_threshold: Number(event.target.value),
                                    },
                                  }
                                : node,
                            )
                          }
                        />
                      </Label>
                    )}
                    <Label>
                      Pinned canonical locations
                      <Input
                        value={selectedDuplicate.pinned_canonical_locations.join(', ')}
                        placeholder="Comma-separated stable source identities"
                        onChange={(event) =>
                          updateNode(selected.id, (node) =>
                            node.type === 'clean'
                              ? {
                                  ...node,
                                  duplicate_policy: {
                                    ...selectedDuplicate,
                                    pinned_canonical_locations: event.target.value
                                      .split(',')
                                      .map((value) => value.trim())
                                      .filter(Boolean),
                                  },
                                }
                              : node,
                          )
                        }
                      />
                    </Label>
                    <p className="field-hint">
                      Canonical order: pinned source, connector priority, first stable identity,
                      then lexical identity. Overrides are saved in a new pipeline version.
                    </p>
                  </div>
                </details>
                <details>
                  <summary>Sensitive-data policy</summary>
                  <div className="field-stack">
                    <Label>
                      <input
                        type="checkbox"
                        checked={selectedSensitive.enabled}
                        onChange={(event) =>
                          updateNode(selected.id, (node) =>
                            node.type === 'clean'
                              ? {
                                  ...node,
                                  sensitive_data_policy: {
                                    ...selectedSensitive,
                                    enabled: event.target.checked,
                                  },
                                }
                              : node,
                          )
                        }
                      />
                      Redact sensitive values before chunking and embedding
                    </Label>
                    <p className="field-hint">
                      Redaction is irreversible in cleaned passages, embeddings, retrieval evidence,
                      and provider requests. Raw artifacts and full diffs are encrypted, retained
                      for 30 days, and limited to project owners and admins.
                    </p>
                    {selectedSensitive.rules.map((rule) => (
                      <Label key={rule.entity_class}>
                        {rule.entity_class.replaceAll('_', ' ')}
                        <NativeSelect
                          aria-label={`${rule.entity_class.replaceAll('_', ' ')} action`}
                          disabled={!selectedSensitive.enabled}
                          value={rule.action}
                          onChange={(event) =>
                            updateNode(selected.id, (node) =>
                              node.type === 'clean'
                                ? {
                                    ...node,
                                    sensitive_data_policy: {
                                      ...selectedSensitive,
                                      rules: selectedSensitive.rules.map((value) =>
                                        value.entity_class === rule.entity_class
                                          ? {
                                              ...value,
                                              action: event.target.value as
                                                | 'redact'
                                                | 'drop_document',
                                            }
                                          : value,
                                      ),
                                    },
                                  }
                                : node,
                            )
                          }
                        >
                          <NativeSelectOption value="redact">Redact value</NativeSelectOption>
                          <NativeSelectOption value="drop_document">
                            Drop entire document
                          </NativeSelectOption>
                        </NativeSelect>
                      </Label>
                    ))}
                    <p className="field-hint">
                      Deterministic pattern detectors cover the listed classes but cannot detect
                      every sensitive value. Review synthetic false-positive and false-negative
                      cases before relying on this policy.
                    </p>
                  </div>
                </details>
              </>
            )}
          </div>
        )}
        {selected?.type === 'embed' && (
          <div className="field-stack">
            <p className="field-hint">
              Convert each passage into a vector for retrieval. The embedding model and dimensions
              must match the destination index.
            </p>
            <dl className="ingestion-stage-facts">
              <dt>Provider</dt>
              <dd>{selected.provider}</dd>
              <dt>Model</dt>
              <dd>{selected.model}</dd>
              <dt>Dimensions</dt>
              <dd>{selected.dimensions}</dd>
              <dt>Configuration version</dt>
              <dd>{selected.config_version}</dd>
            </dl>
            <p className="field-hint">
              Model configuration is managed by the backend and saved with this pipeline version.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
