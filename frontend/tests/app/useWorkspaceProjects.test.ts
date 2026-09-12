import { act, renderHook, waitFor } from '@testing-library/react';
import { useWorkspaceProjects } from '../../src/app/useWorkspaceProjects';
import { getProject, listProjects, type Project } from '../../src/features/projects/api';

vi.mock('../../src/features/projects/api', () => ({ getProject: vi.fn(), listProjects: vi.fn() }));
const first: Project = { id: 'first', name: 'First', description: '', created_at: '2026-09-12' };
const second: Project = { ...first, id: 'second', name: 'Second' };

beforeEach(() => {
  vi.mocked(listProjects)
    .mockReset()
    .mockResolvedValue({ items: [first, second], limit: 20, offset: 0, total: 2 });
  vi.mocked(getProject)
    .mockReset()
    .mockImplementation(async (id) => (id === 'first' ? first : second));
});

test('loads the project list once across project switches and refreshes after creation', async () => {
  const { result, rerender } = renderHook(({ id }) => useWorkspaceProjects(id), {
    initialProps: { id: 'first' },
  });
  await waitFor(() => expect(result.current.current?.id).toBe('first'));
  rerender({ id: 'second' });
  await waitFor(() => expect(result.current.current?.id).toBe('second'));
  expect(listProjects).toHaveBeenCalledTimes(1);
  act(() => result.current.refresh());
  await waitFor(() => expect(listProjects).toHaveBeenCalledTimes(2));
});

test('ignores a late project response after switching projects', async () => {
  let finish!: (project: Project) => void;
  vi.mocked(getProject).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const { result, rerender } = renderHook(({ id }) => useWorkspaceProjects(id), {
    initialProps: { id: 'first' },
  });
  rerender({ id: 'second' });
  await waitFor(() => expect(result.current.current?.id).toBe('second'));
  await act(async () => finish(first));
  expect(result.current.current?.id).toBe('second');
});
