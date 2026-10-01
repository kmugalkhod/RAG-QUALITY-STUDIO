import { fireEvent, render, screen } from '@testing-library/react';

import { EmptyState } from '../../src/components/states/EmptyState';
import { ErrorState } from '../../src/components/states/ErrorState';
import { LoadingState } from '../../src/components/states/LoadingState';
import { PageHeader } from '../../src/components/PageHeader';
import { Button } from '../../src/components/ui/button';

test('loading announces itself through a status region with a test id', () => {
  render(<LoadingState label="Loading documents…" rows={2} />);
  const status = screen.getByRole('status');
  expect(status).toHaveAttribute('data-testid', 'state-loading');
  expect(status).toHaveTextContent('Loading documents…');
});

test('empty shows its message and one action', () => {
  render(
    <EmptyState
      title="No documents"
      description="Upload a PDF or TXT file to start."
      action={<Button>Upload documents</Button>}
    />,
  );
  expect(screen.getByTestId('state-empty')).toHaveTextContent('No documents');
  expect(screen.getAllByRole('button')).toHaveLength(1);
});

test('error shows the safe message and retries', () => {
  const onRetry = vi.fn();
  render(<ErrorState message="The server did not respond." onRetry={onRetry} />);
  expect(screen.getByRole('alert')).toHaveTextContent('The server did not respond.');
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  expect(onRetry).toHaveBeenCalledOnce();
});

test('error without a retry handler renders no button', () => {
  render(<ErrorState message="Not found." />);
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});

test('page header renders a heading, meta and its action', () => {
  render(<PageHeader title="Knowledge" meta="3 documents" action={<Button>Upload</Button>} />);
  expect(screen.getByRole('heading', { level: 1, name: 'Knowledge' })).toBeInTheDocument();
  expect(screen.getByText('3 documents')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Upload' })).toBeInTheDocument();
});
