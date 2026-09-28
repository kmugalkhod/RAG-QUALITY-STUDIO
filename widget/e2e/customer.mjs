/* Local authenticated customer backend fixture. Never serve this file publicly. */
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { createHmac, randomBytes } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const config = JSON.parse(readFileSync(join(tmpdir(), `rag-widget-browser-${process.getuid()}.json`), 'utf8'));
const sessions = new Map();
const tokenRequests = new Map();
const origin = 'http://127.0.0.1:5275';
const api = 'http://127.0.0.1:8000';
const cookie = req => (req.headers.cookie || '').match(/(?:^|; )widget_session=([a-f0-9]{48})/)?.[1];
const siteScript = `document.getElementById('login').onclick=async()=>{await fetch('/login',{method:'POST'});location.reload()};document.getElementById('logout').onclick=async()=>{await fetch('/logout',{method:'POST'});location.reload()};`;
const reactPage = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>React root layout fixture</title></head><body data-deployment-id="${config.deployment_id}"><div id="app"></div><script type="module" src="/react-layout.js"></script></body></html>`;
const vuePage = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vue root layout fixture</title></head><body data-deployment-id="${config.deployment_id}"><div id="app"></div><script type="module" src="/vue-layout.js"></script></body></html>`;
const serverPage = help => `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Server rendered layout fixture</title><script src="http://127.0.0.1:5274/v1.0.0/loader.js" data-rqs-deployment-id="${config.deployment_id}" data-rqs-token-url="/api/rag-widget/token"></script></head><body><header><h1>Server rendered customer layout</h1><nav><a href="/server">Overview</a> <a href="/server/help">Help</a></nav><button id="login">Sign in</button> <button id="logout">Sign out</button></header><main><h2>${help ? 'Help route' : 'Overview route'}</h2><p>The shared server layout loads the assistant before the body exists.</p></main><script src="/site.js"></script></body></html>`;
const page = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Customer site fixture</title></head><body><header><h1>Customer site fixture</h1><nav><a href="/">Home</a> <a href="/help">Help</a></nav><button id="login">Sign in</button> <button id="logout">Sign out</button></header><main><h2>Website content</h2><p>The private assistant is loaded from the shared root layout on both pages.</p></main><script src="/site.js"></script><script async src="http://127.0.0.1:5274/v1.0.0/loader.js" data-rqs-deployment-id="${config.deployment_id}" data-rqs-token-url="/api/rag-widget/token"></script></body></html>`;
http.createServer(async (req,res) => {
  const url = new URL(req.url || '/',origin);
  if (req.headers.host?.toLowerCase() === 'localhost:5275') {
    res.statusCode = 308;
    res.setHeader('Location', `${origin}${url.pathname}${url.search}`);
    res.end();
    return;
  }
  res.setHeader('Cache-Control','no-store');
  res.setHeader('Referrer-Policy','no-referrer');
  if (req.method==='POST' && url.pathname==='/login') {
    const sid=randomBytes(24).toString('hex'); sessions.set(sid,Date.now());
    res.setHeader('Set-Cookie',`widget_session=${sid}; HttpOnly; SameSite=Strict; Path=/`); res.end('ok'); return;
  }
  if (req.method==='POST' && url.pathname==='/logout') {
    const sid=cookie(req);
    if (req.headers.origin===origin && sid && sessions.has(sid)) {
      const visitor=createHmac('sha256',config.deployment_key).update(sid).digest('base64url');
      try { await fetch(`${api}/v1/answer-deployments/${config.deployment_id}/widget-tokens/revoke-session`,{method:'POST',headers:{Authorization:`Bearer ${config.deployment_key}`,'Content-Type':'application/json'},body:JSON.stringify({visitor_session_id:visitor,site_origin:origin})}); } catch {}
    }
    sessions.delete(sid); tokenRequests.delete(sid); res.setHeader('Set-Cookie','widget_session=; HttpOnly; SameSite=Strict; Max-Age=0; Path=/'); res.end('ok'); return;
  }
  if (req.method==='POST' && url.pathname==='/api/rag-widget/token') {
    const sid=cookie(req);
    if (req.headers.origin!==origin || req.headers['x-requested-with']!=='RQS-Widget' || !sid || !sessions.has(sid)) { res.statusCode=401; res.end('Authentication required'); return; }
    const now=Date.now();
    const recent=(tokenRequests.get(sid)||[]).filter(at=>now-at<60_000);
    if (recent.length>=12) { res.statusCode=429; res.setHeader('Retry-After','60'); res.end('Too many token requests'); return; }
    recent.push(now); tokenRequests.set(sid,recent);
    const visitor=createHmac('sha256',config.deployment_key).update(sid).digest('base64url');
    try {
      const response=await fetch(`${api}/v1/answer-deployments/${config.deployment_id}/widget-tokens`,{method:'POST',headers:{Authorization:`Bearer ${config.deployment_key}`,'Content-Type':'application/json'},body:JSON.stringify({visitor_session_id:visitor,site_origin:origin})});
      if (!response.ok) { res.statusCode=response.status===429?429:503; res.end('Token unavailable'); return; }
      const body=await response.text(); res.setHeader('Content-Type','application/json'); res.end(body); return;
    } catch { res.statusCode=503; res.end('Token unavailable'); return; }
  }
  if (req.method==='GET' && url.pathname==='/react-layout.js') { res.setHeader('Content-Type','text/javascript'); res.end(readFileSync(new URL('../.local/react-layout.js', import.meta.url))); return; }
  if (req.method==='GET' && url.pathname==='/vue-layout.js') { res.setHeader('Content-Type','text/javascript'); res.end(readFileSync(new URL('../.local/vue-layout.js', import.meta.url))); return; }
  if (req.method==='GET' && url.pathname==='/site.js') { res.setHeader('Content-Type','text/javascript'); res.end(siteScript); return; }
  if (req.method==='GET' && ['/react', '/react/help'].includes(url.pathname)) { res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'self' http://127.0.0.1:5274; frame-src http://127.0.0.1:5274; connect-src 'self' http://127.0.0.1:5274; base-uri 'none'; form-action 'none'"); res.setHeader('Content-Type','text/html; charset=utf-8'); res.end(reactPage); return; }
  if (req.method==='GET' && ['/vue', '/vue/help'].includes(url.pathname)) { res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'self' http://127.0.0.1:5274; frame-src http://127.0.0.1:5274; connect-src 'self' http://127.0.0.1:5274; base-uri 'none'; form-action 'none'"); res.setHeader('Content-Type','text/html; charset=utf-8'); res.end(vuePage); return; }
  if (req.method==='GET' && ['/server', '/server/help'].includes(url.pathname)) { res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'self' http://127.0.0.1:5274; frame-src http://127.0.0.1:5274; connect-src 'self'; base-uri 'none'; form-action 'none'"); res.setHeader('Content-Type','text/html; charset=utf-8'); res.end(serverPage(url.pathname.endsWith('/help'))); return; }
  if (req.method==='GET' && ['/', '/help'].includes(url.pathname)) { res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'self' http://127.0.0.1:5274; frame-src http://127.0.0.1:5274; connect-src 'self'; base-uri 'none'; form-action 'none'"); res.setHeader('Content-Type','text/html; charset=utf-8'); res.end(page); return; }
  res.statusCode=404; res.end('Not found');
}).listen(5275,'127.0.0.1');
