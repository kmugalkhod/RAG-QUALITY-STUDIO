const token = document.querySelector('meta[name="local-token"]').content;
const form = document.getElementById('question-form');
const question = document.getElementById('question');
const submit = document.getElementById('submit');
const statusTag = document.getElementById('deployment-status');
const statusText = document.getElementById('deployment-status-text');
const errorBox = document.getElementById('error');
const resultBox = document.getElementById('result');
const resultTitle = document.getElementById('result-title');
const resultMeta = document.getElementById('result-meta');
const answer = document.getElementById('answer');
const citations = document.getElementById('citations');
const citationList = document.getElementById('citation-list');

let accepting = false;
let busy = false;
let requestId = null;
let submittedQuestion = '';

function error(message) {
  errorBox.textContent = message || '';
  errorBox.classList.toggle('visible', Boolean(message));
}

function showResult(title, text, meta = '') {
  resultBox.classList.add('visible');
  resultTitle.textContent = title;
  resultMeta.textContent = meta;
  answer.textContent = text;
}

function setBusy(value) {
  busy = value;
  submit.disabled = value || !accepting;
  question.disabled = value;
  submit.textContent = value ? 'Waiting for answer…' : 'Ask deployment';
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'X-Local-Token': token, ...(options.headers || {}) },
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === 'string' ? detail : `Request failed (HTTP ${response.status}).`);
  }
  return { response, data };
}

async function checkDeployment() {
  try {
    const { data } = await api('/api/deployment');
    accepting = data.accepting_questions === true;
    statusTag.classList.toggle('ready', accepting);
    statusTag.classList.toggle('error', !accepting);
    statusText.textContent = accepting
      ? `Accepting questions · Release ${data.active_release_number}`
      : `Not accepting questions · ${data.state}`;
  } catch (cause) {
    accepting = false;
    statusTag.classList.add('error');
    statusText.textContent = 'Deployment unavailable';
    error(cause.message);
  }
  submit.disabled = !accepting;
}

function renderFinal(data) {
  const meta = `Run ${data.id || ''}${data.release_number ? ` · Release ${data.release_number}` : ''}`;
  if (data.status === 'succeeded' || data.status === 'insufficient_evidence') {
    showResult(
      data.status === 'insufficient_evidence' ? 'Insufficient evidence' : 'Answer',
      data.answer || 'No answer text was returned.',
      meta,
    );
    citationList.replaceChildren();
    const sources = Array.isArray(data.citations) ? data.citations : [];
    citations.hidden = sources.length === 0;
    for (const source of sources) {
      const card = document.createElement('div');
      card.className = 'citation';
      const title = document.createElement('div');
      title.className = 'citation-title';
      title.textContent = `${source.label || 'Source'} · ${source.title || 'Untitled'}${source.page ? ` · page ${source.page}` : ''}`;
      const excerpt = document.createElement('p');
      excerpt.className = 'citation-excerpt';
      excerpt.textContent = source.excerpt || '';
      card.append(title, excerpt);
      citationList.append(card);
    }
  } else {
    citations.hidden = true;
    showResult('Run did not complete', data.message || data.error_code || data.status || 'Unknown error.', meta);
  }
}

async function poll(runId) {
  for (let attempt = 0; attempt < 90; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const { response, data } = await api(`/api/questions/${runId}/result`);
    if (response.status === 202) {
      showResult('Working on your answer…', `Current stage: ${data.stage || data.status}`, `Run ${runId}`);
      continue;
    }
    renderFinal(data);
    return;
  }
  showResult('Still processing', 'This run is taking longer than three minutes. Check it in Answer Deployments.', `Run ${runId}`);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy || !accepting) return;
  const text = question.value.trim();
  if (!text) {
    error('Enter a question first.');
    question.focus();
    return;
  }
  if (!requestId || submittedQuestion !== text) requestId = crypto.randomUUID();
  submittedQuestion = text;
  error('');
  citations.hidden = true;
  showResult('Submitting question…', 'The deployment will pin this run to its selected release.');
  setBusy(true);
  try {
    const { data } = await api('/api/questions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: text, idempotency_key: requestId }),
    });
    showResult('Question accepted', 'Waiting for the answer worker…', `Run ${data.id} · Release ${data.release_number}`);
    await poll(data.id);
  } catch (cause) {
    error(`${cause.message} Retrying the same question will reuse its request ID.`);
    showResult('Could not finish the check', 'Your question may already have been accepted. Keep the same question if you retry.');
  } finally {
    setBusy(false);
  }
});

void checkDeployment();
