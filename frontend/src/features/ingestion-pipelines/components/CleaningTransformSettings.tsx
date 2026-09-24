import { useState } from 'react';
import { ArrowDown, ArrowUp, Plus, RotateCcw, Trash2 } from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { Textarea } from '../../../components/ui/textarea';
import type { CleaningTransform, ExtractionCapabilities, IngestionNode } from '../model';

type CleanNode = Extract<IngestionNode, { type: 'clean' }>;

const names: Record<CleaningTransform['type'], string> = {
  preserve_structure: 'Preserve structured blocks',
  unicode_normalize: 'Normalize Unicode',
  remove_control_characters: 'Remove unsupported controls',
  reflow_pdf_lines: 'Reflow PDF lines',
  dehyphenate: 'Dehyphenate line endings',
  remove_repeated_headers_footers: 'Remove repeated headers and footers',
  remove_empty_blocks: 'Remove empty blocks',
  remove_literal_boilerplate: 'Remove literal boilerplate',
  website_selectors: 'Apply Website selectors',
  website_main_content: 'Keep Website main content',
  validate_useful_content: 'Validate useful content',
};

const transformTypes = Object.keys(names) as CleaningTransform['type'][];

function newTransform(type: CleaningTransform['type']): CleaningTransform {
  const base = { id: type.replaceAll('_', '-'), type, enabled: true };
  switch (type) {
    case 'preserve_structure':
      return {
        ...base,
        type,
        block_types: ['table', 'list_item', 'code', 'quote', 'footnote'],
      };
    case 'unicode_normalize':
      return { ...base, type, form: 'NFC' };
    case 'remove_control_characters':
      return { ...base, type };
    case 'reflow_pdf_lines':
      return { ...base, type, block_types: ['paragraph', 'unknown'] };
    case 'dehyphenate':
      return { ...base, type, mode: 'conservative' };
    case 'remove_repeated_headers_footers':
      return {
        ...base,
        type,
        minimum_page_ratio: 0.6,
        minimum_pages: 3,
        margin_ratio: 0.12,
      };
    case 'remove_empty_blocks':
      return { ...base, type, minimum_characters: 1 };
    case 'remove_literal_boilerplate':
      return {
        ...base,
        type,
        values: ['Replace this literal'],
        block_types: ['paragraph', 'unknown'],
      };
    case 'website_selectors':
      return { ...base, type, include: [], exclude: ['.cookie-banner'] };
    case 'website_main_content':
      return {
        ...base,
        type,
        remove_semantic_chrome: true,
        remove_cookie_banners: true,
        remove_repeated_site_chrome: true,
        minimum_page_ratio: 0.6,
      };
    case 'validate_useful_content':
      return { ...base, type, minimum_characters: 1, maximum_characters: 2_000_000 };
  }
}

function lines(value: string) {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
}

export function CleaningTransformSettings({
  node,
  capabilities,
  update,
}: {
  node: CleanNode;
  capabilities?: ExtractionCapabilities;
  update: (node: CleanNode) => void;
}) {
  const [selectedType, setSelectedType] = useState('');
  const steps = node.steps ?? [];
  const supported = capabilities?.cleaning_profiles?.[0];
  const available = transformTypes.filter((type) => !steps.some((step) => step.type === type));

  function updateStep(index: number, value: CleaningTransform) {
    const next = [...steps];
    next[index] = value;
    update({ ...node, steps: next });
  }

  function move(index: number, offset: -1 | 1) {
    const target = index + offset;
    if (target < 0 || target >= steps.length) {
      return;
    }
    const next = [...steps];
    [next[index], next[target]] = [next[target], next[index]];
    update({ ...node, steps: next });
  }

  function useStructureProfile() {
    if (!supported) {
      return;
    }
    update({
      ...node,
      profile: supported.id,
      config_version: supported.config_version,
      steps: structuredClone(supported.steps),
      normalize_whitespace: true,
      repeated_boilerplate: [],
    });
  }

  if (node.profile !== 'structure-aware-v1') {
    return (
      <div className="field-stack">
        <p className="field-hint">
          This saved version uses the compatibility cleaner. Upgrade the draft to configure ordered,
          attributable transforms; historical versions remain unchanged.
        </p>
        <Button type="button" variant="outline" disabled={!supported} onClick={useStructureProfile}>
          Use {supported?.name ?? 'structure-aware profile'}
        </Button>
        <dl className="ingestion-stage-facts">
          <dt>Normalize whitespace</dt>
          <dd>{node.normalize_whitespace === false ? 'Off' : 'On'}</dd>
          <dt>Exact-content deduplication</dt>
          <dd>{node.exact_content_deduplication === false ? 'Off' : 'On'}</dd>
          <dt>Literal removals</dt>
          <dd>{node.repeated_boilerplate?.length ?? 0}</dd>
        </dl>
      </div>
    );
  }

  return (
    <div className="field-stack cleaning-transform-settings">
      <div className="cleaning-profile-heading">
        <div>
          <strong>{supported?.name ?? 'Structure-aware standard'}</strong>
          <p className="field-hint">Transforms run from top to bottom in this saved order.</p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={!supported}
          onClick={useStructureProfile}
        >
          <RotateCcw size={14} aria-hidden="true" />
          Reset profile
        </Button>
      </div>

      <ol className="cleaning-transform-list" aria-label="Ordered cleaning transforms">
        {steps.map((step, index) => (
          <li key={step.id} className="cleaning-transform-card">
            <div className="cleaning-transform-heading">
              <label>
                <input
                  type="checkbox"
                  checked={step.enabled}
                  onChange={(event) =>
                    updateStep(index, { ...step, enabled: event.target.checked })
                  }
                />
                <span>
                  <strong>
                    {index + 1}. {names[step.type]}
                  </strong>
                  <small>{step.type}</small>
                </span>
              </label>
              <div className="cleaning-transform-actions">
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label={`Move ${names[step.type]} up`}
                  disabled={index === 0}
                  onClick={() => move(index, -1)}
                >
                  <ArrowUp size={14} />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label={`Move ${names[step.type]} down`}
                  disabled={index === steps.length - 1}
                  onClick={() => move(index, 1)}
                >
                  <ArrowDown size={14} />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label={`Remove ${names[step.type]}`}
                  onClick={() =>
                    update({ ...node, steps: steps.filter((_, item) => item !== index) })
                  }
                >
                  <Trash2 size={14} />
                </Button>
              </div>
            </div>
            {step.type === 'unicode_normalize' && (
              <Label>
                Unicode form
                <NativeSelect
                  value={step.form}
                  onChange={(event) =>
                    updateStep(index, { ...step, form: event.target.value as 'NFC' | 'NFKC' })
                  }
                >
                  <NativeSelectOption value="NFC">NFC · canonical</NativeSelectOption>
                  <NativeSelectOption value="NFKC">
                    NFKC · compatibility, may change meaning
                  </NativeSelectOption>
                </NativeSelect>
              </Label>
            )}
            {step.type === 'remove_repeated_headers_footers' && (
              <div className="cleaning-transform-grid">
                <Label>
                  Minimum page ratio
                  <Input
                    type="number"
                    min={0.5}
                    max={1}
                    step={0.05}
                    value={step.minimum_page_ratio}
                    onChange={(event) =>
                      updateStep(index, { ...step, minimum_page_ratio: Number(event.target.value) })
                    }
                  />
                </Label>
                <Label>
                  Minimum pages
                  <Input
                    type="number"
                    min={3}
                    max={100}
                    value={step.minimum_pages}
                    onChange={(event) =>
                      updateStep(index, { ...step, minimum_pages: Number(event.target.value) })
                    }
                  />
                </Label>
                <Label>
                  Page margin ratio
                  <Input
                    type="number"
                    min={0.01}
                    max={0.25}
                    step={0.01}
                    value={step.margin_ratio}
                    onChange={(event) =>
                      updateStep(index, { ...step, margin_ratio: Number(event.target.value) })
                    }
                  />
                </Label>
              </div>
            )}
            {step.type === 'remove_empty_blocks' && (
              <Label>
                Minimum non-space characters
                <Input
                  type="number"
                  min={1}
                  max={100}
                  value={step.minimum_characters}
                  onChange={(event) =>
                    updateStep(index, { ...step, minimum_characters: Number(event.target.value) })
                  }
                />
              </Label>
            )}
            {step.type === 'remove_literal_boilerplate' && (
              <>
                <Label>
                  Exact literals
                  <Textarea
                    value={step.values.join('\n')}
                    onChange={(event) =>
                      updateStep(index, { ...step, values: lines(event.target.value) })
                    }
                  />
                </Label>
                <Label>
                  Block types, one per line
                  <Textarea
                    value={step.block_types.join('\n')}
                    onChange={(event) =>
                      updateStep(index, { ...step, block_types: lines(event.target.value) })
                    }
                  />
                </Label>
              </>
            )}
            {step.type === 'website_selectors' && (
              <div className="cleaning-transform-grid">
                <Label>
                  Include selectors
                  <Textarea
                    placeholder="main"
                    value={step.include.join('\n')}
                    onChange={(event) =>
                      updateStep(index, { ...step, include: lines(event.target.value) })
                    }
                  />
                </Label>
                <Label>
                  Exclude selectors
                  <Textarea
                    placeholder=".cookie-banner"
                    value={step.exclude.join('\n')}
                    onChange={(event) =>
                      updateStep(index, { ...step, exclude: lines(event.target.value) })
                    }
                  />
                </Label>
              </div>
            )}
            {step.type === 'website_main_content' && (
              <>
                {(
                  [
                    ['remove_semantic_chrome', 'Remove navigation, banners and semantic chrome'],
                    ['remove_cookie_banners', 'Remove cookie and consent banners'],
                    ['remove_repeated_site_chrome', 'Remove cross-page repeated site chrome'],
                  ] as const
                ).map(([field, label]) => (
                  <label className="ingestion-document-option" key={field}>
                    <input
                      type="checkbox"
                      checked={step[field]}
                      onChange={(event) =>
                        updateStep(index, { ...step, [field]: event.target.checked })
                      }
                    />
                    <span>
                      <strong>{label}</strong>
                    </span>
                  </label>
                ))}
                <Label>
                  Repeated-page ratio
                  <Input
                    type="number"
                    min={0.5}
                    max={1}
                    step={0.05}
                    value={step.minimum_page_ratio}
                    onChange={(event) =>
                      updateStep(index, { ...step, minimum_page_ratio: Number(event.target.value) })
                    }
                  />
                </Label>
              </>
            )}
            {step.type === 'validate_useful_content' && (
              <div className="cleaning-transform-grid">
                <Label>
                  Minimum characters
                  <Input
                    type="number"
                    min={1}
                    max={100000}
                    value={step.minimum_characters}
                    onChange={(event) =>
                      updateStep(index, { ...step, minimum_characters: Number(event.target.value) })
                    }
                  />
                </Label>
                <Label>
                  Maximum characters
                  <Input
                    type="number"
                    min={1}
                    max={2000000}
                    value={step.maximum_characters}
                    onChange={(event) =>
                      updateStep(index, { ...step, maximum_characters: Number(event.target.value) })
                    }
                  />
                </Label>
              </div>
            )}
          </li>
        ))}
      </ol>

      {available.length > 0 && (
        <Label>
          Add transform
          <div className="cleaning-transform-add">
            <NativeSelect
              value={selectedType}
              aria-label="Transform to add"
              onChange={(event) => setSelectedType(event.target.value)}
            >
              <NativeSelectOption value="" disabled>
                Choose a transform
              </NativeSelectOption>
              {available.map((type) => (
                <NativeSelectOption key={type} value={type}>
                  {names[type]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <Button
              type="button"
              variant="outline"
              disabled={!selectedType}
              onClick={() => {
                if (!selectedType) {
                  return;
                }
                const transform = newTransform(selectedType as CleaningTransform['type']);
                const validation = steps.findIndex(
                  (step) => step.type === 'validate_useful_content',
                );
                const next = [...steps];
                next.splice(validation < 0 ? next.length : validation, 0, transform);
                update({
                  ...node,
                  steps: next,
                });
                setSelectedType('');
              }}
            >
              <Plus size={14} /> Add
            </Button>
          </div>
        </Label>
      )}

      <label className="ingestion-document-option">
        <input
          type="checkbox"
          checked={node.exact_content_deduplication !== false}
          onChange={(event) =>
            update({ ...node, exact_content_deduplication: event.target.checked })
          }
        />
        <span>
          <strong>Exact-content deduplication</strong>
          <small>
            Recorded as a separate final removal audit; near-duplicate clustering is not enabled.
          </small>
        </span>
      </label>
    </div>
  );
}
