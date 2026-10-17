import { useId, useState } from 'react';

import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { RadioGroup, RadioGroupItem } from '../../../components/ui/radio-group';
import type { KnowledgeSet } from '../../documents/model';
import type { IngestionNode } from '../model';
import { FIELD_ERROR, HINT, STACK } from './settingsStyles';

type PublishNode = Extract<IngestionNode, { type: 'publish_index' }>;

const CHOICE =
  'flex cursor-pointer items-start gap-3 rounded-control border border-border bg-background p-4 text-sm text-foreground has-data-[state=checked]:border-accent [&>button]:mt-1';

/** The index that a new name would collide with, ignoring case, if another pipeline owns it. */
export function nameClash(
  name: string,
  knowledgeSets: KnowledgeSet[],
  pipelineId?: string,
): KnowledgeSet | undefined {
  const wanted = name.trim().toLocaleLowerCase();
  const match = knowledgeSets.find((set) => set.name.toLocaleLowerCase() === wanted);
  // An index this pipeline already published to is reused when the version is saved.
  if (!match || (pipelineId && match.publishing_pipelines?.some((p) => p.id === pipelineId))) {
    return undefined;
  }
  return match;
}

/** What the next run publishes, and that earlier versions stay available (spec 0012 B). */
export function publishedVersionText(target?: KnowledgeSet, newName?: string): string | undefined {
  if (!target) {
    return newName?.trim()
      ? `This run publishes version 1 of the new index ${newName.trim()}.`
      : undefined;
  }
  if (!target.latest_version) {
    return `This run publishes version 1 of ${target.name}.`;
  }
  // Spec 0012 D8: a run that finds nothing changed publishes no version.
  const current = target.current_version
    ? ` Version ${target.current_version} stays available; if nothing changed, no version is published and it stays current.`
    : '';
  return `This run publishes version ${target.latest_version + 1} of ${target.name}.${current} Answer pipelines keep their version until you switch.`;
}

export function takenMessage(name: string) {
  return `An index named "${name}" already exists. Choose "Add a version to an existing index" to publish to it, or enter another name.`;
}

/**
 * Publish settings (spec 0012 D3): publish a new index, or add a version to an existing
 * one. Switching back to a new index restores the name typed for it, never the name of
 * the existing index that was picked in between.
 */
export function PublishIndexSettings({
  node,
  knowledgeSets,
  pipelineId,
  defaultName,
  serverError,
  update,
}: {
  node: PublishNode;
  knowledgeSets: KnowledgeSet[];
  /** The saved pipeline, if any; its own runs do not count as another publisher. */
  pipelineId?: string;
  /** The name a new index gets when none was typed: the pipeline's name. */
  defaultName: string;
  serverError?: string;
  update: (node: PublishNode) => void;
}) {
  const id = useId();
  const existing = !!node.knowledge_set_id;
  const [newName, setNewName] = useState(existing ? defaultName : node.knowledge_set_name);
  const selected = knowledgeSets.find((set) => set.id === node.knowledge_set_id);
  const clash = existing
    ? undefined
    : nameClash(node.knowledge_set_name, knowledgeSets, pipelineId);
  const error = serverError ?? (clash ? takenMessage(clash.name) : undefined);
  // A new name this pipeline already published to is saved as a version of that index.
  const own = existing
    ? undefined
    : knowledgeSets.find(
        (set) =>
          set.name.toLocaleLowerCase() === node.knowledge_set_name.trim().toLocaleLowerCase() &&
          !!pipelineId &&
          set.publishing_pipelines?.some((value) => value.id === pipelineId),
      );
  const target = selected ?? own;
  const others = (target?.publishing_pipelines ?? []).filter((value) => value.id !== pipelineId);
  const versionLine = publishedVersionText(target, existing ? undefined : node.knowledge_set_name);

  function choose(value: string) {
    if (value === 'new') {
      update({
        id: node.id,
        type: 'publish_index',
        knowledge_set_name: newName,
        destination: 'new',
      });
      return;
    }
    const set =
      knowledgeSets.find(
        (candidate) => candidate.name.toLocaleLowerCase() === newName.trim().toLocaleLowerCase(),
      ) ?? knowledgeSets[0];
    if (set) {
      update({
        ...node,
        knowledge_set_id: set.id,
        knowledge_set_name: set.name,
        destination: 'existing',
      });
    }
  }

  return (
    <div className={STACK}>
      <p className={HINT}>
        Make the embedded passages available as an index that answer pipelines can search. Each run
        publishes a new version; earlier versions stay available.
      </p>
      <RadioGroup
        aria-label="Where to publish"
        value={existing ? 'existing' : 'new'}
        onValueChange={choose}
      >
        <label className={CHOICE}>
          <RadioGroupItem value="new" aria-describedby={`${id}-new`} />
          <span className="flex min-w-0 flex-col gap-1">
            <strong className="font-medium">New index</strong>
            <small id={`${id}-new`} className="text-xs text-foreground-muted">
              Creates an index of its own for this pipeline.
            </small>
          </span>
        </label>
        <label className={CHOICE}>
          <RadioGroupItem
            value="existing"
            disabled={knowledgeSets.length === 0}
            aria-describedby={`${id}-existing`}
          />
          <span className="flex min-w-0 flex-col gap-1">
            <strong className="font-medium">Add a version to an existing index</strong>
            <small id={`${id}-existing`} className="text-xs text-foreground-muted">
              {knowledgeSets.length === 0
                ? 'No index exists in this project yet.'
                : 'Each run replaces the version answers use; earlier versions stay available.'}
            </small>
          </span>
        </label>
      </RadioGroup>
      {existing ? (
        <Label>
          Index
          <NativeSelect
            value={node.knowledge_set_id ?? ''}
            onChange={(event) => {
              const set = knowledgeSets.find((item) => item.id === event.target.value);
              if (set) {
                update({
                  ...node,
                  knowledge_set_id: set.id,
                  knowledge_set_name: set.name,
                  destination: 'existing',
                });
              }
            }}
          >
            {!selected && (
              <NativeSelectOption value={node.knowledge_set_id ?? ''}>
                {node.knowledge_set_name}
              </NativeSelectOption>
            )}
            {knowledgeSets.map((set) => (
              <NativeSelectOption key={set.id} value={set.id}>
                {set.name}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Label>
      ) : (
        <div className="flex flex-col gap-2">
          <Label>
            Index name
            <Input
              value={node.knowledge_set_name}
              maxLength={120}
              aria-invalid={!!error}
              aria-describedby={error ? `${id}-error` : undefined}
              onChange={(event) => {
                setNewName(event.target.value);
                update({ ...node, knowledge_set_name: event.target.value, destination: 'new' });
              }}
            />
          </Label>
          {error && (
            <small id={`${id}-error`} role="alert" className={FIELD_ERROR}>
              {error}
            </small>
          )}
        </div>
      )}
      {versionLine && !error && <p className={HINT}>{versionLine}</p>}
      {others.length > 0 && (
        <p className={HINT}>
          Also published by {others.map((value) => value.name).join(', ')}. Each run replaces its
          current version.
        </p>
      )}
    </div>
  );
}
