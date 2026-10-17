import { useId, useState } from 'react';

import { Callout, SUMMARY } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import { Checkbox } from '../../../components/ui/checkbox';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { RadioGroup, RadioGroupItem } from '../../../components/ui/radio-group';
import {
  aboutWords,
  chunkDifferences,
  passageSize,
  passageTarget,
  resetChunkAdvanced,
  withPassageSize,
  type PassageSize,
} from '../downstreamModel';
import {
  chunkFieldProblems,
  chunkUpgradeAvailable,
  chunkUpgradeChanges,
  currentChunkVersions,
  defaultChunkNode,
  embeddingInputBytes,
  passageLimitFields,
} from '../editorModel';
import type { ChunkNode, ExtractionCapabilities } from '../model';
import { CHECK_ROW, DETAILS, FIELD_ERROR, HINT, STACK } from './settingsStyles';

type Algorithm = 'character_window' | 'section_token' | 'parent_child';
type TokenChunk = Extract<ChunkNode, { algorithm: 'section_token' | 'parent_child' }>;

const methodNames: Record<Algorithm, string> = {
  section_token: 'Section-aware',
  parent_child: 'Parent and child',
  character_window: 'Character window',
};

const sizeNames: Record<PassageSize, string> = {
  small: 'Small',
  medium: 'Medium',
  large: 'Large',
};

const CHOICE =
  'flex cursor-pointer items-start gap-3 rounded-control border border-border bg-background p-4 text-sm text-foreground has-data-[state=checked]:border-accent [&>button]:mt-1';

type NumberFieldProps = {
  label: string;
  field: string;
  value: number;
  minimum: number;
  maximum: number;
  error?: string;
  onChange: (value: number) => void;
};

/** A whole-number field whose empty or partial value is kept invalid, never read as 0. */
function NumberField({ label, field, value, minimum, maximum, error, onChange }: NumberFieldProps) {
  const id = useId();
  return (
    <div className="flex flex-col gap-2">
      <Label>
        {label}
        <Input
          type="number"
          inputMode="numeric"
          name={field}
          min={minimum}
          max={maximum}
          step={1}
          value={Number.isFinite(value) ? value : ''}
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : undefined}
          onChange={(event) =>
            onChange(event.target.value === '' ? Number.NaN : Number(event.target.value))
          }
        />
      </Label>
      {error && (
        <small id={`${id}-error`} role="alert" className={FIELD_ERROR}>
          {error}
        </small>
      )}
    </div>
  );
}

const tokenFields = {
  section_token: [
    ['Target size (bytes)', 'target_tokens', 64, 8192],
    ['Maximum size (bytes)', 'maximum_tokens', 64, 16384],
    ['Overlap (bytes)', 'overlap_tokens', 0, 4096],
  ],
  parent_child: [
    ['Child target size (bytes)', 'child_target_tokens', 64, 4096],
    ['Child maximum size (bytes)', 'child_maximum_tokens', 64, 8192],
    ['Child overlap (bytes)', 'child_overlap_tokens', 0, 2048],
    ['Parent target size (bytes)', 'parent_target_tokens', 128, 16384],
    ['Parent maximum size (bytes)', 'parent_maximum_tokens', 128, 32768],
  ],
} as const;

/**
 * The Chunk panel (spec 0012 Part B and Slice 2): the method and a passage size are the
 * visible choices; exact byte sizes, overlap and section titles are under Advanced with
 * "N changed" and Reset. Every field shows its own error, switching the method can be
 * undone, and sizes that can exceed the embedding provider's limit are flagged.
 */
export function ChunkSettings({
  node,
  capabilities,
  websiteSource,
  serverErrors,
  preview,
  update,
}: {
  node: ChunkNode;
  capabilities?: ExtractionCapabilities;
  websiteSource: boolean;
  /** Server errors of this node, keyed `chunk.<field>`. */
  serverErrors: Record<string, string>;
  /** Starts a preview of the draft; `reason` says why it cannot start now. */
  preview?: { run: () => void; reason?: string };
  update: (node: ChunkNode) => void;
}) {
  const id = useId();
  const [replaced, setReplaced] = useState<ChunkNode>();
  const [open, setOpen] = useState(false);
  const algorithm: Algorithm = node.algorithm ?? 'character_window';
  const problems = chunkFieldProblems(node);
  const errorOf = (field: string) => serverErrors[`chunk.${field}`] ?? problems[field];
  const limitField = passageLimitFields[algorithm];
  const tooLarge =
    Number.isInteger((node as unknown as Record<string, number>)[limitField]) &&
    problems[limitField]?.startsWith('At most');
  const size = passageSize(node);
  const differences = chunkDifferences(node);
  const hasError =
    Object.keys(problems).length > 0 ||
    Object.keys(serverErrors).some((key) => key.startsWith('chunk.'));

  function set(field: string, value: number) {
    setReplaced(undefined);
    update({ ...node, [field]: value } as ChunkNode);
  }

  function choose(next: Algorithm) {
    if (next === algorithm) {
      return;
    }
    setReplaced(node);
    update(defaultChunkNode(node.id, next, capabilities));
  }

  function resetSizes() {
    const defaults = defaultChunkNode(node.id, algorithm, capabilities);
    update({ ...defaults, config_version: node.config_version ?? defaults.config_version });
  }

  return (
    <div className={STACK}>
      <p className={HINT}>
        Splits cleaned text into passages that search can find and answers can cite.
      </p>
      {websiteSource && (
        <Callout>
          <p>
            To try new chunk settings without another Website request: save a new version, choose an
            exact ready snapshot, then select <strong>Reprocess saved source</strong>.
          </p>
        </Callout>
      )}
      <RadioGroup
        aria-label="Chunking method"
        value={algorithm === 'character_window' ? '' : algorithm}
        onValueChange={(value) => choose(value as Algorithm)}
      >
        <label className={CHOICE}>
          <RadioGroupItem value="section_token" aria-describedby={`${id}-section`} />
          <span className="flex min-w-0 flex-col gap-1">
            <strong className="font-medium">Section-aware (recommended)</strong>
            <small id={`${id}-section`} className="text-xs text-foreground-muted">
              Keeps headings and the text under them together.
            </small>
          </span>
        </label>
        <label className={CHOICE}>
          <RadioGroupItem value="parent_child" aria-describedby={`${id}-parent`} />
          <span className="flex min-w-0 flex-col gap-1">
            <strong className="font-medium">Parent and child</strong>
            <small id={`${id}-parent`} className="text-xs text-foreground-muted">
              Better for tables and short facts: search finds a small passage, answers get the
              larger one around it.
            </small>
          </span>
        </label>
      </RadioGroup>
      {replaced && (
        <div role="status" className="flex flex-wrap items-center gap-2 text-sm text-foreground">
          <span>
            Switched to {methodNames[algorithm]} with its recommended sizes; your{' '}
            {methodNames[replaced.algorithm ?? 'character_window']} settings were replaced.
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              update(replaced);
              setReplaced(undefined);
            }}
          >
            Undo
          </Button>
        </div>
      )}
      {algorithm === 'character_window' && (
        <Callout role="note" title="Saved with the character window">
          <p>
            This version splits text into fixed character windows, the original method, so earlier
            runs reproduce. Its sizes are under Advanced. Choosing a method above creates a new
            version when you save; its next run chunks and embeds documents again.
          </p>
        </Callout>
      )}
      {(node.algorithm === 'section_token' || node.algorithm === 'parent_child') && (
        <fieldset className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
          <legend className="mb-2 text-sm font-medium text-foreground">Passage size</legend>
          <RadioGroup
            aria-label="Passage size"
            className="flex flex-col gap-2"
            value={size ?? ''}
            onValueChange={(value) => {
              setReplaced(undefined);
              update(withPassageSize(node, value as PassageSize));
            }}
          >
            {(['small', 'medium', 'large'] as const).map((value) => (
              <label key={value} className={CHOICE}>
                <RadioGroupItem value={value} />
                <span className="flex min-w-0 flex-col gap-1">
                  <strong className="font-medium">
                    {sizeNames[value]}
                    {value === 'medium' ? ' (recommended)' : ''}
                  </strong>
                  <small className="text-xs text-foreground-muted">
                    about {aboutWords(passageTarget(node.algorithm, value))} words
                  </small>
                </span>
              </label>
            ))}
          </RadioGroup>
          {!size && <p className={HINT}>Custom sizes, listed under Advanced.</p>}
        </fieldset>
      )}
      {(algorithm === 'section_token' || algorithm === 'parent_child') &&
        chunkUpgradeAvailable(node) && (
          <Callout
            role="note"
            title={`Saved with ${
              node.config_version ??
              (algorithm === 'section_token' ? 'section-token-v1' : 'parent-child-v1')
            }`}
          >
            <p>
              This version keeps its original chunking so earlier runs reproduce. The current
              chunking, {currentChunkVersions[algorithm]}:
            </p>
            <ul className="list-disc pl-4">
              {chunkUpgradeChanges(node).map((change) => (
                <li key={change}>{change}</li>
              ))}
            </ul>
            <p>
              Saving the upgrade creates a new pipeline version, and its next run chunks and embeds
              documents again.
            </p>
            <div>
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  update({
                    ...node,
                    config_version:
                      currentChunkVersions[algorithm as 'section_token' | 'parent_child'],
                  } as ChunkNode)
                }
              >
                Upgrade chunking
              </Button>
            </div>
          </Callout>
        )}
      {tooLarge && (
        <Callout tone="warning" role="note" title="Passages can be too large to embed">
          <p>
            With these sizes a passage and its section heading can exceed the embedding
            provider&apos;s {embeddingInputBytes.toLocaleString('en-US')}-byte limit. A run stops at
            the Chunk stage when that happens, before any embedding is paid for.
          </p>
          <div>
            <Button type="button" variant="outline" onClick={resetSizes}>
              Reset sizes to recommended
            </Button>
          </div>
        </Callout>
      )}
      {preview && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={!!preview.reason}
            aria-describedby={preview.reason ? `${id}-preview` : undefined}
            onClick={preview.run}
          >
            Preview chunks
          </Button>
          {preview.reason && (
            <small id={`${id}-preview`} className="text-xs text-foreground-muted">
              {preview.reason}
            </small>
          )}
        </div>
      )}
      <details
        className={DETAILS}
        open={open || hasError}
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary className={SUMMARY}>
          <span>Advanced chunking settings</span>
          <small className={HINT}>
            · {differences.length === 0 ? 'recommended' : `${differences.length} changed`}
          </small>
        </summary>
        <div className={STACK}>
          {(node.algorithm === 'section_token' || node.algorithm === 'parent_child') && (
            <>
              <p className={HINT}>
                {differences.length === 0
                  ? 'Using recommended settings. Sizes are UTF-8 bytes; an English word is about six.'
                  : `${differences.length} ${
                      differences.length === 1 ? 'setting differs' : 'settings differ'
                    } from recommended: ${differences.join(', ')}.`}
              </p>
              {differences.length > 0 && (
                <div>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => update(resetChunkAdvanced(node as TokenChunk))}
                  >
                    Reset to recommended
                  </Button>
                </div>
              )}
              {tokenFields[node.algorithm].map(([label, field, minimum, maximum]) => (
                <NumberField
                  key={field}
                  label={label}
                  field={field}
                  value={(node as unknown as Record<string, number>)[field]}
                  minimum={minimum}
                  maximum={maximum}
                  error={errorOf(field)}
                  onChange={(value) => set(field, value)}
                />
              ))}
              {node.algorithm === 'parent_child' && (
                <p className={HINT}>
                  Child passages are embedded. Answers get their saved parent passage as evidence.
                </p>
              )}
              <label className={CHECK_ROW}>
                <Checkbox
                  checked={node.add_heading_context}
                  onCheckedChange={(checked) =>
                    update({ ...node, add_heading_context: checked === true } as ChunkNode)
                  }
                />
                <span>
                  Help search find passages by their section title
                  <small className="block text-xs text-foreground-muted">
                    The title is added to the text that is embedded; it is not shown in answers.
                  </small>
                </span>
              </label>
            </>
          )}
          {node.algorithm !== 'section_token' && node.algorithm !== 'parent_child' && (
            <>
              <div className="flex flex-wrap gap-2" role="group" aria-label="Chunking presets">
                {(
                  [
                    ['Precise', 600, 80],
                    ['Balanced', 1000, 120],
                    ['Broad context', 1600, 200],
                  ] as const
                ).map(([label, value, overlap]) => (
                  <Button
                    key={label}
                    type="button"
                    size="sm"
                    variant="outline"
                    className="aria-pressed:border-accent aria-pressed:text-accent"
                    aria-pressed={node.size === value && node.overlap === overlap}
                    onClick={() => update({ ...node, size: value, overlap })}
                  >
                    {label}
                  </Button>
                ))}
              </div>
              <NumberField
                label="Chunk size (characters)"
                field="size"
                value={node.size}
                minimum={100}
                maximum={10000}
                error={errorOf('size')}
                onChange={(value) => set('size', value)}
              />
              <NumberField
                label="Overlap (characters)"
                field="overlap"
                value={node.overlap}
                minimum={0}
                maximum={9999}
                error={errorOf('overlap')}
                onChange={(value) => set('overlap', value)}
              />
            </>
          )}
        </div>
      </details>
    </div>
  );
}
