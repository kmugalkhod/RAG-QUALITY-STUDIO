import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AnswerText } from '../../src/components/AnswerText';

test('formats paragraphs, emphasis, lists and code while retaining citation controls', async () => {
  const select = vi.fn();
  const { container } = render(
    <AnswerText
      text={
        '**30 days** [S1]\n\n- Receipt required\n- *Unused* sensor\n\n1. Contact support\n\n```\n<script>unsafe()</script>\n```'
      }
      citations={['S1']}
      onCitation={select}
    />,
  );
  expect(container.querySelector('strong')).toHaveTextContent('30 days');
  expect(container.querySelector('em')).toHaveTextContent('Unused');
  expect(screen.getAllByRole('list')).toHaveLength(2);
  expect(container.querySelector('pre code')).toHaveTextContent('<script>unsafe()</script>');
  await userEvent.click(screen.getByRole('button', { name: '[S1]' }));
  expect(select).toHaveBeenCalledWith('S1');
});
test('keeps HTML, links and invalid source labels inert', () => {
  const { container } = render(
    <AnswerText
      text={'<img src=x onerror=alert(1)> [S99] [click](javascript:alert(1)) `**literal**`'}
      citations={['S1']}
      onCitation={vi.fn()}
    />,
  );
  expect(container.querySelector('img,script,a')).toBeNull();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  expect(container.querySelector('code')).toHaveTextContent('**literal**');
  expect(container).toHaveTextContent('[S99]');
});
