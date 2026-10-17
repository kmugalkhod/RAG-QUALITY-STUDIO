import { useState } from 'react';

import { Callout, SUMMARY } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import { Checkbox } from '../../../components/ui/checkbox';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import {
  cleanDifferences,
  cleanLiterals,
  recommendedCleanSteps,
  redactionOn,
  resetCleanAdvanced,
  setCleanLiterals,
} from '../downstreamModel';
import {
  cleanUpgradeChanges,
  defaultDuplicatePolicy,
  defaultSensitiveDataPolicy,
} from '../editorModel';
import type { ExtractionCapabilities, IngestionNode } from '../model';
import { CleaningTransformSettings, cleaningStepProblems } from './CleaningTransformSettings';
import { ListTextField } from './ListTextField';
import { CHECK_ROW, DETAILS, FACTS, FIELD_ERROR, HINT, OPTION, STACK } from './settingsStyles';

type CleanNode = Extract<IngestionNode, { type: 'clean' }>;

const redactionNames: Record<string, string> = {
  email: 'Email addresses',
  phone: 'Phone numbers',
  ip_address: 'IP addresses',
  government_id: 'Government IDs',
  payment_card: 'Payment card numbers',
  api_secret: 'API keys and secrets',
};

/**
 * The Clean panel (spec 0012 Part B): one sentence of what runs, the text to remove and
 * the redaction switch (D9); the step list, duplicate handling, length limits and
 * redaction rules are under Advanced with "N changed" and Reset to recommended.
 */
export function CleanSettings({
  node,
  capabilities,
  errors,
  update,
}: {
  node: CleanNode;
  capabilities?: ExtractionCapabilities;
  /** Server errors of this node, keyed `clean` or `clean.steps.<index>[.<field>]`. */
  errors: Record<string, string>;
  update: (node: CleanNode) => void;
}) {
  const literalIndex = (node.steps ?? []).findIndex(
    (step) => step.type === 'remove_literal_boilerplate',
  );
  const literalError =
    literalIndex >= 0
      ? (errors[`clean.steps.${literalIndex}.values`] ??
        cleaningStepProblems(node)[`steps.${literalIndex}.values`])
      : undefined;
  const structure = node.profile === 'structure-aware-v1';
  const differences = cleanDifferences(node, capabilities);
  // A server error on an advanced setting opens the section, so it is never hidden.
  const advancedError = Object.keys(errors).some(
    (key) => key.startsWith('clean.') && !key.startsWith(`clean.steps.${literalIndex}.values`),
  );
  const [open, setOpen] = useState(false);
  const duplicate = node.duplicate_policy ?? structuredClone(defaultDuplicatePolicy);
  const sensitive = node.sensitive_data_policy ?? structuredClone(defaultSensitiveDataPolicy);
  const profile = capabilities?.cleaning_profiles?.[0];
  const upgradeChanges = structure ? cleanUpgradeChanges(node, capabilities) : [];

  return (
    <div className={STACK}>
      {errors.clean && (
        <p role="alert" className={FIELD_ERROR}>
          {errors.clean}
        </p>
      )}
      {!structure ? (
        <>
          <Callout role="note" title="Saved with the compatibility cleaner">
            <p>
              This version keeps its original cleaner so earlier runs reproduce. The current cleaner
              removes website menus, cookie banners and repeated page headers and keeps tables,
              lists and code. Saving the upgrade creates a new pipeline version, and its next run
              processes documents again.
            </p>
            <div>
              <Button
                type="button"
                variant="outline"
                disabled={!profile}
                onClick={() =>
                  profile &&
                  update({
                    ...node,
                    profile: profile.id,
                    config_version: profile.config_version,
                    steps: recommendedCleanSteps(capabilities),
                    normalize_whitespace: true,
                    repeated_boilerplate: [],
                  })
                }
              >
                Upgrade cleaning
              </Button>
            </div>
          </Callout>
          <dl className={FACTS}>
            <dt>Normalize whitespace</dt>
            <dd>{node.normalize_whitespace === false ? 'Off' : 'On'}</dd>
            <dt>Exact-content deduplication</dt>
            <dd>{node.exact_content_deduplication === false ? 'Off' : 'On'}</dd>
            <dt>Literal removals</dt>
            <dd>{node.repeated_boilerplate?.length ?? 0}</dd>
          </dl>
        </>
      ) : (
        <>
          {profile && upgradeChanges.length > 0 && (
            <Callout role="note" title={`Saved with ${node.config_version}`}>
              <p>
                This version keeps its original cleaning so earlier runs reproduce. The current
                cleaning, {profile.config_version}:
              </p>
              <ul className="list-disc pl-4">
                {upgradeChanges.map((change) => (
                  <li key={change}>{change}</li>
                ))}
              </ul>
              <p>
                Saving the upgrade creates a new pipeline version, and its next run cleans documents
                again.
              </p>
              <div>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => update({ ...node, config_version: profile.config_version })}
                >
                  Upgrade cleaning
                </Button>
              </div>
            </Callout>
          )}
          <p className={HINT}>
            Removes website menus, cookie banners and repeated page headers; keeps tables, lists and
            code.
          </p>
          <ListTextField
            label="Text to remove"
            hint="One line per piece of text, such as a footer line repeated on every page. Each line is removed exactly as typed."
            values={cleanLiterals(node)}
            error={literalError}
            onChange={(values) => update(setCleanLiterals(node, values))}
          />
        </>
      )}
      <label className={OPTION}>
        <Checkbox
          checked={redactionOn(node)}
          onCheckedChange={(checked) =>
            update({ ...node, sensitive_data_policy: { ...sensitive, enabled: checked === true } })
          }
        />
        <span>
          <strong>Redact emails, phone numbers and IDs</strong>
          <small>
            Replaces them before chunking and embedding, so they never reach the index or the
            embedding provider.
          </small>
        </span>
      </label>
      <details
        className={DETAILS}
        open={open || advancedError}
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary className={SUMMARY}>
          <span>Advanced cleaning settings</span>
          <small className={HINT}>
            · {differences.length === 0 ? 'recommended' : `${differences.length} changed`}
          </small>
        </summary>
        <div className={STACK}>
          <p className={HINT}>
            {differences.length === 0
              ? 'Using recommended settings.'
              : `${differences.length} ${
                  differences.length === 1 ? 'setting differs' : 'settings differ'
                } from recommended: ${differences.join(', ')}.`}
          </p>
          {differences.length > 0 && (
            <div>
              <Button
                type="button"
                variant="outline"
                onClick={() => update(resetCleanAdvanced(node, capabilities))}
              >
                Reset to recommended
              </Button>
            </div>
          )}
          {structure && <CleaningTransformSettings node={node} errors={errors} update={update} />}
          <fieldset className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
            <legend className="mb-2 text-sm font-medium text-foreground">
              Skip duplicate pages or files
            </legend>
            {(
              [
                ['exact_raw', 'Identical source files or pages'],
                ['exact_cleaned', 'Identical text after cleaning'],
                ['normalized_sections', 'Identical sections'],
                ['near_duplicate', 'Nearly identical text'],
              ] as const
            ).map(([key, label]) => (
              <label className={CHECK_ROW} key={key}>
                <Checkbox
                  checked={duplicate[key]}
                  onCheckedChange={(checked) =>
                    update({ ...node, duplicate_policy: { ...duplicate, [key]: checked === true } })
                  }
                />
                {label}
              </label>
            ))}
            {duplicate.near_duplicate && (
              <Label>
                Near-duplicate similarity threshold
                <Input
                  type="number"
                  min={0.75}
                  max={1}
                  step={0.01}
                  value={duplicate.near_duplicate_threshold}
                  onChange={(event) =>
                    update({
                      ...node,
                      duplicate_policy: {
                        ...duplicate,
                        near_duplicate_threshold: Number(event.target.value),
                      },
                    })
                  }
                />
              </Label>
            )}
            <ListTextField
              label="Pinned canonical locations"
              separator=","
              trim
              placeholder="Comma-separated stable source identities"
              values={duplicate.pinned_canonical_locations}
              onChange={(values) =>
                update({
                  ...node,
                  duplicate_policy: { ...duplicate, pinned_canonical_locations: values },
                })
              }
            />
            <p className={HINT}>
              The copy kept is the pinned source, then by connector priority, then the first stable
              identity.
            </p>
          </fieldset>
          <label className={CHECK_ROW}>
            <Checkbox
              checked={node.exact_content_deduplication !== false}
              onCheckedChange={(checked) =>
                update({ ...node, exact_content_deduplication: checked === true })
              }
            />
            Remove repeated blocks inside a document
          </label>
          <fieldset className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
            <legend className="mb-2 text-sm font-medium text-foreground">Redaction rules</legend>
            {sensitive.rules.map((rule) => (
              <Label key={rule.entity_class}>
                {redactionNames[rule.entity_class] ?? rule.entity_class}
                <NativeSelect
                  disabled={!sensitive.enabled}
                  value={rule.action}
                  onChange={(event) =>
                    update({
                      ...node,
                      sensitive_data_policy: {
                        ...sensitive,
                        rules: sensitive.rules.map((value) =>
                          value.entity_class === rule.entity_class
                            ? {
                                ...value,
                                action: event.target.value as 'redact' | 'drop_document',
                              }
                            : value,
                        ),
                      },
                    })
                  }
                >
                  <NativeSelectOption value="redact">Redact the value</NativeSelectOption>
                  <NativeSelectOption value="drop_document">
                    Leave out the whole document
                  </NativeSelectOption>
                </NativeSelect>
              </Label>
            ))}
            <p className={HINT}>
              Pattern detectors cover these kinds of values but cannot find every one. Redaction
              cannot be undone in passages, vectors, evidence and provider requests; raw copies are
              encrypted and kept for 30 days for project owners and admins.
            </p>
          </fieldset>
        </div>
      </details>
    </div>
  );
}
