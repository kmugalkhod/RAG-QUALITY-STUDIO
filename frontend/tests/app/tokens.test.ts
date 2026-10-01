import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// Contrast checks for the token table in spec 0002 (AC-2), read straight from styles.css.
const css = readFileSync(resolve(__dirname, '../../src/app/styles.css'), 'utf8');
const tokenBlock = css.slice(css.indexOf('/* @tokens:start */'), css.indexOf('/* @tokens:end */'));

type Rgba = [number, number, number, number];

function declarations(selector: string) {
  const start = tokenBlock.indexOf(`${selector} {`);
  const body = tokenBlock.slice(start, tokenBlock.indexOf('}', start));
  return Object.fromEntries(
    [...body.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((match) => [match[1], match[2].trim()]),
  );
}

const dark = declarations(':root');
const light = { ...dark, ...declarations(":root[data-theme='light']") };

const toLinear = (channel: number) =>
  channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
const fromLinear = (channel: number) =>
  channel <= 0.0031308 ? channel * 12.92 : 1.055 * channel ** (1 / 2.4) - 0.055;

function toOklab([r, g, b]: Rgba) {
  const [lr, lg, lb] = [r, g, b].map(toLinear);
  const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb);
  const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb);
  const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

function fromOklab([okL, okA, okB]: number[]): Rgba {
  const l = (okL + 0.3963377774 * okA + 0.2158037573 * okB) ** 3;
  const m = (okL - 0.1055613458 * okA - 0.0638541728 * okB) ** 3;
  const s = (okL - 0.0894841775 * okA - 1.291485548 * okB) ** 3;
  const rgb = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ].map((channel) => Math.min(1, Math.max(0, fromLinear(channel))));
  return [rgb[0], rgb[1], rgb[2], 1];
}

function parse(value: string, theme: Record<string, string>): Rgba {
  const reference = value.match(/^var\((--[\w-]+)\)$/);
  if (reference) {
    return parse(theme[reference[1]], theme);
  }
  if (value === 'black') {
    return [0, 0, 0, 1];
  }
  const hex = value.match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    const channels = [0, 2, 4].map((at) => parseInt(hex[1].slice(at, at + 2), 16) / 255);
    return [channels[0], channels[1], channels[2], 1];
  }
  const rgb = value.match(/^rgb\((\d+) (\d+) (\d+) \/ (\d+)%\)$/);
  if (rgb) {
    return [+rgb[1] / 255, +rgb[2] / 255, +rgb[3] / 255, +rgb[4] / 100];
  }
  const mix = value.match(/^color-mix\(in oklab, (.+), (.+) (\d+)%\)$/);
  if (mix) {
    const base = toOklab(parse(mix[1], theme));
    const other = toOklab(parse(mix[2], theme));
    const weight = +mix[3] / 100;
    return fromOklab(base.map((channel, index) => channel * (1 - weight) + other[index] * weight));
  }
  throw new Error(`Unsupported token value: ${value}`);
}

function over([r, g, b, a]: Rgba, [br, bg, bb]: Rgba): Rgba {
  return [r * a + br * (1 - a), g * a + bg * (1 - a), b * a + bb * (1 - a), 1];
}

function luminance([r, g, b]: Rgba) {
  const [lr, lg, lb] = [r, g, b].map(toLinear);
  return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
}

function contrast(theme: Record<string, string>, foreground: string, background: string) {
  const back = parse(theme[background], theme);
  const front = over(parse(theme[foreground], theme), back);
  const [high, low] = [luminance(front), luminance(back)].sort((a, b) => b - a);
  return (high + 0.05) / (low + 0.05);
}

const pages = ['--background', '--surface', '--surface-raised', '--surface-hover'];
const pairs: [string, string[], number][] = [
  ['--foreground', pages, 4.5],
  ['--foreground-muted', pages, 4.5],
  ['--accent', ['--background', '--surface'], 4.5],
  ['--success', ['--background', '--surface'], 4.5],
  ['--warning', ['--background', '--surface'], 4.5],
  ['--danger', ['--background', '--surface'], 4.5],
  [
    '--accent-foreground',
    ['--accent-fill', '--accent-fill-hover', '--accent-fill-pressed', '--danger-fill'],
    4.5,
  ],
  // Non text: control boundaries and the focus ring need 3:1.
  ['--border-strong', ['--background', '--surface'], 3],
  ['--accent', ['--background', '--surface', '--surface-hover'], 3],
];

describe.each([
  ['dark', dark],
  ['light', light],
])('%s theme tokens', (_name, theme) => {
  it.each(
    pairs.flatMap(([foreground, backgrounds, ratio]) =>
      backgrounds.map((background) => [foreground, background, ratio] as const),
    ),
  )('%s on %s reaches %s:1', (foreground, background, ratio) => {
    expect(contrast(theme, foreground, background)).toBeGreaterThanOrEqual(ratio);
  });
});

it('defines every color token in both themes', () => {
  // Button hover and pressed fills are derived from the table colors, not table rows.
  const names = Object.keys(dark).filter(
    (name) =>
      !/radius|opacity|transition|shadow|icon/.test(name) &&
      !/^--(?:surface|surface-hover|danger)-fill-(?:hover|pressed)$/.test(name),
  );
  expect(names).toHaveLength(19);
  for (const name of names) {
    expect(light[name]).toBeTruthy();
  }
});
