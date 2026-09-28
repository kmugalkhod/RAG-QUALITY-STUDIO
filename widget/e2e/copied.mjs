/* A copied public script with no authenticated token endpoint. */
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const { deployment_id } = JSON.parse(readFileSync(join(tmpdir(), `rag-widget-browser-${process.getuid()}.json`), 'utf8'));
const html = `<!doctype html><html><head><title>Copied embed</title></head><body><h1>Copied embed</h1><script async src="http://127.0.0.1:5274/v1.0.0/loader.js" data-rqs-deployment-id="${deployment_id}" data-rqs-token-url="/api/rag-widget/token"></script></body></html>`;
http.createServer((req,res) => { if (req.url === '/api/rag-widget/token') { res.statusCode=401; res.end('Not authorized'); return; } res.setHeader('Content-Type','text/html'); res.end(html); }).listen(5276,'127.0.0.1');
