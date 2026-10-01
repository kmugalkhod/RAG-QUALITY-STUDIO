import { fireEvent, render, screen } from '@testing-library/react';
import type { FormEvent } from 'react';

import { Button } from '../../src/components/ui/button';

test('does not submit a parent form unless submit is explicit', () => {
  const onSubmit = vi.fn((event: FormEvent) => event.preventDefault());
  render(
    <form onSubmit={onSubmit}>
      <Button>Secondary action</Button>
      <Button type="submit">Submit form</Button>
    </form>,
  );

  fireEvent.click(screen.getByRole('button', { name: 'Secondary action' }));
  expect(onSubmit).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Submit form' }));
  expect(onSubmit).toHaveBeenCalledOnce();
});

function stubTouch(coarse: boolean) {
  const vibrate = vi.fn(() => true);
  vi.stubGlobal('navigator', { ...navigator, vibrate });
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({ matches: coarse && query === '(pointer: coarse)' })),
  );
  return vibrate;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test('a disabled button stays focusable but ignores click and Enter submit', () => {
  const onClick = vi.fn();
  const onSubmit = vi.fn((event: FormEvent) => event.preventDefault());
  render(
    <form onSubmit={onSubmit}>
      <input aria-label="Name" />
      <Button type="submit" disabled onClick={onClick}>
        Save
      </Button>
    </form>,
  );
  const button = screen.getByRole('button', { name: 'Save' });

  expect(button).toHaveAttribute('aria-disabled', 'true');
  expect(button).not.toHaveAttribute('disabled');
  button.focus();
  expect(button).toHaveFocus();

  fireEvent.click(button);
  expect(onClick).not.toHaveBeenCalled();
  expect(onSubmit).not.toHaveBeenCalled();
});

test('a disabled button does not reach a clickable parent', () => {
  const onParentClick = vi.fn();
  render(
    <div onClick={onParentClick}>
      <Button disabled>Remove</Button>
    </div>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
  expect(onParentClick).not.toHaveBeenCalled();
});

test('a disabled link button loses its destination', () => {
  const onClick = vi.fn();
  render(
    <Button asChild disabled>
      <a href="#/projects" onClick={onClick}>
        Projects
      </a>
    </Button>,
  );
  const link = screen.getByText('Projects');

  expect(link).not.toHaveAttribute('href');
  expect(link).toHaveAttribute('aria-disabled', 'true');
  expect(link).toHaveAttribute('tabindex', '0');
  fireEvent.click(link);
  expect(onClick).not.toHaveBeenCalled();
});

test('loading keeps the accessible name, marks busy and blocks the click', () => {
  const onClick = vi.fn();
  render(
    <Button loading onClick={onClick}>
      Upload document
    </Button>,
  );
  const button = screen.getByRole('button', { name: 'Upload document' });

  expect(button).toHaveAttribute('aria-busy', 'true');
  expect(button).not.toHaveAttribute('aria-disabled');
  fireEvent.click(button);
  expect(onClick).not.toHaveBeenCalled();
});

test('primary and destructive presses vibrate once on touch screens', () => {
  const vibrate = stubTouch(true);
  render(
    <>
      <Button>Run</Button>
      <Button variant="destructive">Delete</Button>
      <Button variant="outline">Cancel</Button>
      <Button variant="ghost">More</Button>
      <Button disabled>Blocked</Button>
    </>,
  );

  fireEvent.pointerDown(screen.getByRole('button', { name: 'Run' }));
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Delete' }));
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Cancel' }));
  fireEvent.pointerDown(screen.getByRole('button', { name: 'More' }));
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Blocked' }));

  expect(vibrate).toHaveBeenCalledTimes(2);
  expect(vibrate).toHaveBeenCalledWith(10);
});

test('no vibration with a fine pointer', () => {
  const vibrate = stubTouch(false);
  render(<Button>Run</Button>);
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Run' }));
  expect(vibrate).not.toHaveBeenCalled();
});
