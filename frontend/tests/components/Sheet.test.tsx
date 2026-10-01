import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from '../../src/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '../../src/components/ui/sheet';

// covers: AC-3 (Sheet primitive) and AC-5 (the More sheet relies on it)

function renderSheet(showCloseButton?: boolean) {
  return render(
    <Sheet>
      <SheetTrigger asChild>
        <Button>More</Button>
      </SheetTrigger>
      <SheetContent side="bottom" showCloseButton={showCloseButton}>
        <SheetHeader>
          <SheetTitle>More pages</SheetTitle>
          <SheetDescription>Everything not in the tab bar.</SheetDescription>
        </SheetHeader>
        <a href="#/settings">Settings</a>
      </SheetContent>
    </Sheet>,
  );
}

test('opening the sheet shows a dialog named by its title and described', async () => {
  const user = userEvent.setup();
  renderSheet();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'More' }));
  const dialog = await screen.findByRole('dialog', { name: 'More pages' });
  expect(dialog).toHaveAccessibleDescription('Everything not in the tab bar.');
});

test('the close button has an accessible name and returns focus to the trigger', async () => {
  const user = userEvent.setup();
  renderSheet();
  const trigger = screen.getByRole('button', { name: 'More' });
  await user.click(trigger);
  await user.click(await screen.findByRole('button', { name: 'Close' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

test('Escape closes the sheet and returns focus to the trigger', async () => {
  const user = userEvent.setup();
  renderSheet();
  const trigger = screen.getByRole('button', { name: 'More' });
  await user.click(trigger);
  await screen.findByRole('dialog');
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

test('focus stays inside the open sheet', async () => {
  const user = userEvent.setup();
  renderSheet();
  await user.click(screen.getByRole('button', { name: 'More' }));
  const dialog = await screen.findByRole('dialog');
  for (let i = 0; i < 4; i += 1) {
    await user.tab();
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  }
});

test('the close button can be left out', async () => {
  const user = userEvent.setup();
  renderSheet(false);
  await user.click(screen.getByRole('button', { name: 'More' }));
  await screen.findByRole('dialog');
  expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument();
});
