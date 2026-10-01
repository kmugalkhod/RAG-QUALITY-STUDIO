import { RefreshCw } from 'lucide-react';
import { Callout, LINK, META } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import { Label } from '../../../components/ui/label';
import {
  NativeSelect,
  NativeSelectOptGroup,
  NativeSelectOption,
} from '../../../components/ui/native-select';
import { findModelOption, type ChatModelOption, type PipelineOptions } from '../model';

const MANAGE_HREF = '#/organization';

function price(value: number | null) {
  return value === null
    ? 'unknown'
    : `$${value.toLocaleString(undefined, { maximumFractionDigits: 4 })}`;
}

export function describeModel(model: ChatModelOption): string {
  const parts = [`${model.context_tokens.toLocaleString()} token budget`];
  if (model.prompt_usd_per_mtok === null && model.completion_usd_per_mtok === null) {
    parts.push(model.source === 'server' ? 'price not recorded' : 'price unknown');
  } else {
    parts.push(
      `${price(model.prompt_usd_per_mtok)} in / ${price(model.completion_usd_per_mtok)} out per 1M tokens (OpenRouter estimate)`,
    );
  }
  parts.push(
    model.source === 'organization' ? 'approved for this organization' : 'set on the server',
  );
  return parts.join(' · ');
}

// Group by provider, the prefix of an OpenRouter model ID, so long lists stay scannable.
function groupByProvider(models: ChatModelOption[]) {
  const groups = new Map<string, ChatModelOption[]>();
  for (const model of models) {
    const provider = model.id.includes('/') ? model.id.split('/')[0] : 'Other';
    groups.set(provider, [...(groups.get(provider) ?? []), model]);
  }
  return [...groups.entries()];
}

interface Props {
  value: string;
  options?: PipelineOptions;
  loading: boolean;
  onChange: (model: string) => void;
  onRefresh: () => void;
}

export function ModelField({ value, options, loading, onChange, onRefresh }: Props) {
  if (!options) {
    return null;
  }
  const refresh = (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="self-start"
      loading={loading}
      onClick={onRefresh}
    >
      <RefreshCw aria-hidden="true" />
      Refresh models
    </Button>
  );
  const manage = options.can_manage_models ? (
    <a className={LINK} href={MANAGE_HREF}>
      Manage approved models
    </a>
  ) : null;
  if (!options.model_options.length) {
    return (
      <Callout tone="warning" role="status" title="Chat model needed">
        <p>{options.error ?? 'No chat model is configured for this organization.'}</p>
        {!options.can_manage_models && (
          <p>Ask an organization admin to approve a model in Organization settings.</p>
        )}
        <div className="flex flex-wrap items-center gap-4">
          {options.can_manage_models && (
            <Button size="sm" asChild>
              <a href={MANAGE_HREF}>Manage models</a>
            </Button>
          )}
          {refresh}
        </div>
      </Callout>
    );
  }
  const selected = findModelOption(options, value);
  const unavailable = !!value && !selected;
  return (
    <>
      <Label className="mb-0">
        Chat model
        <NativeSelect
          className="mt-2"
          aria-label="Chat model"
          aria-describedby="chat-model-details"
          aria-invalid={unavailable || undefined}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          <NativeSelectOption value="">Select a model</NativeSelectOption>
          {unavailable && (
            <NativeSelectOptGroup label="Unavailable">
              <NativeSelectOption value={value}>{value} (not approved)</NativeSelectOption>
            </NativeSelectOptGroup>
          )}
          {groupByProvider(options.model_options).map(([provider, models]) => (
            <NativeSelectOptGroup key={provider} label={provider}>
              {models.map((model) => (
                <NativeSelectOption key={model.id} value={model.id}>
                  {model.label === model.id ? model.id : `${model.label} (${model.id})`}
                  {model.id === options.default_model ? ' · default' : ''}
                </NativeSelectOption>
              ))}
            </NativeSelectOptGroup>
          ))}
        </NativeSelect>
      </Label>
      <p id="chat-model-details" className={META}>
        {selected
          ? describeModel(selected)
          : `${options.model_options.length} model${options.model_options.length === 1 ? '' : 's'} available.`}
      </p>
      {unavailable && (
        <Callout tone="warning" role="status" title="This model is no longer approved">
          <p>
            Saved versions keep {value}. Choose an approved model to save a new version, or ask an
            organization admin to approve it again.
          </p>
        </Callout>
      )}
      {options.error_code === 'provider_key' && (
        <Callout tone="warning" role="status" title="OpenRouter key needed">
          <p>{options.error}</p>
          <a className={LINK} href={MANAGE_HREF}>
            Open Organization settings
          </a>
        </Callout>
      )}
      <div className="flex flex-wrap items-center gap-4">
        {manage}
        {refresh}
      </div>
    </>
  );
}
