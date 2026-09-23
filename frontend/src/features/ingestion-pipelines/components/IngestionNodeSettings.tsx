import { CircleAlert, Database } from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import type { ConnectionSettings, SourceConnection } from '../../connections/model';
import type { Document, KnowledgeSet } from '../../documents/model';
import { ingestionStageLabels as labels } from '../editorModel';
import type { ExistingFilesConfig, IngestionNode, IngestionPipelineVersion } from '../model';
import { ConfluenceSettings, NotionSettings, S3Settings, WebsiteSettings } from './SourceSettings';

type SourceKind = 'existing_files' | 'website' | 's3' | 'notion' | 'confluence';

export function IngestionNodeSettings({
  projectId,
  selected,
  selectedNode,
  nodes,
  dirty,
  saved,
  validation,
  connectionSettings,
  connections,
  documents,
  knowledgeSets,
  websiteSource,
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
  connectionSettings?: ConnectionSettings;
  connections: SourceConnection[];
  documents: Document[];
  knowledgeSets: KnowledgeSet[];
  websiteSource: boolean;
  updateNode: (id: string, update: (node: IngestionNode) => IngestionNode) => void;
  changeSourceKind: (nodeId: string, kind: SourceKind) => void;
}) {
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
                  Choose explicit project files. Only successfully processed files can run.
                </p>
                {documents.map((document) => {
                  const sourceConfig = selected.config as ExistingFilesConfig;
                  const checked = sourceConfig.document_ids.includes(document.id);
                  const disabled = document.latest_run?.status !== 'succeeded';
                  return (
                    <label className="ingestion-document-option" key={document.id}>
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
                                  },
                                }
                              : node,
                          )
                        }
                      />
                      <span>
                        <strong>{document.filename}</strong>
                        <small>
                          {disabled
                            ? `Processing ${document.latest_run?.status ?? 'required'}`
                            : `${document.latest_run?.chunk_count ?? 0} chunks ready`}
                        </small>
                      </span>
                    </label>
                  );
                })}
                {documents.length === 0 && (
                  <p>No uploaded documents. Add and process files in Knowledge Base first.</p>
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
              Character windows preserve neighboring context. More overlap can improve recall, but
              creates more vectors and increases retrieval noise and cost.
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
                    selected.size === size && selected.overlap === overlap ? 'default' : 'outline'
                  }
                  onClick={() =>
                    updateNode(selected.id, (node) =>
                      node.type === 'chunk'
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
                aria-invalid={selected.size < 100 || selected.size > 10000}
                aria-describedby="chunk-size-help"
                onChange={(event) =>
                  updateNode(selected.id, (node) =>
                    node.type === 'chunk' ? { ...node, size: Number(event.target.value) } : node,
                  )
                }
              />
            </Label>
            <p id="chunk-size-help" className="field-hint">
              Enter 100–10,000 characters per chunk.
            </p>
            <Label>
              Overlap (characters)
              <Input
                type="number"
                min={0}
                value={selected.overlap}
                aria-invalid={selected.overlap < 0 || selected.overlap >= selected.size}
                aria-describedby="chunk-overlap-help"
                onChange={(event) =>
                  updateNode(selected.id, (node) =>
                    node.type === 'chunk' ? { ...node, overlap: Number(event.target.value) } : node,
                  )
                }
              />
            </Label>
            <p id="chunk-overlap-help" className="field-hint">
              Overlap must be at least 0 and smaller than the chunk size.
            </p>
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
              Extract readable text using the parser matched to each source’s media type. Source
              provenance stays attached to the extracted content.
            </p>
            <dl className="ingestion-stage-facts">
              <dt>Strategy</dt>
              <dd>{selected.strategy ?? 'media_type_registry'}</dd>
              <dt>Configuration version</dt>
              <dd>{selected.config_version ?? '1'}</dd>
            </dl>
          </div>
        )}
        {selected?.type === 'clean' && (
          <div className="field-stack">
            <p className="field-hint">
              Prepare extracted text before splitting it into searchable passages. These settings
              are recorded with the saved version.
            </p>
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
