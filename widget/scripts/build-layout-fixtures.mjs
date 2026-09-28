import { build } from 'esbuild';
import { mkdir } from 'node:fs/promises';

await mkdir(new URL('../.local/', import.meta.url), { recursive: true });
for (const [entry, output] of [
  ['react-root.tsx', 'react-layout.js'],
  ['vue-root.ts', 'vue-layout.js'],
]) {
  await build({
    entryPoints: [new URL(`../e2e/${entry}`, import.meta.url).pathname],
    outfile: new URL(`../.local/${output}`, import.meta.url).pathname,
    bundle: true,
    format: 'esm',
    platform: 'browser',
    jsx: 'automatic',
  });
}
