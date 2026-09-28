import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { randomBytes } from 'node:crypto';
import { stdin, stdout } from 'node:process';

const deploymentId = process.argv[2];
const port = Number(process.env.DEPLOYMENT_CHECK_PORT || 8787);
const apiPort = 8000;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

if (!uuid.test(deploymentId || '') || !Number.isInteger(port) || port < 1 || port > 65535) {
  console.error('Usage: node tools/deployment-check/server.mjs <deployment-id>');
  process.exit(1);
}

function promptForKey() {
  return new Promise((resolve, reject) => {
    if (!stdin.isTTY) {
      reject(new Error('Run this command in a terminal so the key can be entered privately.'));
      return;
    }
    stdout.write('Paste server key (hidden), then press Enter: ');
    let value = '';
    stdin.setRawMode(true);
    stdin.resume();
    const done = () => {
      stdin.off('data', onData);
      stdin.setRawMode(false);
      stdin.pause();
      stdout.write('\n');
    };
    const onData = (chunk) => {
      for (const character of chunk.toString('utf8')) {
        if (character === '\r' || character === '\n') {
          done();
          resolve(value.trim());
          return;
        }
        if (character === '\u0003') {
          done();
          process.exit(130);
        }
        if (character === '\u007f' || character === '\b') {
          value = value.slice(0, -1);
        } else if (character >= ' ') {
          value += character;
        }
      }
    };
    stdin.on('data', onData);
  });
}

const deploymentKey = process.env.DEPLOYMENT_CHECK_KEY || await promptForKey();
delete process.env.DEPLOYMENT_CHECK_KEY;
if (!deploymentKey) {
  console.error('A server key is required.');
  process.exit(1);
}

const origin = `http://127.0.0.1:${port}`;
const api = `http://127.0.0.1:${apiPort}/v1/answer-deployments/${deploymentId}`;
const csrfToken = randomBytes(32).toString('base64url');
const html = (await readFile(new URL('index.html', import.meta.url), 'utf8'))
  .replaceAll('__LOCAL_TOKEN__', csrfToken)
  .replaceAll('__DEPLOYMENT_ID__', deploymentId);
const javascript = await readFile(new URL('app.js', import.meta.url));

function send(response, status, value) {
  const body = JSON.stringify(value);
  response.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Cache-Control': 'no-store',
  });
  response.end(body);
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    request.on('data', (chunk) => {
      size += chunk.length;
      if (size > 12_000) {
        reject(new Error('Question is too long.'));
        request.destroy();
      } else {
        chunks.push(chunk);
      }
    });
    request.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    request.on('error', reject);
  });
}

async function forward(path, options = {}) {
  const response = await fetch(`${api}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${deploymentKey}`,
      ...(options.headers || {}),
    },
    signal: AbortSignal.timeout(25_000),
  });
  let result;
  try {
    result = await response.json();
  } catch {
    result = { detail: `Deployment API returned HTTP ${response.status}.` };
  }
  return { status: response.status, result };
}

const server = createServer(async (request, response) => {
  response.setHeader('X-Content-Type-Options', 'nosniff');
  response.setHeader('Referrer-Policy', 'no-referrer');
  response.setHeader('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");

  if (request.headers.host !== `127.0.0.1:${port}` || (request.headers.origin && request.headers.origin !== origin)) {
    send(response, 403, { detail: 'Only this local page can use the check server.' });
    return;
  }

  const path = new URL(request.url || '/', origin).pathname;
  if (request.method === 'GET' && path === '/') {
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    response.end(html);
    return;
  }
  if (request.method === 'GET' && path === '/app.js') {
    response.writeHead(200, { 'Content-Type': 'text/javascript; charset=utf-8', 'Cache-Control': 'no-store' });
    response.end(javascript);
    return;
  }
  if (request.headers['x-local-token'] !== csrfToken) {
    send(response, 403, { detail: 'Open the local check page first.' });
    return;
  }

  try {
    if (request.method === 'GET' && path === '/api/deployment') {
      const upstream = await forward('/status');
      send(response, upstream.status, upstream.result);
      return;
    }
    if (request.method === 'POST' && path === '/api/questions') {
      let payload;
      try {
        payload = JSON.parse(await readBody(request));
      } catch {
        send(response, 400, { detail: 'Enter a valid question.' });
        return;
      }
      const question = payload?.question;
      const idempotencyKey = payload?.idempotency_key;
      if (typeof question !== 'string' || !question.trim() || question.length > 8000 || !uuid.test(idempotencyKey || '')) {
        send(response, 422, { detail: 'Enter a question of up to 8,000 characters.' });
        return;
      }
      const upstream = await forward('/questions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
        body: JSON.stringify({ question: question.trim() }),
      });
      send(response, upstream.status, upstream.result);
      return;
    }
    const match = path.match(/^\/api\/questions\/([0-9a-f-]{36})\/result$/i);
    if (request.method === 'GET' && match && uuid.test(match[1])) {
      const upstream = await forward(`/questions/${match[1]}/result`);
      send(response, upstream.status, upstream.result);
      return;
    }
    send(response, 404, { detail: 'Not found.' });
  } catch (error) {
    const timedOut = error?.name === 'TimeoutError';
    send(response, timedOut ? 504 : 502, {
      detail: timedOut
        ? 'The request timed out. Its outcome may be uncertain; retry the same question to reuse its request ID.'
        : 'Could not reach the local deployment API.',
    });
  }
});

server.listen(port, '127.0.0.1', () => {
  console.log(`Local deployment check: ${origin}`);
  console.log(`Deployment: ${deploymentId}`);
  console.log(`Real deployment API: ${api}`);
  console.log('The key stays in this Node process. Stop with Ctrl+C.');
});
