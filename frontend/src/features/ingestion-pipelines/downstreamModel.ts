/**
 * Recommended values, "N changed" lists and resets for the Clean and Chunk panels
 * (spec 0012 Part B, in the spec 0008 D1 pattern): the schema keeps every field, new
 * drafts and Reset use the recommended values, and a saved custom value stays as saved.
 */
import { defaultDuplicatePolicy, defaultSensitiveDataPolicy } from './editorModel';
import type { ChunkNode, CleaningTransform, ExtractionCapabilities, IngestionNode } from './model';

type CleanNode = Extract<IngestionNode, { type: 'clean' }>;
type TokenChunk = Extract<ChunkNode, { algorithm: 'section_token' | 'parent_child' }>;

export const cleaningStepNames: Record<CleaningTransform['type'], string> = {
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

/** The order the server requires; a new step is inserted at its place in it. */
export const cleaningStepOrder: CleaningTransform['type'][] = [
  'preserve_structure',
  'unicode_normalize',
  'remove_control_characters',
  'remove_repeated_headers_footers',
  'reflow_pdf_lines',
  'dehyphenate',
  'website_selectors',
  'website_main_content',
  'remove_literal_boilerplate',
  'remove_empty_blocks',
  'validate_useful_content',
];

/** The server's recommended steps, or the same list for a server that does not send them. */
export function recommendedCleanSteps(capabilities?: ExtractionCapabilities): CleaningTransform[] {
  const steps = capabilities?.cleaning_profiles?.[0]?.steps;
  if (steps?.length) {
    return structuredClone(steps);
  }
  return [
    {
      id: 'preserve-structure',
      type: 'preserve_structure',
      enabled: true,
      block_types: ['table', 'list_item', 'code', 'quote', 'footnote'],
    },
    { id: 'unicode-normalize', type: 'unicode_normalize', enabled: true, form: 'NFC' },
    { id: 'remove-controls', type: 'remove_control_characters', enabled: true },
    {
      id: 'repeated-margins',
      type: 'remove_repeated_headers_footers',
      enabled: true,
      minimum_page_ratio: 0.6,
      minimum_pages: 3,
      margin_ratio: 0.12,
    },
    {
      id: 'reflow-pdf-lines',
      type: 'reflow_pdf_lines',
      enabled: true,
      block_types: ['paragraph', 'unknown'],
    },
    { id: 'dehyphenate', type: 'dehyphenate', enabled: true, mode: 'conservative-compounds' },
    {
      id: 'website-main-content',
      type: 'website_main_content',
      enabled: true,
      remove_semantic_chrome: true,
      remove_cookie_banners: true,
      remove_repeated_site_chrome: true,
      minimum_page_ratio: 0.6,
    },
    {
      id: 'remove-empty-blocks',
      type: 'remove_empty_blocks',
      enabled: true,
      minimum_characters: 1,
    },
    {
      id: 'validate-useful-content',
      type: 'validate_useful_content',
      enabled: true,
      minimum_characters: 1,
      maximum_characters: 2_000_000,
    },
  ];
}

/** Key-order independent comparison of saved JSON values. */
function same(left: unknown, right: unknown): boolean {
  return JSON.stringify(sorted(left)) === JSON.stringify(sorted(right));
}

function sorted(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sorted);
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, sorted((value as Record<string, unknown>)[key])]),
    );
  }
  return value;
}

/** A step's settings without its ID, which carries no behaviour. */
function settingsOf(step: CleaningTransform) {
  const { id: _id, ...rest } = step;
  void _id;
  return rest;
}

/** The literal lines the visible "Text to remove" box edits. */
export function cleanLiterals(node: CleanNode): string[] {
  const step = node.steps?.find((value) => value.type === 'remove_literal_boilerplate');
  return step?.type === 'remove_literal_boilerplate' ? step.values : [];
}

/**
 * Sets the visible literal lines: they live in the literal step, inserted at its place in
 * the server order; clearing every line removes the step.
 */
export function setCleanLiterals(node: CleanNode, values: string[]): CleanNode {
  const steps = [...(node.steps ?? [])];
  const index = steps.findIndex((step) => step.type === 'remove_literal_boilerplate');
  if (!values.length) {
    return index < 0 ? node : { ...node, steps: steps.filter((_, item) => item !== index) };
  }
  if (index >= 0) {
    const step = steps[index] as Extract<CleaningTransform, { type: 'remove_literal_boilerplate' }>;
    steps[index] = { ...step, enabled: true, values };
    return { ...node, steps };
  }
  return {
    ...node,
    steps: insertStep(steps, {
      id: 'remove-literal-boilerplate',
      type: 'remove_literal_boilerplate',
      enabled: true,
      values,
      block_types: ['paragraph', 'unknown'],
    }),
  };
}

/** Inserts a step before the first existing step that the server order puts after it. */
export function insertStep(steps: CleaningTransform[], step: CleaningTransform) {
  const rank = cleaningStepOrder.indexOf(step.type);
  const position = steps.findIndex((value) => cleaningStepOrder.indexOf(value.type) > rank);
  const next = [...steps];
  next.splice(position < 0 ? next.length : position, 0, step);
  return next;
}

export function redactionOn(node: CleanNode) {
  return (node.sensitive_data_policy ?? defaultSensitiveDataPolicy).enabled;
}

/**
 * Advanced Clean settings that differ from the recommended ones, by their panel label.
 * The literal lines and the redaction switch are visible choices and do not count.
 */
export function cleanDifferences(node: CleanNode, capabilities?: ExtractionCapabilities): string[] {
  const differences =
    node.profile === 'structure-aware-v1' ? stepDifferences(node, capabilities) : [];
  if (!same(node.duplicate_policy ?? defaultDuplicatePolicy, defaultDuplicatePolicy)) {
    differences.push('Skip duplicate pages or files');
  }
  if (node.exact_content_deduplication === false) {
    differences.push('Repeated blocks in a document');
  }
  const policy = node.sensitive_data_policy ?? defaultSensitiveDataPolicy;
  if (!same({ ...policy, enabled: true }, { ...defaultSensitiveDataPolicy, enabled: true })) {
    differences.push('Redaction rules');
  }
  return differences;
}

/** The structure-aware steps and length limits that differ from the recommended ones. */
function stepDifferences(node: CleanNode, capabilities?: ExtractionCapabilities): string[] {
  const recommended = recommendedCleanSteps(capabilities);
  const steps = (node.steps ?? []).filter((step) => step.type !== 'remove_literal_boilerplate');
  const differences: string[] = [];
  for (const step of recommended) {
    const saved = steps.find((value) => value.type === step.type);
    if (step.type === 'validate_useful_content') {
      continue; // counted with the length limits below
    }
    if (!saved || !same(settingsOf(saved), settingsOf(step))) {
      differences.push(cleaningStepNames[step.type]);
    }
  }
  for (const step of steps) {
    if (!recommended.some((value) => value.type === step.type)) {
      differences.push(cleaningStepNames[step.type]);
    }
  }
  // The literal text is a visible choice; only its switch and block types are advanced.
  const literal = node.steps?.find((step) => step.type === 'remove_literal_boilerplate');
  if (
    literal?.type === 'remove_literal_boilerplate' &&
    (!literal.enabled || !same([...literal.block_types].sort(), ['paragraph', 'unknown']))
  ) {
    differences.push(cleaningStepNames.remove_literal_boilerplate);
  }
  const order = steps.map((step) => step.type).filter((type) => cleaningStepOrder.includes(type));
  const expected = [...order].sort(
    (left, right) => cleaningStepOrder.indexOf(left) - cleaningStepOrder.indexOf(right),
  );
  if (!same(order, expected)) {
    differences.push('Step order');
  }
  const validate = steps.find((step) => step.type === 'validate_useful_content');
  const recommendedValidate = recommended.find((step) => step.type === 'validate_useful_content');
  if (
    (node.minimum_text_chars ?? 1) !== 1 ||
    (node.maximum_text_chars ?? 2_000_000) !== 2_000_000 ||
    (recommendedValidate &&
      (!validate || !same(settingsOf(validate), settingsOf(recommendedValidate))))
  ) {
    differences.push('Length limits');
  }
  return differences;
}

/** Restores the advanced settings; the literal lines and the redaction switch are kept. */
export function resetCleanAdvanced(
  node: CleanNode,
  capabilities?: ExtractionCapabilities,
): CleanNode {
  const shared = {
    exact_content_deduplication: true,
    duplicate_policy: structuredClone(defaultDuplicatePolicy),
    sensitive_data_policy: {
      ...structuredClone(defaultSensitiveDataPolicy),
      enabled: redactionOn(node),
    },
  };
  if (node.profile !== 'structure-aware-v1') {
    // A compatibility version keeps its cleaner; Upgrade cleaning changes that.
    return { ...node, ...shared };
  }
  const literal = node.steps?.find((step) => step.type === 'remove_literal_boilerplate');
  let steps = recommendedCleanSteps(capabilities);
  if (literal) {
    steps = insertStep(steps, literal);
  }
  return { ...node, ...shared, steps, minimum_text_chars: 1, maximum_text_chars: 2_000_000 };
}

/** Passage sizes in UTF-8 bytes (spec 0012 D4); Medium is the recommended size. */
export const passageSizes = {
  section_token: {
    small: { target_tokens: 300, maximum_tokens: 400, overlap_tokens: 40 },
    medium: { target_tokens: 600, maximum_tokens: 800, overlap_tokens: 80 },
    large: { target_tokens: 1200, maximum_tokens: 1600, overlap_tokens: 160 },
  },
  parent_child: {
    small: {
      child_target_tokens: 160,
      child_maximum_tokens: 240,
      child_overlap_tokens: 24,
      parent_target_tokens: 600,
      parent_maximum_tokens: 800,
    },
    medium: {
      child_target_tokens: 240,
      child_maximum_tokens: 320,
      child_overlap_tokens: 40,
      parent_target_tokens: 900,
      parent_maximum_tokens: 1200,
    },
    large: {
      child_target_tokens: 480,
      child_maximum_tokens: 640,
      child_overlap_tokens: 80,
      parent_target_tokens: 1800,
      parent_maximum_tokens: 2400,
    },
  },
} as const;

export type PassageSize = 'small' | 'medium' | 'large';

/** About this many English words per passage: roughly six UTF-8 bytes per word. */
export function aboutWords(bytes: number) {
  return Math.max(10, Math.round(bytes / 6 / 10) * 10);
}

/** The target size that "about N words" describes for a method and size. */
export function passageTarget(algorithm: TokenChunk['algorithm'], size: PassageSize) {
  return algorithm === 'section_token'
    ? passageSizes.section_token[size].target_tokens
    : passageSizes.parent_child[size].child_target_tokens;
}

/** Which size the saved values are, or undefined when they are custom. */
export function passageSize(node: ChunkNode): PassageSize | undefined {
  if (node.algorithm !== 'section_token' && node.algorithm !== 'parent_child') {
    return undefined;
  }
  const values = node as unknown as Record<string, number>;
  return (['small', 'medium', 'large'] as const).find((size) =>
    Object.entries(passageSizes[node.algorithm][size]).every(
      ([field, value]) => values[field] === value,
    ),
  );
}

export function withPassageSize(node: TokenChunk, size: PassageSize): ChunkNode {
  return { ...node, ...passageSizes[node.algorithm][size] } as ChunkNode;
}

/** Advanced Chunk settings that differ from the recommended ones, by their panel label. */
export function chunkDifferences(node: ChunkNode): string[] {
  if (node.algorithm !== 'section_token' && node.algorithm !== 'parent_child') {
    return [];
  }
  const differences: string[] = [];
  if (!passageSize(node)) {
    differences.push('Exact passage sizes');
  }
  if (!node.add_heading_context) {
    differences.push('Section titles for search');
  }
  return differences;
}

/** Medium sizes with section titles on; the method and its version are kept. */
export function resetChunkAdvanced(node: TokenChunk): ChunkNode {
  return { ...withPassageSize(node, 'medium'), add_heading_context: true } as ChunkNode;
}
