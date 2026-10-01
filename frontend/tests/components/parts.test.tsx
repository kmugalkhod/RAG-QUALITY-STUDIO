import { createRef } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Callout, Facts, InlineError, Notice, SectionHeading } from '../../src/components/parts';
import { Section } from '../../src/features/experiments/components/parts';

// covers: AC-8 (shared product components) and AC-10 (inline error with Retry)

describe('InlineError', () => {
  test('is an alert carrying its message', () => {
    render(<InlineError>Could not save the pipeline.</InlineError>);
    expect(screen.getByRole('alert')).toHaveTextContent('Could not save the pipeline.');
  });

  test('renders no button without a retry handler', () => {
    render(<InlineError>Failed.</InlineError>);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  test('retries through a custom labeled button', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <InlineError onRetry={onRetry} retryLabel="Retry loading">
        Failed.
      </InlineError>,
    );
    await user.click(screen.getByRole('button', { name: 'Retry loading' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  test('defaults the button label to Retry', () => {
    render(<InlineError onRetry={vi.fn()}>Failed.</InlineError>);
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});

describe('Notice', () => {
  test('keeps an empty live region so later messages are announced', () => {
    const { rerender } = render(<Notice />);
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
    rerender(<Notice>Saved version 2.</Notice>);
    expect(screen.getByRole('status')).toHaveTextContent('Saved version 2.');
  });
});

describe('Facts', () => {
  test('pairs each label with its value', () => {
    render(
      <Facts
        items={[
          ['Chunks', 42],
          ['Model', 'text-embed'],
        ]}
      />,
    );
    const terms = screen.getAllByRole('term').map((node) => node.textContent);
    const values = screen.getAllByRole('definition').map((node) => node.textContent);
    expect(terms).toEqual(['Chunks', 'Model']);
    expect(values).toEqual(['42', 'text-embed']);
  });
});

describe('Callout', () => {
  test('shows its title and body text, so color is never the only signal', () => {
    render(
      <Callout tone="warning" title="Unsaved changes" role="note">
        Save before running.
      </Callout>,
    );
    const callout = screen.getByRole('note');
    expect(callout).toHaveTextContent('Unsaved changes');
    expect(callout).toHaveTextContent('Save before running.');
  });

  test('takes no role unless one is given', () => {
    const { container } = render(<Callout title="Heads up" />);
    expect(container.firstElementChild).not.toHaveAttribute('role');
  });

  test('passes extra attributes through', () => {
    render(<Callout data-testid="callout" id="c1" title="x" />);
    expect(screen.getByTestId('callout')).toHaveAttribute('id', 'c1');
  });
});

describe('SectionHeading', () => {
  test('renders an h3 by default with its description and action', () => {
    render(
      <SectionHeading
        title="Source connections"
        description="Stored credentials stay on the server."
        action={<button type="button">Add connection</button>}
      />,
    );
    expect(screen.getByRole('heading', { level: 3, name: 'Source connections' })).toBeVisible();
    expect(screen.getByText('Stored credentials stay on the server.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Add connection' })).toBeVisible();
  });

  test('renders the requested level', () => {
    render(<SectionHeading level="h2" title="Models" />);
    expect(screen.getByRole('heading', { level: 2, name: 'Models' })).toBeInTheDocument();
  });

  test('a heading ref makes the heading a programmatic focus target only', () => {
    const ref = createRef<HTMLHeadingElement>();
    render(<SectionHeading title="Results" headingRef={ref} />);
    expect(ref.current).toHaveAttribute('tabindex', '-1');
    ref.current?.focus();
    expect(ref.current).toHaveFocus();
  });

  test('without a ref the heading is not focusable', () => {
    render(<SectionHeading title="Results" />);
    expect(screen.getByRole('heading', { name: 'Results' })).not.toHaveAttribute('tabindex');
  });
});

describe('experiments Section', () => {
  test('is a region named by its heading', () => {
    render(
      <Section id="paired" title="Paired comparison" description="Same questions, two runs.">
        <table />
      </Section>,
    );
    const region = screen.getByRole('region', { name: 'Paired comparison' });
    expect(region).toHaveTextContent('Same questions, two runs.');
  });
});
