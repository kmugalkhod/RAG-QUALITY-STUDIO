import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  IngestionToolbar,
  PhoneMenuItems,
} from '../../../src/features/ingestion-pipelines/components/IngestionToolbar';
import { IngestionRunStrip } from '../../../src/features/ingestion-pipelines/components/IngestionRunStrip';
import type {
  IngestionPipelineVersion,
  IngestionRun,
} from '../../../src/features/ingestion-pipelines/model';
import { plural } from '../../../src/lib/utils';

// Spec 0015 U2 and U5. jsdom applies no media queries, so these check that the phone
// controls exist and work; Playwright measures the phone layout itself.
const saved = { id: 'v1', version: 1 } as IngestionPipelineVersion;

function toolbar(props: Partial<Parameters<typeof IngestionToolbar>[0]> = {}) {
  const handlers = { onRun: vi.fn(), onSave: vi.fn(), onPreview: vi.fn(), onDiscard: vi.fn() };
  render(
    <IngestionToolbar
      backHref="#/projects/p/pipelines?kind=ingestion"
      name="Docs"
      saved={saved}
      versions={[saved]}
      dirty={false}
      legacy={false}
      runLabel="Run ingestion"
      canPreview
      canSave={false}
      onNameChange={vi.fn()}
      onVersionSelect={vi.fn()}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

describe('phone toolbar', () => {
  it('has a short Run button on the name line that starts the run', async () => {
    const handlers = toolbar();
    const buttons = screen.getAllByRole('button', { name: /Run/ });
    expect(buttons.map((button) => button.textContent)).toEqual(['Run', 'Run ingestion']);
    await userEvent.click(buttons[0]);
    expect(handlers.onRun).toHaveBeenCalledOnce();
  });

  it('names the full run in the short button for long labels', () => {
    toolbar({ runLabel: 'Collect source & publish index' });
    expect(
      screen.getByRole('button', { name: 'Run: Collect source & publish index' }),
    ).toHaveTextContent('Run');
  });

  it('renders the save status once and moves it to the second line on phones', () => {
    toolbar({ dirty: true });
    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('Unsaved changes');
    expect(status).toHaveClass('max-md:order-2');
    expect(screen.getAllByText('Unsaved changes')).toHaveLength(1);
  });
});

describe('phone "…" menu items', () => {
  function items(phone = {}) {
    const actions = {
      canPreview: true,
      canSave: true,
      canDiscard: true,
      onPreview: vi.fn(),
      onSave: vi.fn(),
      onDiscard: vi.fn(),
      ...phone,
    };
    const onDone = vi.fn();
    render(<PhoneMenuItems actions={actions} onDone={onDone} />);
    return { actions, onDone };
  }

  it('holds Preview processing, Save version and Discard, each closing the menu', () => {
    const { actions, onDone } = items();
    fireEvent.click(screen.getByRole('button', { name: 'Save version' }));
    fireEvent.click(screen.getByRole('button', { name: 'Preview processing' }));
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(actions.onSave).toHaveBeenCalledOnce();
    expect(actions.onPreview).toHaveBeenCalledOnce();
    expect(actions.onDiscard).toHaveBeenCalledOnce();
    expect(onDone).toHaveBeenCalledTimes(3);
  });

  it('disables what cannot run and hides Discard without changes', () => {
    items({ canSave: false, canPreview: false, canDiscard: false });
    expect(screen.getByRole('button', { name: 'Save version' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(screen.getByRole('button', { name: 'Preview processing' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(screen.queryByRole('button', { name: 'Discard changes' })).not.toBeInTheDocument();
  });
});

describe('phone run strip', () => {
  it('says which index version is ready on the one line', () => {
    render(
      <IngestionRunStrip
        projectId="p"
        run={
          {
            status: 'succeeded',
            stage: 'complete',
            progress: 100,
            new_count: 1,
            changed_count: 0,
            unchanged_count: 0,
            removed_count: 0,
            failed_count: 0,
            published_index_id: 'index-1',
            published_index_version: 1,
          } as unknown as IngestionRun
        }
        displayStatus="succeeded"
        busy={false}
        detailsOpen={false}
        onCancel={vi.fn()}
        onToggleDetails={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );
    expect(screen.getByText('· index v1 ready')).toHaveClass('md:hidden');
    expect(screen.getByTestId('published-index')).toHaveClass('max-md:hidden');
    expect(screen.getByRole('button', { name: 'Run details' })).toBeInTheDocument();
  });
});

describe('plural', () => {
  it('uses the singular for one', () => {
    expect(plural(1, 'chunk')).toBe('1 chunk');
    expect(plural(0, 'chunk')).toBe('0 chunks');
    expect(plural(1200, 'token')).toBe('1,200 tokens');
    expect(plural(2, 'analysis', 'analyses')).toBe('2 analyses');
  });
});
