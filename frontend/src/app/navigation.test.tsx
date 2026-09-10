import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { parseRoute, useRoute, useUnsavedChanges } from './navigation';
const id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
beforeEach(() => { window.history.replaceState(null, '', '/'); });
it('parses project, page, editor and saved version links', () => {
  expect(parseRoute(`#/projects/${id}/pipelines/new`)).toMatchObject({ projectId: id, page: 'pipelines', detail: 'new' });
  expect(parseRoute(`#/projects/${id}`)).toMatchObject({ page: 'knowledge-base' });
  expect(parseRoute(`#/projects/${id}/playground?pipeline=p&version=v`).query.get('version')).toBe('v');
  expect(parseRoute('#/missing').page).toBe('not-found');
});
function Guard() { const route = useRoute(); useUnsavedChanges(true); return <p>{route.page}</p>; }
it('keeps the current route when a dirty editor navigation is rejected', async () => {
  window.history.replaceState(null, '', `#/projects/${id}/pipelines/new`);
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  render(<Guard/>);
  act(() => { window.location.hash = `/projects/${id}/overview`; });
  await waitFor(() => expect(confirm).toHaveBeenCalledOnce());
  expect(window.location.hash).toContain('/pipelines/new');
  expect(screen.getByText('pipelines')).toBeInTheDocument();
  confirm.mockRestore();
});
