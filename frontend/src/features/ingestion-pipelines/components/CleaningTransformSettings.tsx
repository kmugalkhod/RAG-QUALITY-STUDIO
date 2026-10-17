import { useState } from 'react';
import { Plus } from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { Checkbox } from '../../../components/ui/checkbox';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { cleaningStepNames as names, insertStep } from '../downstreamModel';
import type { CleaningTransform, IngestionNode } from '../model';
import { ListTextField } from './ListTextField';
import { FIELD_ERROR, FIELD_GRID, HINT, OPTION, STACK } from './settingsStyles';

type CleanNode = Extract<IngestionNode, { type: 'clean' }>;

const transformTypes = (Object.keys(names) as CleaningTransform['type'][]).filter(
  // Literal text has its own box on the Clean panel.
  (type) => type !== 'remove_literal_boilerplate',
);

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
      return { ...base, type, mode: 'conservative-compounds' };
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
        // Starts empty: an empty list is invalid until text is entered (spec 0012 A19).
        values: [],
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

/** Client checks of the step fields, keyed `steps.<index>.<field>` (spec 0012 A19, A20). */
export function cleaningStepProblems(node: CleanNode): Record<string, string> {
  return Object.fromEntries(
    (node.steps ?? []).flatMap((step, index) =>
      step.type === 'remove_literal_boilerplate' && step.enabled && step.values.length === 0
        ? [[`steps.${index}.values`, 'Enter at least one line of text to remove.']]
        : [],
    ),
  );
}

/**
 * The advanced list of cleaning steps (spec 0012 Part B): in their saved order, each with
 * its switch and fields, without reordering or deleting. A missing step can be added at
 * its place in the server order. Literal text is edited in the Clean panel's own box.
 */
export function CleaningTransformSettings({
  node,
  errors = {},
  update,
}: {
  node: CleanNode;
  /** Server errors of this node, keyed `clean` or `clean.steps.<index>[.<field>]`. */
  errors?: Record<string, string>;
  update: (node: CleanNode) => void;
}) {
  const problems = cleaningStepProblems(node);
  const errorOf = (key: string) => errors[`clean.${key}`] ?? problems[key];
  const [selectedType, setSelectedType] = useState('');
  const steps = node.steps ?? [];
  const available = transformTypes.filter((type) => !steps.some((step) => step.type === type));

  function updateStep(index: number, value: CleaningTransform) {
    const next = [...steps];
    next[index] = value;
    update({ ...node, steps: next });
  }

  return (
    <div className={STACK}>
      <p className={HINT}>Steps run from top to bottom in this saved order.</p>
      <ol className="flex flex-col gap-2" aria-label="Ordered cleaning transforms">
        {steps.map((step, index) => (
          <li
            key={step.id}
            className="flex min-w-0 flex-col gap-4 rounded-card border border-border bg-background p-4"
          >
            <div className="flex items-start justify-between gap-2">
              {step.type === 'preserve_structure' ? (
                // Protection always applies, so this step has no switch (spec 0012 A18).
                <span className="flex min-w-0 flex-col gap-1 text-sm text-foreground">
                  <strong className="font-medium">
                    {index + 1}. {names[step.type]}
                  </strong>
                  <small className="text-xs text-foreground-muted">
                    Always on: tables, lists, code, quotes and footnotes are never rewritten or
                    removed.
                  </small>
                </span>
              ) : (
                <label className="flex min-w-0 cursor-pointer items-start gap-3 text-sm text-foreground [&>[data-slot=checkbox]]:mt-1">
                  <Checkbox
                    checked={step.enabled}
                    onCheckedChange={(checked) =>
                      updateStep(index, { ...step, enabled: checked === true })
                    }
                  />
                  <span className="flex min-w-0 flex-col gap-1">
                    <strong className="font-medium">
                      {index + 1}. {names[step.type]}
                    </strong>
                    <small className="text-xs text-foreground-muted wrap-anywhere">
                      {step.type}
                    </small>
                  </span>
                </label>
              )}
            </div>
            {errors[`clean.steps.${index}`] && (
              <p role="alert" className={FIELD_ERROR}>
                {errors[`clean.steps.${index}`]}
              </p>
            )}
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
              <div className={FIELD_GRID}>
                <Label>
                  Minimum page ratio
                  <Input
                    type="number"
                    min={0.5}
                    max={1}
                    step={0.05}
                    value={step.minimum_page_ratio}
                    onChange={(event) =>
                      updateStep(index, {
                        ...step,
                        minimum_page_ratio: Number(event.target.value),
                      })
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
                <p className={HINT}>
                  {step.values.length} {step.values.length === 1 ? 'line' : 'lines'} of text, edited
                  in Text to remove above.
                </p>
                <ListTextField
                  label="Block types, one per line"
                  trim
                  values={step.block_types}
                  error={errorOf(`steps.${index}.block_types`)}
                  onChange={(values) =>
                    updateStep(index, {
                      ...step,
                      block_types: values as typeof step.block_types,
                    })
                  }
                />
              </>
            )}
            {step.type === 'website_selectors' && (
              <div className={FIELD_GRID}>
                <ListTextField
                  label="Include selectors"
                  trim
                  placeholder="main"
                  values={step.include}
                  error={errorOf(`steps.${index}.include`)}
                  onChange={(include) => updateStep(index, { ...step, include })}
                />
                <ListTextField
                  label="Exclude selectors"
                  trim
                  placeholder=".cookie-banner"
                  values={step.exclude}
                  error={errorOf(`steps.${index}.exclude`)}
                  onChange={(exclude) => updateStep(index, { ...step, exclude })}
                />
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
                  <label className={OPTION} key={field}>
                    <Checkbox
                      checked={step[field]}
                      onCheckedChange={(checked) =>
                        updateStep(index, { ...step, [field]: checked === true })
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
                      updateStep(index, {
                        ...step,
                        minimum_page_ratio: Number(event.target.value),
                      })
                    }
                  />
                </Label>
              </>
            )}
            {step.type === 'validate_useful_content' && (
              <div className={FIELD_GRID}>
                <Label>
                  Minimum characters
                  <Input
                    type="number"
                    min={1}
                    max={100000}
                    value={step.minimum_characters}
                    onChange={(event) =>
                      updateStep(index, {
                        ...step,
                        minimum_characters: Number(event.target.value),
                      })
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
                      updateStep(index, {
                        ...step,
                        maximum_characters: Number(event.target.value),
                      })
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
          <div className="flex items-center gap-2 [&>[data-slot=native-select-wrapper]]:min-w-0 [&>[data-slot=native-select-wrapper]]:flex-1">
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
                update({ ...node, steps: insertStep(steps, transform) });
                setSelectedType('');
              }}
            >
              <Plus aria-hidden="true" /> Add
            </Button>
          </div>
        </Label>
      )}
    </div>
  );
}
