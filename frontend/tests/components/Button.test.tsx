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
