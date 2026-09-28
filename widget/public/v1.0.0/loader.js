/* RAG Quality Studio widget protocol 1.0.0. No credentials are embedded here. */
(() => {
  const script = document.currentScript;
  if (!script || window.__rqsWidgetV1) return;
  const deployment = script.dataset.rqsDeploymentId;
  const tokenPath = script.dataset.rqsTokenUrl;
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const version = '1.0.0';
  let assetOrigin;
  try {
    const url = new URL(script.src);
    if (url.pathname !== '/v1.0.0/loader.js') return;
    assetOrigin = url.origin;
    if (!uuid.test(deployment || '')) return;
    if (tokenPath) {
      const token = new URL(tokenPath, location.origin);
      if (!tokenPath.startsWith('/') || tokenPath.startsWith('//') || token.origin !== location.origin || token.search || token.hash) return;
    }
    if (location.protocol !== 'https:' && !['localhost', '127.0.0.1'].includes(location.hostname)) return;
  } catch { return; }
  window.__rqsWidgetV1 = true;
  const nonce = Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2, '0')).join('');
  const frame = document.createElement('iframe');
  frame.title = 'Website question assistant';
  frame.setAttribute('aria-label', 'Website question assistant');
  frame.referrerPolicy = 'no-referrer';
  frame.src = `${assetOrigin}/v1.0.0/frame/${deployment}`;
  frame.style.cssText = 'position:fixed;bottom:16px;right:16px;width:76px;height:76px;border:0;z-index:2147483000;background:transparent;';
  const send = (type, extra = {}) => frame.contentWindow?.postMessage({ type, version, deployment, nonce, ...extra }, assetOrigin);
  const mobile = () => matchMedia('(max-width: 600px)').matches;
  let opened = false;
  let side = 'right';
  const place = () => { frame.style.left = side === 'left' ? '16px' : 'auto'; frame.style.right = side === 'right' ? '16px' : 'auto'; };
  let fetching = false;
  async function getToken() {
    if (!tokenPath) { send('token-error', { status: 403 }); return; }
    if (fetching) return;
    fetching = true;
    try {
      const result = await fetch(tokenPath, { method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: { 'Accept': 'application/json', 'X-Requested-With': 'RQS-Widget' }, redirect: 'error' });
      if (!result.ok) { send('token-error', { status: result.status }); return; }
      const body = await result.json();
      if (typeof body.token !== 'string' || !/^rqs_widget_[A-Za-z0-9_-]{43}$/.test(body.token)) throw new Error('Invalid token response');
      send('token', { token: body.token, expires_at: body.expires_at });
    } catch { send('token-error', { status: 503 }); }
    finally { fetching = false; }
  }
  let initialized = false;
  let initTimer;
  let unavailable;
  const showUnavailable = () => {
    if (initialized || unavailable) return;
    unavailable = document.createElement('div');
    unavailable.setAttribute('role', 'status');
    unavailable.textContent = 'Assistant unavailable. Check this site widget setup.';
    unavailable.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:2147483000;max-width:280px;padding:12px 14px;border:1px solid #cbd5e1;border-radius:12px;background:#fff;color:#243047;box-shadow:0 8px 24px #14223e3d;font:14px/1.4 system-ui,sans-serif;';
    frame.style.display = 'none';
    (document.body || document.documentElement).appendChild(unavailable);
  };
  frame.addEventListener('load', () => {
    send('init', { mobile: mobile() });
    initTimer = window.setInterval(() => { if (!initialized) send('init', { mobile: mobile() }); else clearInterval(initTimer); }, 500);
    window.setTimeout(() => clearInterval(initTimer), 10000);
  });
  window.addEventListener('message', event => {
    if (event.source !== frame.contentWindow || event.origin !== assetOrigin) return;
    const data = event.data;
    if (!data || data.version !== version || data.deployment !== deployment || data.nonce !== nonce) return;
    if (data.type === 'ready') { initialized = true; unavailable?.remove(); unavailable = null; frame.style.display = ''; side = data.position === 'left' ? 'left' : 'right'; place(); return; }
    if (data.type === 'token-needed') { void getToken(); return; }
    if (data.type === 'open') {
      opened = true;
      frame.style.width = mobile() ? '100vw' : 'min(400px, calc(100vw - 32px))';
      frame.style.height = mobile() ? '100dvh' : 'min(640px, calc(100dvh - 32px))';
      frame.style.bottom = mobile() ? '0' : '16px';
      if (mobile()) { frame.style.left = '0'; frame.style.right = '0'; } else place();
      return;
    }
    if (data.type === 'close') {
      opened = false;
      frame.style.width = '76px'; frame.style.height = '76px'; frame.style.bottom = '16px'; place();
    }
  });
  window.addEventListener('pagehide', () => send('clear'));
  window.addEventListener('resize', () => {
    send('viewport', { mobile: mobile() });
    if (opened) { const narrow = mobile(); frame.style.width = narrow ? '100vw' : 'min(400px, calc(100vw - 32px))'; frame.style.height = narrow ? '100dvh' : 'min(640px, calc(100dvh - 32px))'; frame.style.bottom = narrow ? '0' : '16px'; if (narrow) { frame.style.left = '0'; frame.style.right = '0'; } else place(); }
  });
  if (document.body) document.body.appendChild(frame);
  else document.addEventListener('DOMContentLoaded', () => (document.body || document.documentElement).appendChild(frame), { once: true });
  window.setTimeout(showUnavailable, 10000);
})();
