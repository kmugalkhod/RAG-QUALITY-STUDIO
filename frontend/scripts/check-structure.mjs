import { readdir } from 'node:fs/promises';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = resolve(frontend, 'src');
const errors = [];

async function inspect(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  if (!entries.length)
    errors.push(`Remove empty source directory: ${relative(frontend, directory)}`);
  for (const entry of entries) {
    const path = resolve(directory, entry.name);
    const name = relative(frontend, path);
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
  }
}

await inspect(source);
if (errors.length) {
  console.error(errors.join('\n'));
  process.exitCode = 1;
} else {
  console.log('Frontend structure checks passed.');
}
