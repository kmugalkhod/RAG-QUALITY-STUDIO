import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../../src/lib/api';
import * as api from '../../../src/features/pipelines/api';
import { EditorErrorBoundary, PipelineRoute } from '../../../src/features/pipelines/PipelineRoute';

vi.mock('../../../src/features/pipelines/PipelineEditor', () => ({
  PipelineEditor: ({ pipelineId }: { pipelineId: string }) => <p>Answer editor {pipelineId}</p>,
}));
vi.mock('../../../src/features/ingestion-pipelines/IngestionPipelineEditor', () => ({
  IngestionPipelineEditor: ({ pipelineId }: { pipelineId: string }) => (
    <p>Ingestion editor {pipelineId}</p>
  ),
}));

const PROJECT = '11111111-1111-1111-1111-111111111111';

beforeEach(() => {
  window.location.hash = '';
});
afterEach(() => vi.restoreAllMocks());

function pipeline(kind: 'answer' | 'ingestion') {
  return { id: 'p1', name: 'Saved', kind };
}

describe('pipeline links open the saved kind', () => {
  it('opens an ingestion pipeline linked without ?kind and corrects the address', async () => {
    vi.spyOn(api, 'getPipeline').mockResolvedValue(pipeline('ingestion'));
    window.location.hash = `#/projects/${PROJECT}/pipelines/p1?version=v2`;
    render(<PipelineRoute projectId={PROJECT} pipelineId="p1" versionId="v2" linkedKind={null} />);
    expect(await screen.findByText('Ingestion editor p1')).toBeInTheDocument();
    expect(window.location.hash).toBe(
      `#/projects/${PROJECT}/pipelines/p1?kind=ingestion&version=v2`,
    );
    expect(api.getPipeline).toHaveBeenCalledWith(PROJECT, 'p1');
  });

  it('opens an answer pipeline linked as ingestion in the answer editor', async () => {
    vi.spyOn(api, 'getPipeline').mockResolvedValue(pipeline('answer'));
    window.location.hash = `#/projects/${PROJECT}/pipelines/p1?kind=ingestion`;
    render(
      <PipelineRoute projectId={PROJECT} pipelineId="p1" versionId="" linkedKind="ingestion" />,
    );
    expect(await screen.findByText('Answer editor p1')).toBeInTheDocument();
    expect(window.location.hash).toBe(`#/projects/${PROJECT}/pipelines/p1`);
  });

  it('leaves a correct address unchanged', async () => {
    vi.spyOn(api, 'getPipeline').mockResolvedValue(pipeline('ingestion'));
    const replace = vi.spyOn(window.history, 'replaceState');
    render(
      <PipelineRoute projectId={PROJECT} pipelineId="p1" versionId="" linkedKind="ingestion" />,
    );
    expect(await screen.findByText('Ingestion editor p1')).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it('opens a new pipeline by the kind the link names without a request', async () => {
    const read = vi.spyOn(api, 'getPipeline');
    render(
      <PipelineRoute projectId={PROJECT} pipelineId="new" versionId="" linkedKind="ingestion" />,
    );
    expect(await screen.findByText('Ingestion editor new')).toBeInTheDocument();
    expect(read).not.toHaveBeenCalled();
  });

  it.each([404, 422])('shows Pipeline not found for a %i', async (status) => {
    vi.spyOn(api, 'getPipeline').mockRejectedValue(new ApiError('Not found', status));
    render(<PipelineRoute projectId={PROJECT} pipelineId="p1" versionId="" linkedKind={null} />);
    expect(await screen.findByRole('heading', { name: 'Pipeline not found' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Back to pipelines' })).toHaveAttribute(
      'href',
      `#/projects/${PROJECT}/pipelines`,
    );
  });

  it('offers a retry when the request fails for another reason', async () => {
    vi.spyOn(api, 'getPipeline').mockRejectedValue(new ApiError('Service unavailable', 503));
    render(<PipelineRoute projectId={PROJECT} pipelineId="p1" versionId="" linkedKind={null} />);
    expect(await screen.findByText('The pipeline could not be loaded')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeVisible();
  });
});

describe('editor error boundary', () => {
  it('shows a safe message instead of a blank page', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    function Broken(): never {
      throw new Error('node type "source" is unknown');
    }
    render(
      <EditorErrorBoundary projectId={PROJECT} kind="ingestion">
        <Broken />
      </EditorErrorBoundary>,
    );
    expect(screen.getByText('The pipeline editor could not be shown')).toBeVisible();
    expect(screen.queryByText(/unknown/)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to pipelines' })).toHaveAttribute(
      'href',
      `#/projects/${PROJECT}/pipelines?kind=ingestion`,
    );
  });
});

it('keeps the linked kind when the response has no valid kind', async () => {
  vi.spyOn(api, 'getPipeline').mockResolvedValue({ id: 'p1', name: 'Odd' } as never);
  render(<PipelineRoute projectId={PROJECT} pipelineId="p1" versionId="" linkedKind="ingestion" />);
  expect(await screen.findByText('Ingestion editor p1')).toBeInTheDocument();
});
