import { readdir, readFile } from 'node:fs/promises';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import postcss from 'postcss';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = resolve(frontend, 'src');
const errors = [];
const sourceFiles = [];

async function inspect(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  if (!entries.length)
    errors.push(`Remove empty source directory: ${relative(frontend, directory)}`);
  for (const entry of entries) {
    const path = resolve(directory, entry.name);
    // Forward slashes on every platform, so the checks below match on Windows too.
    const name = relative(frontend, path).replaceAll('\\', '/');
    if (entry.isDirectory()) {
      await inspect(path);
      continue;
    }
    if (entry.name.endsWith('.css') && name !== 'src/app/styles.css') {
      errors.push(
        `${name}: keep application CSS in src/app/styles.css and use Tailwind in components.`,
      );
    }
    if (/\.(test|spec)\./.test(entry.name)) {
      errors.push(`${name}: move unit/component tests to tests/ or browser journeys to e2e/.`);
    }
    if (/\.(css|ts|tsx)$/.test(entry.name)) {
      sourceFiles.push({ path, name });
    }
  }
}

// Design token guard (spec 0002, AC-1). The total must equal LEGACY_ALLOWANCE exactly:
// lower the allowance when a migration removes violations, never raise it.
// Set GUARD_DETAILS=1 to list every violation with its line.
const LEGACY_ALLOWANCE = 0;

const GRID_KEYS = new Set(['1', '2', '3', '4', '6', '8', '12', '16']);
const NAMED_SIZE_KEYS = new Set([
  'control-sm',
  'control-md',
  'control-lg',
  'row-header',
  'row',
  'tabbar',
  'node-h',
  'node-legacy',
  'sidebar',
  'node',
  'panel',
]);
const SIZE_KEYWORDS = new Set([
  'full',
  'screen',
  'dvh',
  'auto',
  'px',
  '0',
  'fit',
  'min',
  'max',
  'none',
]);
const TEXT_SIZES = new Set(['xs', 'sm', 'md', 'base', 'lg', 'xl']);
const RADIUS_KEYS = new Set(['control', 'card', 'shell', 'full', 'none']);
const SHADOW_KEYS = new Set(['popover', 'none']);
const PALETTE =
  /^(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}$|^(?:white|black)$/;
const COLOR_PREFIX =
  /^(?:bg|text|border(?:-[xytrblse])?|ring|ring-offset|outline|fill|stroke|divide|placeholder|caret|accent|decoration|from|via|to)-(.+)$/;
const SPACING_UTILITY =
  /^(?:px|py|pt|pr|pb|pl|ps|pe|p|mx|my|mt|mr|mb|ml|ms|me|m|gap-x|gap-y|gap|space-x|space-y)-(.+)$/;
const SIZE_UTILITY =
  /^(?:w|h|size|min-w|min-h|max-w|max-h|basis|inset-x|inset-y|inset|top|right|bottom|left)-(.+)$/;
const COLOR_LITERAL =
  /(?<![\w&/-])#(?:[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3,4})(?![\w-])|\b(?:rgba?|hsla?)\(/gi;

function lineAt(text, index) {
  return text.slice(0, index).split('\n').length;
}

// Blank out a marked block so offsets and line numbers stay stable.
function blankBlock(text, start, end) {
  let result = text;
  for (;;) {
    const from = result.indexOf(start);
    if (from < 0) {
      return result;
    }
    const to = result.indexOf(end, from);
    const stop = to < 0 ? result.length : to + end.length;
    result =
      result.slice(0, from) + result.slice(from, stop).replace(/[^\n]/g, ' ') + result.slice(stop);
  }
}

function checkCss(text, report) {
  const clean = text.replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, ' '));
  let segmentStart = 0;
  for (let index = 0; index < clean.length; index += 1) {
    const char = clean[index];
    if (char !== '{' && char !== '}' && char !== ';') {
      continue;
    }
    const segment = clean.slice(segmentStart, index);
    const offset = segmentStart;
    segmentStart = index + 1;
    if (char === '{') {
      continue; // a selector or at-rule prelude, never a value
    }
    const colon = segment.indexOf(':');
    if (colon < 0) {
      continue;
    }
    const property = segment.slice(0, colon).trim();
    const value = segment.slice(colon + 1).trim();
    for (const match of value.matchAll(COLOR_LITERAL)) {
      report('color literal', offset + colon + 1 + match.index, match[0]);
    }
    if (
      property === 'font-size' &&
      !/^(?:var\(--text-(?:xs|sm|md|base|lg|xl)\)|inherit)$/.test(value)
    ) {
      report('font-size', offset, value);
    }
  }
}

// Return [start, end) of the balanced region opening at text[open].
function balanced(text, open) {
  const pairs = { '(': ')', '{': '}' };
  const stack = [pairs[text[open]]];
  let index = open + 1;
  while (index < text.length && stack.length) {
    const char = text[index];
    if (char === "'" || char === '"' || char === '`') {
      index = skipString(text, index);
      continue;
    }
    if (char === '(' || char === '{') {
      stack.push(pairs[char]);
    } else if (char === stack[stack.length - 1]) {
      stack.pop();
    }
    index += 1;
  }
  return [open + 1, index - 1];
}

function skipString(text, start) {
  const quote = text[start];
  let index = start + 1;
  while (index < text.length && text[index] !== quote) {
    if (text[index] === '\\') {
      index += 1;
    } else if (quote === '`' && text[index] === '$' && text[index + 1] === '{') {
      index = balanced(text, index + 1)[1];
    }
    index += 1;
  }
  return index + 1;
}

// Literal string parts inside a code region, with their offsets.
function stringsIn(text, from, to) {
  const found = [];
  let index = from;
  while (index < to) {
    const char = text[index];
    if (char !== "'" && char !== '"' && char !== '`') {
      index += 1;
      continue;
    }
    const end = skipString(text, index);
    const body = text.slice(index + 1, end - 1);
    found.push({ value: body.replace(/\$\{[\s\S]*?\}/g, ' '), offset: index + 1 });
    index = end;
  }
  return found;
}

function classStrings(text) {
  const found = [];
  for (const match of text.matchAll(/className=(["'])/g)) {
    const open = match.index + 'className='.length;
    const end = skipString(text, open);
    found.push({ value: text.slice(open + 1, end - 1), offset: open + 1 });
  }
  for (const match of text.matchAll(/className=\{/g)) {
    const [from, to] = balanced(text, match.index + match[0].length - 1);
    found.push(...stringsIn(text, from, to));
  }
  for (const match of text.matchAll(/\b(?:cn|cva)\(/g)) {
    const [from, to] = balanced(text, match.index + match[0].length - 1);
    found.push(...stringsIn(text, from, to));
  }
  return found;
}

function utilityOf(token) {
  let depth = 0;
  let last = 0;
  for (let index = 0; index < token.length; index += 1) {
    const char = token[index];
    if (char === '[' || char === '(') {
      depth += 1;
    } else if (char === ']' || char === ')') {
      depth -= 1;
    } else if (char === ':' && depth === 0) {
      last = index + 1;
    }
  }
  return token.slice(last).replace(/^!|!$/g, '').replace(/^-/, '');
}

function classViolation(utility) {
  const bracket = utility.match(/\[([^\]]*)\]/);
  if (bracket && /\d(?:px|rem|%)/.test(bracket[1])) {
    return 'arbitrary value';
  }
  if (
    utility === 'font-bold' ||
    utility === 'blur' ||
    /^(?:backdrop|blur|bg-gradient|bg-linear|bg-radial|bg-conic)-/.test(utility)
  ) {
    return 'banned utility';
  }
  if (bracket || utility.includes('(--')) {
    return null; // other arbitrary values and (--var) shorthands are allowed
  }
  const radius = utility.match(/^rounded(?:-(?:tl|tr|br|bl|ss|se|es|ee|t|r|b|l|s|e))?(?:-(.+))?$/);
  if (radius) {
    return RADIUS_KEYS.has(radius[1]) ? null : 'radius key';
  }
  const shadow = utility.match(/^shadow(?:-(.+))?$/);
  if (shadow) {
    return SHADOW_KEYS.has(shadow[1]) ? null : 'shadow key';
  }
  const spacing = utility.match(SPACING_UTILITY);
  if (spacing) {
    const key = spacing[1];
    return GRID_KEYS.has(key) || key === '0' || key === 'auto' || key === 'reverse'
      ? null
      : 'spacing key';
  }
  const size = utility.match(SIZE_UTILITY);
  if (size) {
    const key = size[1];
    const allowed =
      GRID_KEYS.has(key) ||
      NAMED_SIZE_KEYS.has(key) ||
      SIZE_KEYWORDS.has(key) ||
      /^\d+\/\d+$/.test(key);
    return allowed ? null : 'size key';
  }
  const text = utility.match(/^text-(.+)$/);
  if (text) {
    const key = text[1];
    if (TEXT_SIZES.has(key)) {
      return null;
    }
    if (/^(?:\d?xl|[2-9]xl)$/.test(key) || /^(?:xs|sm|md|base|lg|xl)\//.test(key)) {
      return 'text key';
    }
  }
  const color = utility.match(COLOR_PREFIX);
  if (color && PALETTE.test(color[1].replace(/\/\d+$/, ''))) {
    return 'palette color';
  }
  return null;
}

function checkTs(text, name, report) {
  for (const match of text.matchAll(COLOR_LITERAL)) {
    report('color literal', match.index, match[0]);
  }
  for (const match of text.matchAll(/style=\{\{/g)) {
    const [from, to] = balanced(text, match.index + match[0].length - 1);
    const body = text.slice(from, to);
    const keys = [];
    let depth = 0;
    let part = '';
    for (const char of body + ',') {
      if ('([{'.includes(char)) {
        depth += 1;
      } else if (')]}'.includes(char)) {
        depth -= 1;
      }
      if (char === ',' && depth === 0) {
        keys.push(part.trim());
        part = '';
      } else {
        part += char;
      }
    }
    const invalid = keys.filter((entry) => entry && !/^(['"])--[\w-]+\1\s*:/.test(entry));
    if (invalid.length) {
      report('style prop', match.index, invalid.join(', ').slice(0, 60));
    }
  }
  for (const { value, offset } of classStrings(text)) {
    for (const match of value.matchAll(/\S+/g)) {
      const kind = classViolation(utilityOf(match[0]));
      if (kind) {
        report(kind, offset + match.index, match[0]);
      }
    }
  }
  if (name.startsWith('src/features/') && name.endsWith('.tsx')) {
    for (const match of text.matchAll(/<(?:button|input|select|textarea)\b/g)) {
      report('raw element', match.index, match[0]);
    }
  }
}

async function guardTokens() {
  const counts = new Map();
  const details = [];
  for (const { path, name } of sourceFiles) {
    let text = await readFile(path, 'utf8');
    text = blankBlock(text, '/* @tokens:start */', '/* @tokens:end */');
    text = blankBlock(text, '/* @vendor:react-flow:start */', '/* @vendor:react-flow:end */');
    const report = (kind, index, sample) => {
      counts.set(name, (counts.get(name) ?? 0) + 1);
      details.push(`${name}:${lineAt(text, index)} ${kind}: ${sample}`);
    };
    if (name.endsWith('.css')) {
      checkCss(text, report);
    } else {
      checkTs(text, name, report);
    }
  }
  const total = [...counts.values()].reduce((sum, count) => sum + count, 0);
  if (process.env.GUARD_DETAILS) {
    console.log(details.join('\n'));
  }
  for (const [name, count] of [...counts].sort((a, b) => b[1] - a[1])) {
    console.log(`${String(count).padStart(5)}  ${name}`);
  }
  console.log(`Token guard: ${total} violations, allowance ${LEGACY_ALLOWANCE}.`);
  if (total > LEGACY_ALLOWANCE) {
    errors.push(
      `Token guard: ${total - LEGACY_ALLOWANCE} new violations. Use tokens and approved keys (spec 0002); run with GUARD_DETAILS=1 to list them.`,
    );
  } else if (total < LEGACY_ALLOWANCE) {
    errors.push(
      `Token guard: violations fell to ${total}. Lower LEGACY_ALLOWANCE in scripts/check-structure.mjs to ${total}.`,
    );
  }
}

// Stylesheet layers (spec 0002, AC-8). styles.css holds only the token block, the base
// layer, a components layer of shared selectors and the React Flow vendor block. Imports,
// @theme and @custom-variant are allowed at the top level; any other rule or layer fails.
const ALLOWED_LAYERS = new Set(['base', 'components']);
const TOP_LEVEL_AT_RULES = new Set(['import', 'theme', 'custom-variant']);

async function guardLayers() {
  const css = await readFile(resolve(source, 'app/styles.css'), 'utf8');
  const lines = css.split('\n');
  const lineOf = (marker) => lines.findIndex((line) => line.includes(marker)) + 1;
  const blocks = [
    [lineOf('/* @tokens:start */'), lineOf('/* @tokens:end */')],
    [lineOf('/* @vendor:react-flow:start */'), lineOf('/* @vendor:react-flow:end */')],
  ];
  const inBlock = (line, [from, to]) => from > 0 && line > from && line < to;
  for (const node of postcss.parse(css).nodes) {
    const line = node.source.start.line;
    if (node.type === 'comment') {
      continue;
    }
    if (node.type === 'atrule') {
      if (TOP_LEVEL_AT_RULES.has(node.name)) {
        continue;
      }
      if (node.name === 'layer' && ALLOWED_LAYERS.has(node.params) && node.nodes) {
        continue;
      }
      if (node.name === 'media' && inBlock(line, blocks[1])) {
        continue;
      }
      errors.push(
        `src/app/styles.css:${line}: "@${node.name} ${node.params}" is outside the allowed layers (spec 0002).`,
      );
      continue;
    }
    const tokenRoot =
      inBlock(line, blocks[0]) && /^:root(?:\[data-theme='light'\])?$/.test(node.selector);
    if (!tokenRoot && !inBlock(line, blocks[1])) {
      errors.push(
        `src/app/styles.css:${line}: selector "${node.selector}" belongs in @layer base or components (spec 0002).`,
      );
    }
  }
}

await inspect(source);
await guardTokens();
await guardLayers();
if (errors.length) {
  console.error(errors.join('\n'));
  process.exitCode = 1;
} else {
  console.log('Frontend structure checks passed.');
}
