import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = join(dirname(fileURLToPath(import.meta.url)), '..');

function localValue(path, name) {
  let lines;
  try {
    lines = readFileSync(path, 'utf8').split(/\r?\n/);
  } catch {
    return '';
  }
  const line = lines.find((entry) => entry.startsWith(`${name}=`));
  return line?.slice(name.length + 1).replace(/^['"]|['"]$/g, '') ?? '';
}

const secretKey =
  process.env.CLERK_SECRET_KEY || localValue(join(frontend, '..', '.env'), 'CLERK_SECRET_KEY');
const publishableKey =
  process.env.CLERK_PUBLISHABLE_KEY ||
  localValue(join(frontend, '.env.local'), 'VITE_CLERK_PUBLISHABLE_KEY');

if (!secretKey.startsWith('sk_test_') || !publishableKey.startsWith('pk_test_')) {
  process.stderr.write('Clerk browser checks require ignored development keys.\n');
  process.exit(1);
}

const result = spawnSync(
  'npm',
  ['run', 'test:e2e', '--', 'e2e/clerk-auth.spec.ts', '--workers=1', ...process.argv.slice(2)],
  {
    cwd: frontend,
    env: { ...process.env, CLERK_SECRET_KEY: secretKey, CLERK_PUBLISHABLE_KEY: publishableKey },
    stdio: 'inherit',
  },
);
process.exit(result.status ?? 1);
