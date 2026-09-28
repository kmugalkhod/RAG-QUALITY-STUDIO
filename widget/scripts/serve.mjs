import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, resolve } from 'node:path';
const host = '127.0.0.1';
const port = 5274;
const api = process.env.WIDGET_API_ORIGIN || 'http://127.0.0.1:8000';
const root = resolve('dist');
const types = { '.js':'text/javascript', '.css':'text/css', '.html':'text/html' };
http.createServer(async (req,res) => {
  const path = new URL(req.url || '/', `http://${host}:${port}`).pathname;
  const frame = /^\/v1\.0\.0\/frame\/([0-9a-fA-F-]{36})$/.exec(path);
  try {
    if (frame) {
      const configResponse = await fetch(`${api}/v1/answer-deployments/${frame[1]}/widget/config`);
      if (!configResponse.ok) throw new Error('Unknown deployment');
      const config = await configResponse.json();
      const preview = new URL(req.url || '/', `http://${host}:${port}`).searchParams.get('preview') === '1';
      const ancestors = [...config.allowed_origins, ...(preview ? ['http://127.0.0.1:5273', 'http://localhost:5273'] : [])].join(' ') || "'none'";
      res.setHeader('Content-Security-Policy', `default-src 'none'; frame-ancestors ${ancestors}; script-src 'self'; style-src 'self'; connect-src ${api}; img-src 'self' data:; base-uri 'none'; form-action 'none'`);
      res.setHeader('Referrer-Policy','no-referrer');
      res.setHeader('Cache-Control','no-store');
      res.setHeader('Content-Type','text/html; charset=utf-8');
      res.end(await readFile(resolve(root,'frame.html')));
      return;
    }
    if (!/^\/(v1\.0\.0\/loader\.js|v1\.0\.0\/assets\/[A-Za-z0-9_.-]+)$/.test(path)) throw new Error('Unknown asset');
    const file = resolve(root, path.slice(1));
    if (!file.startsWith(root+'/')) throw new Error('Invalid path');
    res.setHeader('Content-Type', `${types[extname(file)] || 'application/octet-stream'}; charset=utf-8`);
    res.setHeader('Cache-Control','public, max-age=31536000, immutable');
    res.setHeader('Access-Control-Allow-Origin','*');
    res.end(await readFile(file));
  } catch { res.statusCode = 404; res.end('Not found'); }
}).listen(port,host);
