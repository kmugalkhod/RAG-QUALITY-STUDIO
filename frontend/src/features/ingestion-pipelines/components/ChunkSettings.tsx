import { useId, useState } from 'react';

import { Callout } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import { Checkbox } from '../../../components/ui/checkbox';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import {
  chunkFieldProblems,
  chunkUpgradeAvailable,
  currentChunkVersions,
  defaultChunkNode,
  embeddingInputBytes,
  passageLimitFields,
} from '../editorModel';
import type { ChunkNode, ExtractionCapabilities } from '../model';
import { CHECK_ROW, FIELD_ERROR, HINT, STACK } from './settingsStyles';

type Algorithm = 'character_window' | 'section_token' | 'parent_child';

const methodNames: Record<Algorithm, string> = {
  section_token: 'Section-aware tokens',
  parent_child: 'Parent and child',
  character_window: 'Character window (compatibility)',
};

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

/**
 * Chunk settings (spec 0012 Slice 2): every field shows its own client or server error,
 * switching the method starts from the server's recommended sizes and can be undone, and
 * sizes that can exceed the embedding provider's limit are flagged with a one-click reset.
 */
export function ChunkSettings({
  node,
  capabilities,
  websiteSource,
  serverErrors,
  update,
}: {
  node: ChunkNode;
  capabilities?: ExtractionCapabilities;
  websiteSource: boolean;
  /** Server errors of this node, keyed `chunk.<field>`. */
  serverErrors: Record<string, string>;
  update: (node: ChunkNode) => void;
}) {
  const [replaced, setReplaced] = useState<ChunkNode>();
  const algorithm: Algorithm = node.algorithm ?? 'character_window';
  const problems = chunkFieldProblems(node);
  const errorOf = (field: string) => serverErrors[`chunk.${field}`] ?? problems[field];
  const limitField = passageLimitFields[algorithm];
  const tooLarge =
    Number.isInteger((node as unknown as Record<string, number>)[limitField]) &&
    problems[limitField]?.startsWith('At most');

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
        Choose the saved chunking algorithm used for this index variant. Token limits use the stable
        UTF-8 byte tokenizer, a conservative model-independent upper bound.
      </p>
      {websiteSource && (
        <Callout>
          <p>
            To try new chunk settings without another Website request: save a new version, choose an
            exact ready snapshot, then select <strong>Reprocess saved source</strong>.
          </p>
        </Callout>
      )}
      <Label>
        Chunking algorithm
        <NativeSelect
          value={algorithm}
          onChange={(event) => choose(event.target.value as Algorithm)}
        >
          <NativeSelectOption value="section_token">{methodNames.section_token}</NativeSelectOption>
          <NativeSelectOption value="parent_child">{methodNames.parent_child}</NativeSelectOption>
          <NativeSelectOption value="character_window">
            {methodNames.character_window}
          </NativeSelectOption>
        </NativeSelect>
      </Label>
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
              chunking, {currentChunkVersions[algorithm]}, joins a short piece on a page, such as a
              chart label or callout read as a heading, to the passage before it, so it is no longer
              a passage of a few words that search rarely finds. Saving the upgrade creates a new
              pipeline version, and its next run chunks and embeds documents again.
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
      {node.algorithm === 'section_token' ? (
        <>
          <NumberField
            label="Target tokens"
            field="target_tokens"
            value={node.target_tokens}
            minimum={64}
            maximum={8192}
            error={errorOf('target_tokens')}
            onChange={(value) => set('target_tokens', value)}
          />
          <NumberField
            label="Hard maximum tokens"
            field="maximum_tokens"
            value={node.maximum_tokens}
            minimum={64}
            maximum={16384}
            error={errorOf('maximum_tokens')}
            onChange={(value) => set('maximum_tokens', value)}
          />
          <NumberField
            label="Overlap tokens"
            field="overlap_tokens"
            value={node.overlap_tokens}
            minimum={0}
            maximum={4096}
            error={errorOf('overlap_tokens')}
            onChange={(value) => set('overlap_tokens', value)}
          />
        </>
      ) : node.algorithm === 'parent_child' ? (
        <>
          {(
            [
              ['Child target tokens', 'child_target_tokens', 64, 4096],
              ['Child hard maximum tokens', 'child_maximum_tokens', 64, 8192],
              ['Child overlap tokens', 'child_overlap_tokens', 0, 2048],
              ['Parent target tokens', 'parent_target_tokens', 128, 16384],
              ['Parent hard maximum tokens', 'parent_maximum_tokens', 128, 32768],
            ] as const
          ).map(([label, field, minimum, maximum]) => (
            <NumberField
              key={field}
              label={label}
              field={field}
              value={node[field]}
              minimum={minimum}
              maximum={maximum}
              error={errorOf(field)}
              onChange={(value) => set(field, value)}
            />
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
                aria-pressed={node.size === size && node.overlap === overlap}
                onClick={() => update({ ...node, size, overlap })}
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
      {'add_heading_context' in node && (
        <label className={CHECK_ROW}>
          <Checkbox
            checked={node.add_heading_context}
            onCheckedChange={(checked) =>
              update({ ...node, add_heading_context: checked === true } as ChunkNode)
            }
          />
          Add heading context to embedding text only
        </label>
      )}
    </div>
  );
}
