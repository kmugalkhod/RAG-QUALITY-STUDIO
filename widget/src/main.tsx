import { StrictMode, useEffect, useRef, useState, type FormEvent } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { api, publicConfig, publicToken, type Answer, type Branding, type Config, WidgetError, VERSION } from './api';
import './styles.css';

const preview = new URLSearchParams(location.search).get('preview') === '1';
const deployment = location.pathname.match(/^\/v1\.0\.0\/frame\/([0-9a-fA-F-]{36})$/)?.[1] || '';
type Message = { type: string; version: string; deployment: string; nonce: string; token?: string; expires_at?: string; status?: number; mobile?: boolean };
type PastTurn = { question: string; answer?: Answer; phase: string; runId: string };
const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

function Widget() {
  const [config, setConfig] = useState<Config>();
  const [setupError, setSetupError] = useState('');
  const [open, setOpen] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [phase, setPhase] = useState('');
  const [question, setQuestion] = useState('');
  const [submitted, setSubmitted] = useState('');
  const [answer, setAnswer] = useState<Answer>();
  const [slow, setSlow] = useState(false);
  const [rateSeconds, setRateSeconds] = useState(0);
  const [citationsOpen, setCitationsOpen] = useState(false);
  const [runId, setRunId] = useState('');
  const [pastTurns, setPastTurns] = useState<PastTurn[]>([]);
  const [pastEvidenceOpen, setPastEvidenceOpen] = useState<string[]>([]);
  const token = useRef('');
  const visitor = useRef(crypto.randomUUID().replaceAll('-', ''));
  const tokenFailure = useRef<WidgetError | null>(null);
  const expiry = useRef(0);
  const parentOrigin = useRef('');
  const nonce = useRef('');
  const active = useRef(false);
  const refreshUsed = useRef(false);
  const pending = useRef<((ok: boolean) => void) | null>(null);
  const pendingSubmission = useRef<{ question: string; key: string } | null>(null);
  const polling = useRef(false);
  const slowTimer = useRef<number | undefined>(undefined);
  const launcher = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const transcript = useRef<HTMLElement>(null);
  const [handshake, setHandshake] = useState(false);
  const branding: Branding = config?.branding || { title: 'Ask a question', greeting: 'How can I help?', color: 'blue', position: 'right' };

  const send = (type: string, extra: Record<string, string> = {}) => {
    if (parentOrigin.current && nonce.current) window.parent.postMessage({ type, version: VERSION, deployment, nonce: nonce.current, ...extra }, parentOrigin.current);
  };
  const requestToken = (): Promise<boolean> => {
    tokenFailure.current = null;
    if (config?.public_enabled) {
      setPhase('authenticating');
      return publicToken(deployment, visitor.current, parentOrigin.current).then(value => {
        token.current = value.token;
        expiry.current = Date.parse(value.expires_at);
        return true;
      }).catch(error => {
        tokenFailure.current = error instanceof WidgetError ? error : new WidgetError(503, 'widget_unavailable');
        handleError(tokenFailure.current);
        return false;
      });
    }
    return new Promise(resolve => {
    pending.current = resolve;
    setPhase('authenticating');
    send('token-needed');
    window.setTimeout(() => { if (pending.current === resolve) { pending.current = null; resolve(false); setPhase('unavailable'); } }, 10000);
    });
  };
  const ensureToken = async () => {
    if (token.current && expiry.current > Date.now() + 10000) return true;
    token.current = '';
    return requestToken();
  };
  const call = async <T,>(path: string, init?: RequestInit): Promise<T> => {
    if (!await ensureToken()) throw tokenFailure.current || new WidgetError(401, 'session_required');
    try { return await api<T>(deployment, path, token.current, init); }
    catch (error) {
      if (error instanceof WidgetError && error.status === 401 && !refreshUsed.current) {
        refreshUsed.current = true;
        token.current = '';
        if (await requestToken()) return api<T>(deployment, path, token.current, init);
      }
      throw error;
    }
  };

  useEffect(() => {
    if (!deployment) { setSetupError('Invalid deployment ID.'); return; }
    let alive = true;
    void publicConfig(deployment).then(value => { if (alive) { setConfig(value); if (preview) { setHandshake(true); setOpen(true); setPhase('preview'); } } }).catch(() => { if (alive) setSetupError('Assistant configuration is unavailable.'); });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    if (!preview || !config) return;
    const ready = { type: 'preview-ready', version: VERSION, deployment };
    const onMessage = (event: MessageEvent<Message>) => {
      if (event.source === window.parent && event.data?.type === 'preview-status-request' && event.data.version === VERSION && event.data.deployment === deployment) {
        window.parent.postMessage(ready, event.origin);
      }
    };
    window.addEventListener('message', onMessage);
    window.parent.postMessage(ready, '*');
    return () => window.removeEventListener('message', onMessage);
  }, [config]);
  useEffect(() => {
    if (!config) return;
    const onMessage = (event: MessageEvent<Message>) => {
      const data = event.data;
      if (event.source !== window.parent || !config.allowed_origins.includes(event.origin) || !data || data.version !== VERSION || data.deployment !== deployment || !/^[0-9a-f]{32}$/.test(data.nonce)) return;
      if (data.type === 'init' && !nonce.current) {
        parentOrigin.current = event.origin;
        nonce.current = data.nonce;
        setMobile(data.mobile === true);
        setHandshake(true);
        send('ready', { position: config.branding.position });
        return;
      }
      if (event.origin !== parentOrigin.current || data.nonce !== nonce.current) return;
      if (data.type === 'viewport') { setMobile(data.mobile === true); return; }
      if (data.type === 'clear') { token.current = ''; expiry.current = 0; active.current = false; pendingSubmission.current = null; setOpen(false); setAnswer(undefined); setSubmitted(''); setPastTurns([]); setPastEvidenceOpen([]); return; }
      if (data.type === 'token' && typeof data.token === 'string' && /^rqs_widget_[A-Za-z0-9_-]{43}$/.test(data.token)) {
        token.current = data.token;
        expiry.current = Date.parse(data.expires_at || '');
        pending.current?.(true); pending.current = null;
        setPhase('ready');
      }
      if (data.type === 'token-error') {
        pending.current?.(false); pending.current = null;
        if (data.status === 401 || data.status === 403) setPhase('sign-in');
        else void publicConfig(deployment).then(value => setPhase(value.enabled ? 'unavailable' : 'paused')).catch(() => setPhase('unavailable'));
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [config]);
  useEffect(() => { if (open) window.setTimeout(() => input.current?.focus(), 30); }, [open]);
  useEffect(() => { if (open && transcript.current) transcript.current.scrollTop = transcript.current.scrollHeight; }, [open, submitted, answer, phase, pastTurns]);
  useEffect(() => {
    if (rateSeconds <= 0) return;
    const id = window.setTimeout(() => setRateSeconds(rateSeconds - 1), 1000);
    return () => window.clearTimeout(id);
  }, [rateSeconds]);

  const openPanel = () => {
    if (!handshake || !config?.enabled) return;
    active.current = true; setOpen(true); setPhase('authenticating'); send('open');
    void ensureToken().then(ok => { if (ok) setPhase('ready'); });
  };
  const closePanel = () => {
    active.current = false;
    window.clearTimeout(slowTimer.current);
    if (token.current) void api(deployment, '/revoke', token.current, { method: 'POST' }).catch(() => {});
    token.current = ''; expiry.current = 0;
    pendingSubmission.current = null;
    setOpen(false); setQuestion(''); setSubmitted(''); setAnswer(undefined); setRunId(''); setCitationsOpen(false); setPastTurns([]); setPastEvidenceOpen([]);
    send('close');
    window.setTimeout(() => launcher.current?.focus(), 0);
  };
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape' && open) { event.preventDefault(); closePanel(); }
    if (event.key === 'Tab' && open && mobile) {
      const focusable = Array.from(document.querySelectorAll<HTMLElement>('button:not([disabled]),textarea:not([disabled]),summary'));
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  };
  const handleError = (error: unknown) => {
    if (error instanceof WidgetError) {
      if (error.status === 401) setPhase('sign-in');
      else if (error.status === 429) { setRateSeconds(error.retryAfter || 2); setPhase('rate-limited'); }
      else if (error.code === 'widget_disabled' || error.code === 'deployment_not_active') setPhase('paused');
      else if (error.status === 410) setPhase('expired-result');
      else setPhase('failed');
    } else setPhase('unavailable');
  };
  const pollRun = async (id: string) => {
    if (polling.current) return;
    polling.current = true;
    let interruptions = 0;
    try { while (active.current) {
      try {
        const state = await call<{ status: string; stage: string; retry_after_seconds?: number }>(`/questions/${id}/status`);
        interruptions = 0;
        if (['succeeded','insufficient_evidence','failed','cancelled'].includes(state.status)) {
          const result = await call<Answer>(`/questions/${id}/result`);
          setAnswer(result);
          setPhase(result.status === 'failed' || result.status === 'cancelled' ? 'failed' : result.insufficient_evidence ? 'insufficient' : 'answered');
          setQuestion('');
          return;
        }
        setPhase(state.status === 'queued' ? 'queued' : 'running');
        await wait(Math.min(5000, Math.max(1000, (state.retry_after_seconds || 2) * 1000)));
      } catch (error) {
        if (!active.current) return;
        if (error instanceof WidgetError && error.status < 500 && error.status !== 429) { handleError(error); return; }
        interruptions += 1;
        if (interruptions >= 3) { polling.current = false; setPhase('poll-interrupted'); return; }
        setPhase('running');
        await wait(Math.min(4000, 1000 * 2 ** (interruptions - 1)));
      }
    } } finally { polling.current = false; window.clearTimeout(slowTimer.current); }
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = question.trim();
    if (!text || ['submitting','queued','running','poll-interrupted'].includes(phase)) return;
    active.current = true;
    const priorSubmission = pendingSubmission.current;
    const idempotency = priorSubmission?.question === text ? priorSubmission.key : crypto.randomUUID();
    if (submitted && !priorSubmission) setPastTurns(current => [...current, { question: submitted, answer, phase, runId }].slice(-10));
    pendingSubmission.current = { question: text, key: idempotency };
    setSubmitted(text); setAnswer(undefined); setRunId(''); setCitationsOpen(false); setSlow(false); setPhase('submitting'); refreshUsed.current = false;
    window.setTimeout(() => input.current?.focus(), 0);
    try {
      const accepted = await call<{ id: string }>('/questions', { method: 'POST', headers: { 'Idempotency-Key': idempotency }, body: JSON.stringify({ question: text }) });
      pendingSubmission.current = null;
      setRunId(accepted.id); setPhase('queued');
      window.clearTimeout(slowTimer.current);
      slowTimer.current = window.setTimeout(() => { if (active.current && polling.current) setSlow(true); }, 12000);
      await pollRun(accepted.id);
    } catch (error) { if (active.current) handleError(error); }
  };
  const statusText: Record<string,string> = {
    authenticating: config?.public_enabled ? 'Connecting to the assistant…' : 'Checking your website session…', 'sign-in': 'Sign in to this website or ask its owner for access, then reopen the assistant.',
    unavailable: 'The assistant is temporarily unavailable. Please try again.', ready: 'Ready for your question.',
    submitting: 'Submitting your question…', queued: 'Your question is queued.', running: 'Finding evidence and preparing an answer…',
    'rate-limited': `Too many questions. Try again in ${rateSeconds} seconds.`, paused: 'This assistant is paused.',
    failed: answer?.message || 'The answer could not be completed. Please try again later.',
    'expired-result': 'This result has expired. Ask a new question.', insufficient: 'The available evidence is insufficient to answer this question.',
    'poll-interrupted': 'Connection interrupted. Your accepted question is saved. Check its result again.',
    answered: 'Answer ready.', preview: 'Appearance preview. Questions are unavailable here.',
  };
  const reply = (item: PastTurn, current: boolean) => {
    const expanded = current ? citationsOpen : pastEvidenceOpen.includes(item.runId);
    const toggle = () => current ? setCitationsOpen(!citationsOpen) : setPastEvidenceOpen(values => expanded ? values.filter(id => id !== item.runId) : [...values, item.runId]);
    const openSources = () => current ? setCitationsOpen(true) : setPastEvidenceOpen(values => values.includes(item.runId) ? values : [...values, item.runId]);
    const visibleStatus = !['ready','answered','preview'].includes(item.phase);
    const answerParts = item.answer?.answer?.split(/(\[S\d+\])/g) || [];
    return <div className="turn" key={item.runId || item.question}>
      <div className="message message-user" role="group" aria-label="You asked"><p>{item.question}</p></div>
      <div className="assistant-row"><span className="assistant-mark" aria-hidden="true"><ChatIcon /></span><div className="assistant-content" role="group" aria-label={`${branding.title} replied`}>
        <span className="speaker">{branding.title}</span>
        <p className={`status ${visibleStatus ? '' : 'sr-only'}`} role={current ? 'status' : undefined} aria-live={current ? 'polite' : undefined}>{statusText[item.phase] || setupError}{current && item.phase === 'answered' && item.answer?.answer ? ` ${item.answer.answer}` : ''}</p>
        {current && slow && ['queued','running'].includes(item.phase) && <p className="slow">This is taking longer than usual. You can keep waiting.</p>}
        {item.answer?.answer && !item.answer.insufficient_evidence && <div className="message message-assistant"><h2>Answer</h2><p>{answerParts.map((part, index) => {
          const label = /^\[(S\d+)\]$/.exec(part)?.[1];
          return label && item.answer?.citations?.some(citation => citation.label === label) ? <button className="inline-citation" type="button" key={index} onClick={openSources} aria-label={`View source ${label}`}>[{label.slice(1)}]</button> : part;
        })}</p></div>}
        {!!item.answer?.citations?.length && <div className="citations"><button type="button" aria-expanded={expanded} onClick={toggle}>Evidence ({item.answer.citations.length})</button>{expanded && <ol>{item.answer.citations.map((citation, index) => <li key={index}><strong>{citation.title || `Source ${index + 1}`}</strong>{citation.page != null && <span> · page {citation.page}</span>}{citation.rank != null && <span> · rank {citation.rank}</span>}<p>{(citation.excerpt || citation.text || '').slice(0, 1200)}</p></li>)}</ol>}</div>}
        {current && item.phase === 'poll-interrupted' && item.runId && <button type="button" className="resume" onClick={() => void pollRun(item.runId)}>Check result again</button>}
        {item.runId && <details className="run-details"><summary>Answer details</summary><p>Question run {item.runId.slice(0, 8)}{item.answer?.release_number ? ` · release ${item.answer.release_number}` : ''}</p></details>}
      </div></div>
    </div>;
  };
  return <div className={`widget ${branding.color} ${mobile ? 'mobile' : ''}`} onKeyDown={onKeyDown}>
    {!open ? <button ref={launcher} className="launcher" type="button" onClick={openPanel} aria-label={config && !config.enabled ? `${branding.title} is paused` : setupError ? `${branding.title} is unavailable` : `Open ${branding.title}`} disabled={!handshake || !config?.enabled}>{config && !config.enabled ? 'Paused' : setupError ? 'Offline' : <ChatIcon />}</button> :
      <section className="panel" role={mobile ? 'dialog' : 'region'} aria-modal={mobile ? true : undefined} aria-label={branding.title}>
        <header><span className="header-mark" aria-hidden="true"><ChatIcon /></span><div className="header-copy"><h1>{branding.title}</h1><p>Here to help</p></div><button className="close" type="button" onClick={closePanel} aria-label="Close assistant"><CloseIcon /></button></header>
        <main ref={transcript} className="transcript" aria-label="Conversation">
          <div className="intro"><span className="assistant-mark" aria-hidden="true"><ChatIcon /></span><div><span className="speaker">{branding.title}</span><div className="message message-assistant"><p>{branding.greeting}</p></div></div></div>
          {pastTurns.map(item => reply(item, false))}
          {submitted ? reply({ question: submitted, answer, phase, runId }, true) : <p className={phase === 'ready' ? 'sr-only' : 'status intro-status'} role="status" aria-live="polite">{statusText[phase] || setupError}</p>}
        </main>
        <form className="composer" onSubmit={submit}><label className="sr-only" htmlFor="question">Your question</label><div className="composer-field"><textarea ref={input} id="question" value={question} maxLength={8000} rows={2} placeholder="Ask a question…" onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} disabled={preview} readOnly={['submitting','queued','running'].includes(phase)}/><button type="submit" aria-label="Ask question" disabled={!question.trim() || !['ready','answered','insufficient','failed','expired-result','rate-limited','unavailable'].includes(phase) || rateSeconds > 0}><SendIcon /></button></div><p className="composer-note">Each question is answered separately.</p></form>
        <footer>Questions and answers are retained by RAG Quality Studio for up to 30 days. Contact this website for its privacy policy.</footer>
      </section>}
  </div>;
}

function ChatIcon() { return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 11.5a8 8 0 0 1-8 8 8.6 8.6 0 0 1-3.4-.7L4 20l1.2-4.1A8 8 0 1 1 20 11.5Z"/><path d="M8.5 11.5h7"/></svg>; }
function CloseIcon() { return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M5 5 19 19M19 5 5 19"/></svg>; }
function SendIcon() { return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m5 12 14-7-4 14-3.5-6.5L5 12Z"/><path d="M11.5 12.5 19 5"/></svg>; }

const frameWindow = window as typeof window & { __rqsRoot?: Root };
frameWindow.__rqsRoot ||= createRoot(document.getElementById('root')!);
frameWindow.__rqsRoot.render(<StrictMode><Widget /></StrictMode>);
