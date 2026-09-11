import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { RunResult, RunInspector } from './AnswerResult';
import type { QueryRun } from './api';

const run: QueryRun = { id: 'r', project_id: 'p', index_id: 'i', index_version: 2, question: 'Question?', answer: 'Claim [S1] [S99]', status: 'succeeded', error: null, created_at: '2026-09-10', snapshot: { top_k: 1, prompt_version: 'v1', evidence: [{ label: 'S1', text: 'Source text', filename: 'source.pdf', page_number: 3, rank: 1, document_id: 'd', content_hash: 'hash', run_id: 'processing', processing_version: 1, ordinal: 0, start_char: 0, end_char: 11, cosine_distance: 0.2 }], retrieval_ms: 10, generation_ms: 20, total_ms: 30, usage: null, cost_usd: null, cost_basis: null, citations: { valid: ['S1'], invalid: ['S99'], missing: false, semantics: 'Reference membership only.' } } };

describe('query result', () => {
  it('opens supplied citations in the inspector without showing evidence in chat', async () => {
    const inspect = vi.fn();
    render(<RunResult run={run} onCitation={inspect}/>);
    expect(screen.getByRole('button', { name: '[S1]' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '[S99]' })).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid citation references: S99');
    expect(screen.queryByText('Source text')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '[S1]' }));
    expect(inspect).toHaveBeenCalledWith('S1');
  });
  it('shows failed runs and preserved evidence', () => {
    render(<><RunResult run={{ ...run, status: 'failed', answer: null, error: 'OpenRouter timed out.' }}/><RunInspector run={run} mode="sources"/></>);
    expect(screen.getByRole('heading', { name: 'Answer failed' })).toBeInTheDocument();
    expect(screen.getByText('OpenRouter timed out.')).toBeInTheDocument();
    expect(screen.getByText('Source text')).toBeInTheDocument();
  });
  it('focuses the selected source and preserves provenance', () => {
    render(<RunInspector run={run} mode="sources" sourceLabel="S1"/>);
    expect(screen.getByText(/Page 3/)).toHaveTextContent('Passage 1');
    expect(document.getElementById('evidence-S1')).toHaveFocus();
  });
  it('keeps unavailable cost and usage explicit in run details', () => {
    render(<RunInspector run={run} mode="details"/>);
    expect(screen.getAllByText('Unavailable')).toHaveLength(2);
  });
  it('shows insufficient evidence explicitly', async () => {
    render(<RunResult run={{ ...run, status: 'insufficient_evidence', answer: 'INSUFFICIENT_EVIDENCE: No answer.' }}/>);
    expect(screen.getByRole('heading', { name: 'Insufficient evidence' })).toBeInTheDocument();
    await userEvent.setup().tab();
  });
});
