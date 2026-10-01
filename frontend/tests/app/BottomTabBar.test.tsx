import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it } from 'vitest';
import { BottomTabBar } from '../../src/app/BottomTabBar';

const projectId = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

beforeEach(() => sessionStorage.clear());

it('marks Pipelines active on the list and the editors', () => {
  render(<BottomTabBar projectId={projectId} page="pipelines" section={null} />);
  const tabs = screen.getByRole('navigation', { name: 'Project sections' });
  expect(within(tabs).getByRole('link', { name: 'Pipelines' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  expect(within(tabs).getByRole('link', { name: 'Overview' })).not.toHaveAttribute('aria-current');
});

it('reopens remembered views and marks More active on its routes', async () => {
  const href = `#/projects/${projectId}/playground?version=saved`;
  sessionStorage.setItem(`playground:${projectId}`, href);
  render(<BottomTabBar projectId={projectId} page="experiments" section={null} />);
  expect(screen.getByRole('link', { name: 'Playground' })).toHaveAttribute('href', href);
  const more = screen.getByRole('button', { name: 'More' });
  expect(more).toHaveAttribute('aria-haspopup', 'dialog');
  expect(more).toHaveAttribute('aria-current', 'page');

  await userEvent.click(more);
  const sheet = screen.getByRole('dialog', { name: 'More' });
  expect(within(sheet).getByRole('link', { name: 'Experiments' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  expect(within(sheet).getByRole('link', { name: 'Connections' })).toHaveAttribute(
    'href',
    `#/projects/${projectId}/settings?section=connections`,
  );
  expect(within(sheet).getByRole('link', { name: 'All projects' })).toHaveAttribute('href', '#/');
});

it('hides while a Playground composer field has focus', async () => {
  render(
    <>
      <textarea aria-label="Question" data-composer="" />
      <BottomTabBar projectId={projectId} page="playground" section={null} />
    </>,
  );
  const tabs = screen.getByRole('navigation', { name: 'Project sections' });
  await userEvent.click(screen.getByLabelText('Question'));
  expect(tabs).toHaveClass('hidden');
  await userEvent.tab();
  expect(tabs).not.toHaveClass('hidden');
});
