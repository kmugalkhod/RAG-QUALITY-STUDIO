import { useState, type ReactNode } from 'react';

import { Callout, LINK, SUMMARY } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import { Checkbox } from '../../../components/ui/checkbox';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { docsHref } from '../../../lib/docs';
import { cn } from '../../../lib/utils';
import type { ConnectionSettings, SourceConnection } from '../../connections/model';
import type { Document, KnowledgeSet } from '../../documents/model';
import {
  currentExtractVersion,
  defaultDuplicatePolicy,
  defaultLanguagePolicy,
  defaultSensitiveDataPolicy,
  extractDifferences,
  extractLegacySettings,
  extractReadsFiles,
  fallbackQualityPolicy,
  fieldErrorsForNode,
  ingestionStageLabels as labels,
  isLayoutExtractVersion,
  legacyExtractFields,
  qualityChoice,
  type QualityChoice,
  qualityPolicyForChoice,
  recommendedExtractSettings,
  resetExtractAdvanced,
  resetExtractLegacy,
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
import {
  CHECK_ROW,
  DETAILS,
  FACTS,
  FIELD_ERROR,
  FIELDSET,
  FORM,
  HINT,
  OPTION,
  STACK,
} from './settingsStyles';

type SourceKind = 'existing_files' | 'website' | 's3' | 'notion' | 'confluence';

const sourceNames: Record<SourceKind, string> = {
  existing_files: 'Existing files',
  website: 'Website',
  s3: 'Amazon S3',
  notion: 'Notion',
  confluence: 'Confluence',
};

// Readable names for common Tesseract language packs; unknown codes show as-is.
const languageNames: Record<string, string> = {
  eng: 'English',
  fra: 'French',
  deu: 'German',
  spa: 'Spanish',
  ita: 'Italian',
  por: 'Portuguese',
  nld: 'Dutch',
  hin: 'Hindi',
  mar: 'Marathi',
  ara: 'Arabic',
  chi_sim: 'Chinese (simplified)',
  jpn: 'Japanese',
};

function languageName(code: string) {
  return languageNames[code] ? `${languageNames[code]} (${code})` : code;
}

const qualityChoiceHelp: Record<QualityChoice, string> = {
  stop: 'A file or page that fails the quality checks stops the run, so nothing new is published until you review it. The last published index stays in use.',
  publish:
    'Quality problems are shown as warnings and are still published. A file or page that cannot be read at all is left out with its reason, and everything else is published.',
  custom:
    'This pipeline uses custom quality rules. Review them under Advanced extraction settings.',
};

function stageName(node: IngestionNode) {
  return node.type === 'source' ? sourceNames[node.config.kind] : labels[node.type];
}

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
  sourceCount = 1,
  sourceLabel,
  nodeLabel,
  heading,
  stageMeta,
  stageOptions,
  scopeControl,
  onSelectNode,
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
  /** Source nodes in the draft; with more than one the kind is fixed. */
  sourceCount?: number;
  /** "Website 2" style names when there are several sources. */
  sourceLabel?: (nodeId: string) => string;
  /** Stage names that say which source a stage belongs to in a per-source layout. */
  nodeLabel?: (node: IngestionNode) => string;
  /** Replaces "<stage> settings", for a stage shown once for several sources. */
  heading?: string;
  /** Replaces the "Stage N of M" line. */
  stageMeta?: string;
  /** Replaces the stage menu's entries, when the canvas shows grouped stages. */
  stageOptions?: { value: string; label: string }[];
  /** Shown above the stage's fields: which sources an edit applies to. */
  scopeControl?: ReactNode;
  onSelectNode: (nodeId: string) => void;
}) {
  const nameOf = (node: IngestionNode) =>
    nodeLabel
      ? nodeLabel(node)
      : node.type === 'source' && sourceLabel
        ? sourceLabel(node.id)
        : stageName(node);
  // Server errors are keyed per node, so each source shows only its own.
  const nodeErrors = fieldErrorsForNode(serverFieldErrors, selected?.id ?? selectedNode);
  const readsFiles = extractReadsFiles(nodes);
  const [extractAdvancedOpen, setExtractAdvancedOpen] = useState(false);
  const selectedOcr =
    selected?.type === 'extract'
      ? (selected.ocr ?? {
          mode: 'off' as const,
          languages: ['eng'],
          rotate_pages: true,
          deskew: true,
          dpi: 200,
          max_pages: 100,
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
  const selectedQualityChoice: QualityChoice =
    selected?.type === 'extract'
      ? qualityChoice(selected.quality_policy, extractionCapabilities)
      : 'stop';
  const extractAdvanced =
    selected?.type === 'extract'
      ? extractDifferences(selected, extractionCapabilities, readsFiles)
      : [];
  const extractLegacy =
    selected?.type === 'extract'
      ? extractLegacySettings(selected, extractionCapabilities, readsFiles)
      : [];
  // Hidden settings have no field, so their server errors show on the legacy line.
  const extractLegacyErrors = Object.entries(nodeErrors).filter(([key]) =>
    legacyExtractFields.has(key),
  );
  // Server errors on advanced fields open the section so they are never hidden.
  const hasExtractAdvancedError = Object.keys(nodeErrors).some(
    (key) =>
      !legacyExtractFields.has(key) &&
      (key.startsWith('ocr.') ||
        key.startsWith('quality_policy') ||
        key.startsWith('language_policy')),
  );
  const extractChangedCount = extractAdvanced.length + (extractLegacy.length > 0 ? 1 : 0);
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
      className="flex min-w-0 flex-col border-t border-border bg-surface desktop:w-panel desktop:shrink-0 desktop:overflow-y-auto desktop:overscroll-contain desktop:border-t-0 desktop:border-l"
      aria-labelledby="ingestion-settings-heading"
    >
      <div className="flex shrink-0 flex-col gap-1 border-b border-border bg-surface px-4 py-4 md:px-6 desktop:sticky desktop:top-0 desktop:z-10">
        <h2 id="ingestion-settings-heading" className="text-base font-semibold text-foreground">
          {heading ?? (selected ? `${nameOf(selected)} settings` : 'Node settings')}
        </h2>
        <p className="flex flex-wrap items-center gap-x-2 text-xs text-foreground-muted">
          <span>
            {stageMeta ??
              `Stage ${nodes.findIndex((node) => node.id === selectedNode) + 1} of ${nodes.length}`}{' '}
            ·{' '}
            {dirty
              ? 'Draft configuration'
              : saved
                ? `Version ${saved.version}`
                : 'Draft configuration'}
          </span>
          {selected && (
            <a
              className={cn(LINK, 'text-xs')}
              href={
                selected.type === 'source'
                  ? docsHref('ingestion/sources')
                  : selected.type === 'extract'
                    ? docsHref('ingestion/extraction')
                    : selected.type === 'clean'
                      ? docsHref('ingestion/cleaning')
                      : selected.type === 'chunk' || selected.type === 'embed'
                        ? docsHref('ingestion/chunking')
                        : docsHref('knowledge-base/collections')
              }
              target="_blank"
              rel="noopener noreferrer"
            >
              About this stage
            </a>
          )}
        </p>
        {/* Keyboard and screen reader route to every stage, outside canvas clicks. */}
        <Label className="mt-3 mb-0">
          Selected stage
          <NativeSelect
            className="mt-2"
            value={selectedNode}
            onChange={(event) => onSelectNode(event.target.value)}
          >
            {(
              stageOptions ??
              nodes.map((node, index) => ({
                value: node.id,
                label: `${index + 1} · ${nameOf(node)}`,
              }))
            ).map((option) => (
              <NativeSelectOption key={option.value} value={option.value}>
                {option.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Label>
      </div>
      <div
        id="ingestion-settings-body"
        className={cn(
          FORM,
          'p-4 outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent md:p-6',
        )}
        tabIndex={0}
        role="region"
        aria-label="Stage settings"
      >
        {validation.length > 0 && (
          <Callout tone="warning" role="status" title="Complete the configuration">
            <ul className="flex flex-col gap-1">
              {validation.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </Callout>
        )}
        {scopeControl}
        {selected?.type === 'source' && (
          <div className={STACK}>
            <Label>
              Source type
              <NativeSelect
                value={selected.config.kind}
                disabled={sourceCount > 1}
                aria-describedby={sourceCount > 1 ? 'source-kind-fixed' : undefined}
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
            {sourceCount > 1 && (
              <p id="source-kind-fixed" className={HINT}>
                Remove the other sources to change the source type.
              </p>
            )}
            {/* Points to vault setup while the source type can still change, or for a
                credentialed source; several sources fix the type, so it is not shown then. */}
            {!connectionSettings?.enabled &&
              (sourceCount <= 1 ||
                ['s3', 'notion', 'confluence'].includes(selected.config.kind)) && (
                <Callout role="note">
                  <p>
                    Amazon S3, Notion, and Confluence need the local encrypted connection vault.{' '}
                    <a href={`#/projects/${projectId}/settings`}>
                      Review setup in project settings
                    </a>
                    .
                  </p>
                </Callout>
              )}
            {selected.config.kind === 'existing_files' ? (
              <>
                <p className={HINT}>
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
                      <label className={OPTION}>
                        <Checkbox
                          checked={checked}
                          disabled={disabled}
                          onCheckedChange={(checked) =>
                            updateNode(selected.id, (node) =>
                              node.type === 'source' && node.config.kind === 'existing_files'
                                ? {
                                    ...node,
                                    config: {
                                      ...node.config,
                                      document_ids:
                                        checked === true
                                          ? [...node.config.document_ids, document.id]
                                          : node.config.document_ids.filter(
                                              (id: string) => id !== document.id,
                                            ),
                                      optional_document_ids:
                                        checked === true
                                          ? (node.config.optional_document_ids ?? [])
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
                        <label className={OPTION}>
                          <Checkbox
                            checked={(sourceConfig.optional_document_ids ?? []).includes(
                              document.id,
                            )}
                            onCheckedChange={(checked) =>
                              updateNode(selected.id, (node) =>
                                node.type === 'source' && node.config.kind === 'existing_files'
                                  ? {
                                      ...node,
                                      config: {
                                        ...node.config,
                                        optional_document_ids:
                                          checked === true
                                            ? [
                                                ...(node.config.optional_document_ids ?? []),
                                                document.id,
                                              ]
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
                key={selected.id}
                config={selected.config}
                fieldErrors={nodeErrors}
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
          <div className={STACK}>
            <p className={HINT}>
              Choose the saved chunking algorithm used for this index variant. Token limits use the
              stable UTF-8 byte tokenizer, a conservative model-independent upper bound.
            </p>
            {websiteSource && (
              <Callout>
                <p>
                  To try new chunk settings without another Website request: save a new version,
                  choose an exact ready snapshot, then select{' '}
                  <strong>Reprocess saved source</strong>.
                </p>
              </Callout>
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
                <p className={HINT}>
                  Child chunks are embedded. Retrieval supplies their saved parent text as evidence.
                </p>
              </>
            ) : (
              <>
                <div className="flex flex-wrap gap-2" role="group" aria-label="Chunking presets">
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
                      variant="outline"
                      className="aria-pressed:border-accent aria-pressed:text-accent"
                      aria-pressed={selected.size === size && selected.overlap === overlap}
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
              <label className={CHECK_ROW}>
                <Checkbox
                  checked={selected.add_heading_context}
                  onCheckedChange={(checked) =>
                    updateNode(selected.id, (node) =>
                      node.type === 'chunk' && 'add_heading_context' in node
                        ? { ...node, add_heading_context: checked === true }
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
          <div className={STACK}>
            <p className={HINT}>
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
          <div className={STACK}>
            {schemaVersion === 1 || !isLayoutExtractVersion(selected.config_version) ? (
              <>
                <p className={HINT}>
                  Extract readable text with page-level provenance. PDF layout and OCR fallbacks run
                  offline inside bounded workers.
                </p>
                <dl className={FACTS}>
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
                  <p className={HINT}>
                    Runs report quality findings for this extractor as warnings only; they do not
                    stop publication. Enable robust extraction to apply the quality policy.
                  </p>
                )}
                {schemaVersion === 2 && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() =>
                      updateExtract({
                        ...recommendedExtractSettings(extractionCapabilities, readsFiles),
                        config_version: currentExtractVersion,
                      })
                    }
                  >
                    Enable robust extraction
                  </Button>
                )}
              </>
            ) : (
              <>
                {selected.config_version !== currentExtractVersion && (
                  <Callout role="note" title={`Saved with ${selected.config_version}`}>
                    <p>
                      This version keeps its original extractor so earlier runs reproduce. The
                      current extractor, {currentExtractVersion}, keeps tables and their rows
                      together on websites and in files, keeps the reading order of multi-column
                      pages and leaves out reference lists. It also reads tables printed sideways
                      and tables in PowerPoint slides, keeps words broken at the end of a line
                      whole, reads charts as text instead of as broken tables, and files each table
                      under its caption. Saving the upgrade creates a new pipeline version, and its
                      next run processes documents again.
                    </p>
                    <div>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => updateExtract({ config_version: currentExtractVersion })}
                      >
                        Upgrade extraction
                      </Button>
                    </div>
                  </Callout>
                )}
                {!readsFiles && (
                  <Callout role="note" title="Quality and language only">
                    <p>
                      Website, Notion and Confluence pages are read as structured text, so
                      extraction strategy, OCR and table evidence do not apply to them. Saved values
                      are kept and take effect for uploaded files and Amazon S3 sources.
                    </p>
                  </Callout>
                )}
                {readsFiles && (
                  <>
                    <p className={HINT}>
                      Text, tables and headings are read automatically. Scanned pages are read with
                      OCR when they have no text layer.
                    </p>
                    {!extractionCapabilities?.ocr.available && (
                      <Callout role="note">
                        <p>
                          {extractionCapabilities?.ocr.reason ??
                            'OCR capability information is unavailable.'}
                        </p>
                      </Callout>
                    )}
                    {selectedOcr && selectedOcr.mode !== 'off' && (
                      <fieldset className={FIELDSET}>
                        <legend>Languages in scanned pages</legend>
                        {(extractionCapabilities?.ocr.languages ?? []).map((language) => {
                          const checked = selectedOcr.languages.includes(language);
                          return (
                            <label className={OPTION} key={language}>
                              <Checkbox
                                checked={checked}
                                disabled={checked && selectedOcr.languages.length === 1}
                                onCheckedChange={(checked) =>
                                  updateExtract({
                                    ocr: {
                                      ...selectedOcr,
                                      languages:
                                        checked === true
                                          ? [...selectedOcr.languages, language].slice(0, 3)
                                          : selectedOcr.languages.filter(
                                              (value) => value !== language,
                                            ),
                                    },
                                  })
                                }
                              />
                              <span>
                                <strong>{languageName(language)}</strong>
                                <small>Installed local language pack</small>
                              </span>
                            </label>
                          );
                        })}
                      </fieldset>
                    )}
                  </>
                )}
                <Label>
                  If a file can&apos;t be read well
                  <NativeSelect
                    value={selectedQualityChoice}
                    onChange={(event) =>
                      updateExtract({
                        quality_policy: qualityPolicyForChoice(
                          event.target.value as 'stop' | 'publish',
                          extractionCapabilities,
                        ),
                      })
                    }
                  >
                    <NativeSelectOption value="stop">Stop and let me review</NativeSelectOption>
                    <NativeSelectOption value="publish">
                      {readsFiles
                        ? 'Publish the other files and show warnings'
                        : 'Publish the other pages and show warnings'}
                    </NativeSelectOption>
                    {selectedQualityChoice === 'custom' && (
                      <NativeSelectOption value="custom" disabled>
                        Custom (see Advanced)
                      </NativeSelectOption>
                    )}
                  </NativeSelect>
                </Label>
                <p className={HINT}>{qualityChoiceHelp[selectedQualityChoice]}</p>
                {(extractLegacy.length > 0 || extractLegacyErrors.length > 0) && (
                  <Callout role="note">
                    {extractLegacy.length > 0 && (
                      <p>
                        {extractLegacy.length === 1
                          ? 'Uses an older custom setting: '
                          : 'Uses older custom settings: '}
                        {extractLegacy.join(', ')}. The panel no longer shows{' '}
                        {extractLegacy.length === 1 ? 'this setting' : 'these settings'}; the saved
                        value runs as saved.
                      </p>
                    )}
                    {extractLegacyErrors.map(([key, message]) => (
                      <p key={key} role="alert" className={FIELD_ERROR}>
                        {message}
                      </p>
                    ))}
                    <div>
                      <Button
                        type="button"
                        variant="outline"
                        aria-label="Reset older settings to recommended"
                        onClick={() =>
                          updateExtract(
                            resetExtractLegacy(selected, extractionCapabilities, readsFiles),
                          )
                        }
                      >
                        Reset to recommended
                      </Button>
                    </div>
                  </Callout>
                )}
                <details
                  className={DETAILS}
                  open={extractAdvancedOpen || hasExtractAdvancedError}
                  onToggle={(event) => setExtractAdvancedOpen(event.currentTarget.open)}
                >
                  <summary className={SUMMARY}>
                    <span>Advanced extraction settings</span>
                    <small className={HINT}>
                      ·{' '}
                      {extractChangedCount === 0 ? 'recommended' : `${extractChangedCount} changed`}
                    </small>
                  </summary>
                  <div className={STACK}>
                    <p className={HINT}>
                      {extractAdvanced.length === 0
                        ? extractLegacy.length > 0
                          ? 'These settings use the recommended values. The older setting is listed above.'
                          : 'Using recommended settings.'
                        : `${extractAdvanced.length} ${
                            extractAdvanced.length === 1 ? 'setting differs' : 'settings differ'
                          } from recommended: ${extractAdvanced.join(', ')}.`}
                    </p>
                    {extractAdvanced.length > 0 && (
                      <div>
                        <Button
                          type="button"
                          variant="outline"
                          onClick={() =>
                            updateExtract(
                              resetExtractAdvanced(selected, extractionCapabilities, readsFiles),
                            )
                          }
                        >
                          Reset to recommended
                        </Button>
                      </div>
                    )}
                    {readsFiles && selectedOcr && selectedOcr.mode !== 'off' && (
                      <Label>
                        Maximum OCR pages
                        <Input
                          type="number"
                          min={1}
                          max={extractionCapabilities?.ocr.max_pages ?? 100}
                          aria-invalid={!!nodeErrors['ocr.max_pages']}
                          value={selectedOcr.max_pages}
                          onChange={(event) =>
                            updateExtract({
                              ocr: { ...selectedOcr, max_pages: Number(event.target.value) },
                            })
                          }
                        />
                        <small className={HINT}>
                          Scanned PDF pages read per file. More pages take longer but cost nothing
                          extra.
                        </small>
                        {nodeErrors['ocr.max_pages'] && (
                          <small role="alert" className={FIELD_ERROR}>
                            {nodeErrors['ocr.max_pages']}
                          </small>
                        )}
                      </Label>
                    )}
                    <Label>
                      Quality policy
                      <NativeSelect
                        value={selectedQualityId}
                        onChange={(event) => {
                          const id = event.target.value as QualityPolicyId;
                          updateExtract({
                            quality_policy: structuredClone(
                              extractionCapabilities?.quality_policies.find(
                                (value) => value.id === id,
                              )?.settings ?? fallbackQualityPolicy(id),
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
                    <p className={HINT}>
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
                      Files or pages that fail
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
                    <details className={DETAILS}>
                      <summary className={SUMMARY}>Quality thresholds</summary>
                      <div className={STACK}>
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
                        <label className={CHECK_ROW}>
                          <Checkbox
                            checked={selectedQuality.thresholds.fail_on_suspicious_reading_order}
                            onCheckedChange={(checked) =>
                              updateExtract({
                                quality_policy: {
                                  ...selectedQuality,
                                  thresholds: {
                                    ...selectedQuality.thresholds,
                                    fail_on_suspicious_reading_order: checked === true,
                                  },
                                },
                              })
                            }
                          />
                          Fail on suspicious reading order
                        </label>
                        <label className={CHECK_ROW}>
                          <Checkbox
                            checked={selectedQuality.thresholds.fail_on_malformed_tables}
                            onCheckedChange={(checked) =>
                              updateExtract({
                                quality_policy: {
                                  ...selectedQuality,
                                  thresholds: {
                                    ...selectedQuality.thresholds,
                                    fail_on_malformed_tables: checked === true,
                                  },
                                },
                              })
                            }
                          />
                          Fail on malformed tables
                        </label>
                      </div>
                    </details>
                    <details className={DETAILS}>
                      <summary className={SUMMARY}>Language policy</summary>
                      <div className={STACK}>
                        <p className={HINT}>
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
                            <NativeSelectOption value="exclude">
                              Exclude and report
                            </NativeSelectOption>
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
                  </div>
                </details>
              </>
            )}
          </div>
        )}
        {selected?.type === 'clean' && (
          <div className={STACK}>
            <p className={HINT}>
              Prepare extracted text before splitting it into searchable passages. These settings
              are recorded with the saved version.
            </p>
            {schemaVersion === 1 ? (
              <dl className={FACTS}>
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
                <details className={DETAILS}>
                  <summary className={SUMMARY}>Duplicate policy</summary>
                  <div className={STACK}>
                    {(
                      [
                        ['exact_raw', 'Exact raw-content hash'],
                        ['exact_cleaned', 'Exact cleaned-content hash'],
                        ['normalized_sections', 'Normalized section fingerprint'],
                        ['near_duplicate', 'Near-duplicate SimHash'],
                      ] as const
                    ).map(([key, label]) => (
                      <label className={CHECK_ROW} key={key}>
                        <Checkbox
                          checked={selectedDuplicate[key]}
                          onCheckedChange={(checked) =>
                            updateNode(selected.id, (node) =>
                              node.type === 'clean'
                                ? {
                                    ...node,
                                    duplicate_policy: {
                                      ...selectedDuplicate,
                                      [key]: checked === true,
                                    },
                                  }
                                : node,
                            )
                          }
                        />
                        {label}
                      </label>
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
                    <p className={HINT}>
                      Canonical order: pinned source, connector priority, first stable identity,
                      then lexical identity. Overrides are saved in a new pipeline version.
                    </p>
                  </div>
                </details>
                <details className={DETAILS}>
                  <summary className={SUMMARY}>Sensitive-data policy</summary>
                  <div className={STACK}>
                    <label className={CHECK_ROW}>
                      <Checkbox
                        checked={selectedSensitive.enabled}
                        onCheckedChange={(checked) =>
                          updateNode(selected.id, (node) =>
                            node.type === 'clean'
                              ? {
                                  ...node,
                                  sensitive_data_policy: {
                                    ...selectedSensitive,
                                    enabled: checked === true,
                                  },
                                }
                              : node,
                          )
                        }
                      />
                      Redact sensitive values before chunking and embedding
                    </label>
                    <p className={HINT}>
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
                    <p className={HINT}>
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
          <div className={STACK}>
            <p className={HINT}>
              Convert each passage into a vector for retrieval. The embedding model and dimensions
              must match the destination index.
            </p>
            <dl className={FACTS}>
              <dt>Provider</dt>
              <dd>{selected.provider}</dd>
              <dt>Model</dt>
              <dd>{selected.model}</dd>
              <dt>Dimensions</dt>
              <dd>{selected.dimensions}</dd>
              <dt>Configuration version</dt>
              <dd>{selected.config_version}</dd>
            </dl>
            <p className={HINT}>
              Model configuration is managed by the backend and saved with this pipeline version.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
