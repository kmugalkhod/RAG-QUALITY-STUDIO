import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { AnswerPolicyField } from '../../../src/features/pipelines/components/AnswerPolicyField';

test('shows strict for versions saved without a policy and changes by keyboard-accessible select', async () => {
  const onChange = vi.fn();
  render(<AnswerPolicyField value={undefined} onChange={onChange} />);
  const select = screen.getByRole('combobox', { name: 'Answer style' });
  expect(select).toHaveValue('strict-v1');
  expect(screen.getByText(/Earlier saved versions use this style/)).toBeInTheDocument();
  await userEvent.selectOptions(select, 'complete-v2');
  expect(onChange).toHaveBeenCalledWith('complete-v2');
});

test('explains the complete answer style', () => {
  render(<AnswerPolicyField value="complete-v2" onChange={() => {}} />);
  expect(screen.getByText(/names what the sources do not cover/)).toBeInTheDocument();
});
