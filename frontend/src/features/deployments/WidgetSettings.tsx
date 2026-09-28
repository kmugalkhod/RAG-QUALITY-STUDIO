import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import * as api from './api';

type Props = { projectId: string; deployment: api.Deployment; canManage: boolean; onSaved: () => void };
const widgetOrigin = 'http://127.0.0.1:5274';
const snippet = (id: string, publicEnabled: boolean) => `<script async src="${widgetOrigin}/v1.0.0/loader.js" data-rqs-deployment-id="${id}"${publicEnabled ? '' : ' data-rqs-token-url="/api/rag-widget/token"'}></script>`;

function AppearancePreview({ deploymentId }: { deploymentId: string }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState<'loading' | 'ready' | 'unavailable'>('loading');

  useEffect(() => {
    setStatus('loading');
    const timeout = window.setTimeout(() => setStatus('unavailable'), 8000);
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== widgetOrigin || event.source !== frame.current?.contentWindow) { return; }
      const data = event.data;
      if (data?.type !== 'preview-ready' || data.version !== '1.0.0' || data.deployment !== deploymentId) { return; }
      window.clearTimeout(timeout);
      setStatus('ready');
    };
    window.addEventListener('message', onMessage);
    return () => { window.clearTimeout(timeout); window.removeEventListener('message', onMessage); };
  }, [attempt, deploymentId]);

  return <div className="space-y-2">
    <h4 className="font-semibold">Appearance preview</h4>
    <p className="text-xs text-muted-foreground">This preview cannot submit a charged question.</p>
    {status === 'loading' && <p role="status" className="text-sm text-muted-foreground">Loading widget preview…</p>}
    {status === 'unavailable' && <div role="alert" className="space-y-2 text-sm text-destructive">
      <p>Widget preview is unavailable. Check that the widget app is running on port 5274.</p>
      <Button type="button" variant="outline" onClick={() => setAttempt(value => value + 1)}>Retry preview</Button>
    </div>}
    <iframe key={attempt} ref={frame} title="Widget appearance preview" src={`${widgetOrigin}/v1.0.0/frame/${deploymentId}?preview=1`} onLoad={() => frame.current?.contentWindow?.postMessage({ type: 'preview-status-request', version: '1.0.0', deployment: deploymentId }, widgetOrigin)} className="h-120 w-full max-w-100 rounded-lg border border-border" />
  </div>;
}

export function WidgetSettings({ projectId, deployment, canManage, onSaved }: Props) {
  const [settings, setSettings] = useState<api.WidgetSettings>();
  const [origins, setOrigins] = useState('');
  const [title, setTitle] = useState('');
  const [greeting, setGreeting] = useState('');
  const [color, setColor] = useState<'blue'|'slate'|'green'>('blue');
  const [position, setPosition] = useState<'left'|'right'>('right');
  const [enabled, setEnabled] = useState(false);
  const [publicEnabled, setPublicEnabled] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    void api.widgetSettings(projectId, deployment.id).then(value => {
      if (!alive) {return;}
      setSettings(value); setOrigins(value.allowed_origins.join('\n')); setTitle(value.branding.title);
      setGreeting(value.branding.greeting); setColor(value.branding.color); setPosition(value.branding.position); setEnabled(value.enabled); setPublicEnabled(value.public_enabled);
    }).catch(cause => { if (alive) {setError((cause as Error).message);} });
    return () => { alive = false; };
  }, [projectId, deployment.id, deployment.revision]);
  async function save(event: FormEvent) {
    event.preventDefault(); if (!settings || !canManage) {return;}
    setBusy(true); setError(''); setMessage('');
    try {
      await api.updateWidgetSettings(projectId, deployment.id, {
        enabled, public_enabled: publicEnabled, allowed_origins: origins.split(/\r?\n/).map(item => item.trim()).filter(Boolean),
        branding: { title: title.trim(), greeting: greeting.trim(), color, position },
      }, settings.revision);
      setMessage('Widget settings saved. Existing browser tokens are checked against the new state.'); onSaved();
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function copy() { try { await navigator.clipboard.writeText(snippet(deployment.id, settings?.public_enabled || false)); setMessage('Embed snippet copied.'); } catch { setError('Copy failed. Select the snippet and copy it manually.'); } }
  return <section aria-labelledby="widget-heading" className="space-y-4 border-t border-border pt-6">
    <h3 id="widget-heading" className="text-base font-semibold">Website widget</h3>
    <p className="text-sm text-muted-foreground">Deployment ID: <code>{deployment.id}</code>. Enable public visitor access for a one-script embed that lets anyone on an allowed website ask questions within this deployment’s saved limits.</p>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {message && <p role="status" className="text-sm text-success">{message}</p>}
    {!settings ? <p role="status">Loading widget settings…</p> : <>
      {deployment.state !== 'active' && <p role="alert">Promote or resume this deployment before the widget can answer questions.</p>}
      {!settings.allowed_origins.length && <p role="status">Add at least one exact site origin before enabling the widget.</p>}
      <form onSubmit={save} className="space-y-4 rounded-lg border border-border p-4">
        <label className="flex items-center gap-2"><input type="checkbox" checked={enabled} disabled={!canManage || busy} onChange={event => setEnabled(event.target.checked)} /> Enable widget access</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={publicEnabled} disabled={!canManage || busy || !enabled} onChange={event => setPublicEnabled(event.target.checked)} /> Allow public visitors to ask questions</label>
        <p className="text-xs text-muted-foreground">Public questions can incur model charges. The saved question rates, queue limits, and daily and monthly budgets apply. Website origins restrict browser embedding but do not authenticate visitors.</p>
        <div className="space-y-1"><Label htmlFor="widget-origins">Allowed website origins, one per line</Label><textarea id="widget-origins" className="w-full rounded-md border border-border bg-background p-2 text-sm" rows={3} value={origins} disabled={!canManage} onChange={event => setOrigins(event.target.value)} placeholder="https://your-site.example" /><p className="text-xs text-muted-foreground">Exact HTTPS origins only; loopback HTTP is allowed for local testing. No wildcards or paths.</p></div>
        <div className="space-y-1"><Label htmlFor="widget-title">Assistant title</Label><Input id="widget-title" maxLength={60} value={title} disabled={!canManage} onChange={event => setTitle(event.target.value)} /></div>
        <div className="space-y-1"><Label htmlFor="widget-greeting">Greeting</Label><Input id="widget-greeting" maxLength={240} value={greeting} disabled={!canManage} onChange={event => setGreeting(event.target.value)} /></div>
        <div className="flex gap-4"><label>Color <select value={color} disabled={!canManage} onChange={event => setColor(event.target.value as typeof color)}><option value="blue">Blue</option><option value="slate">Slate</option><option value="green">Green</option></select></label><label>Position <select value={position} disabled={!canManage} onChange={event => setPosition(event.target.value as typeof position)}><option value="right">Right</option><option value="left">Left</option></select></label></div>
        {canManage && <Button type="submit" disabled={busy || !title.trim()}>Save widget settings</Button>}
      </form>
      <AppearancePreview deploymentId={deployment.id} />
      <div className="space-y-2"><h4 className="font-semibold">Shared root layout snippet</h4><pre className="overflow-x-auto rounded bg-muted p-3 text-xs"><code>{snippet(deployment.id, settings.public_enabled)}</code></pre><Button variant="outline" onClick={() => void copy()}>Copy versioned embed snippet</Button><p className="text-xs text-muted-foreground">Paste this script once in your site’s shared layout. The snippet reflects the saved access mode.</p></div>
      {settings.public_enabled ? <p className="text-sm">Visitors need no login or customer backend. Add the exact website origin above and keep the deployment active. Result content is retained for up to 30 days. Public internet hosting has not been configured; this integration is local only.</p> : <div className="space-y-2 text-sm"><h4 className="font-semibold">Private visitor setup</h4><ol className="list-decimal space-y-1 pl-5"><li>Save a deployment key in your backend secret store. Never put it in HTML, browser storage or the script.</li><li>On every POST to <code>/api/rag-widget/token</code>, verify the visitor session, CSRF or Fetch Metadata, and permission to use this assistant.</li><li>From the backend call <code>POST /v1/answer-deployments/{deployment.id}/widget-tokens</code> with the deployment key and JSON <code>{'{"visitor_session_id":"opaque-per-login-session-32-plus-chars","site_origin":"https://your-site.example"}'}</code>.</li><li>Return only <code>{'{token,expires_at}'}</code> with <code>Cache-Control: no-store</code>. Rate-limit issuance. Allow the pinned script and frame origins in your site CSP.</li></ol><p>Result content is retained for up to 30 days. A public internet ingress has not been configured; this integration is local only.</p></div>}
    </>}
  </section>;
}
