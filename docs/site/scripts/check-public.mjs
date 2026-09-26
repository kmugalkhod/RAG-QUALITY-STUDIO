import {existsSync, readFileSync, readdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';

const root = resolve(import.meta.dirname, '..');
function allFiles(dir) {
  return readdirSync(dir, {withFileTypes: true}).flatMap(entry => {
    const path = resolve(dir, entry.name);
    return entry.isDirectory() ? allFiles(path) : [path];
  });
}
const pages = allFiles(resolve(root, 'docs')).filter(path => path.endsWith('.md'));
const slugs = new Set();
const screenshotReferences = new Set();
for (const path of pages) {
  const body = readFileSync(path, 'utf8');
  const slug = body.match(/^slug: (\S+)/m)?.[1];
  if (!slug || !body.match(/^verified_against: /m) || !body.match(/^title: /m)) {
    throw new Error(`Missing public page metadata: ${path}`);
  }
  if (slugs.has(slug)) throw new Error(`Duplicate public slug: ${slug}`);
  slugs.add(slug);
  if (/\b(TODO|placeholder guide|coming soon)\b/i.test(body)) {
    throw new Error(`Unfinished public content: ${path}`);
  }
  if (/!\[\s*\]\(/.test(body)) throw new Error(`Image lacks alt text: ${path}`);
  for (const [, name] of body.matchAll(/\/img\/screenshots\/([a-zA-Z0-9.-]+\.png)/g)) {
    screenshotReferences.add(name);
  }
  for (const [asset] of body.matchAll(/\/(?:img|examples)\/[a-zA-Z0-9._/-]+/g)) {
    const relative = asset.slice(1);
    if (!existsSync(resolve(root, 'static', relative)) || !existsSync(resolve(root, 'build', relative))) {
      throw new Error(`Missing public asset ${asset} used by ${path}`);
    }
    if (asset.endsWith('.svg')) {
      const svg = readFileSync(resolve(root, 'static', relative), 'utf8');
      if (!/<title\b/.test(svg) || !/<desc\b/.test(svg)) {
        throw new Error(`Referenced diagram needs a title and description: ${asset}`);
      }
    }
  }
  if (/sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|xoxb-[A-Za-z0-9-]{15,}|-----BEGIN (?:RSA )?PRIVATE KEY-----/.test(body)) {
    throw new Error(`Potential secret in public page: ${path}`);
  }
  for (const [, language, sample] of body.matchAll(/^```(json|sh|bash|python)\s*\n([\s\S]*?)^```\s*$/gm)) {
    if (language === 'json') {
      try { JSON.parse(sample); } catch { throw new Error(`Invalid JSON sample: ${path}`); }
      continue;
    }
    const command = language === 'python' ? ['python3', ['-c', 'import ast,sys; ast.parse(sys.stdin.read())']] : ['bash', ['-n']];
    const result = spawnSync(command[0], command[1], {input: sample, encoding: 'utf8'});
    if (result.status !== 0) throw new Error(`Invalid ${language} sample in ${path}: ${result.stderr}`);
  }
  const built = resolve(root, 'build', 'docs', slug.replace(/^\/+|\/+$/g, ''), 'index.html');
  if (!existsSync(built)) throw new Error(`Missing built route: ${slug}`);
}
const appFiles = allFiles(resolve(root, '../../frontend/src')).filter(path => path.endsWith('.tsx'));
const routeContract = JSON.parse(readFileSync(resolve(root, 'route-contract.json'), 'utf8'));
const contracted = new Set(routeContract.routes);
if (contracted.size !== routeContract.routes.length || contracted.size !== slugs.size ||
    [...slugs].some(slug => !contracted.has(slug))) {
  throw new Error('Public routes differ from the reviewed route contract');
}
if (routeContract.redirects.length > 0) {
  throw new Error('A historical redirect needs an implemented and tested Docusaurus redirect before release');
}
for (const path of appFiles) {
  const source = readFileSync(path, 'utf8');
  for (const [, route] of source.matchAll(/docsHref\('([^']+)'\)/g)) {
    if (!slugs.has(`/${route}/`)) throw new Error(`App links to unfinished docs page ${route} in ${path}`);
  }
}
const buildFiles = allFiles(resolve(root, 'build')).map(path => path.slice(root.length + 7));
for (const disallowed of ['implementation-plan', 'documentation-plan', 'architecture.md', '/qa/', '.env']) {
  if (buildFiles.some(path => path.includes(disallowed))) throw new Error(`Internal file published: ${disallowed}`);
}
if (!existsSync(resolve(root, 'build/examples/harbor-desk.txt'))) throw new Error('Synthetic example missing from build');
const examples = resolve(root, 'static/examples');
const exampleReview = readFileSync(resolve(examples, 'README.md'), 'utf8');
for (const name of readdirSync(examples).filter(value => /\.(txt|csv)$/.test(value))) {
  const digest = createHash('sha256').update(readFileSync(resolve(examples, name))).digest('hex');
  if (!exampleReview.includes(`\`${name}\``) || !exampleReview.includes(`\`${digest}\``)) {
    throw new Error(`Missing reviewed hash for synthetic example ${name}`);
  }
}
const screenshotManifest = JSON.parse(readFileSync(resolve(root, 'screenshot-manifest.json'), 'utf8'));
if (!/^\d{4}-\d{2}-\d{2}$/.test(screenshotManifest.captured_on) || !/^[a-f0-9]{7,40}$/.test(screenshotManifest.application_base_commit)) {
  throw new Error('Screenshot manifest needs capture date and application commit');
}
const listedScreenshots = new Set();
for (const entry of screenshotManifest.screenshots) {
  if (!entry.file || !entry.viewport || !entry.scenario || listedScreenshots.has(entry.file)) {
    throw new Error(`Incomplete or duplicate screenshot record: ${entry.file}`);
  }
  listedScreenshots.add(entry.file);
  const file = resolve(root, 'static/img/screenshots', entry.file);
  const png = readFileSync(file);
  if (!png.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex')) || png.readUInt32BE(16) === 0 || png.readUInt32BE(20) === 0) {
    throw new Error(`Invalid screenshot PNG: ${entry.file}`);
  }
  if (!screenshotReferences.has(entry.file)) throw new Error(`Unreferenced public screenshot: ${entry.file}`);
}
for (const name of screenshotReferences) {
  if (!listedScreenshots.has(name)) throw new Error(`Screenshot missing review metadata: ${name}`);
}
const index = readFileSync(resolve(root, 'build/search-index.json'), 'utf8');
if (!index.includes('/docs/start/first-workflow/') || !index.includes('/docs/experiments/compare/') || !index.includes('/docs/api/reference/') || index.includes('/docs/api/schema-models/') || index.includes('implementation-plan.md')) {
  throw new Error('Public local-search index is incomplete or includes internal content');
}
const openapi = JSON.parse(readFileSync(resolve(root, 'build/openapi.json'), 'utf8'));
if (!openapi.paths['/api/health'] || Object.keys(openapi.paths).some(path => path.startsWith('/api/test/'))) {
  throw new Error('Public OpenAPI schema is missing core routes or includes test-only routes');
}
console.log(`Checked ${pages.length} public pages, ${slugs.size} routes, app Help targets, search index and static fixture.`);
