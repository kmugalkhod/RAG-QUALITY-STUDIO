import { useEffect, useState } from 'react';
import { useClerk } from '@clerk/react';
import { InlineError, LIST, LIST_ROW, Notice } from '../../../components/parts';
import { Button } from '../../../components/ui/button';
import { Label } from '../../../components/ui/label';
import { NativeSelect, NativeSelectOption } from '../../../components/ui/native-select';
import { postJson, request } from '../../../lib/api';
import { cn } from '../../../lib/utils';
import { SETTINGS_INTRO, SETTINGS_SECTION } from './settingsLayout';

type OrganizationMember = { user_id: string; identifier: string; organization_role: string };
type ProjectMember = { user_id: string; role: string };
type ProjectAccess = { role: string };

export function ProjectMembers({ projectId }: { projectId: string }) {
  const clerk = useClerk();
  const [directory, setDirectory] = useState<OrganizationMember[]>([]);
  const [grants, setGrants] = useState<ProjectMember[]>([]);
  const [access, setAccess] = useState<ProjectAccess | null>(null);
  const [userId, setUserId] = useState('');
  const [role, setRole] = useState('viewer');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([
      request<{ items: OrganizationMember[] }>('/organizations/current/members'),
      request<{ items: ProjectMember[] }>(`/projects/${projectId}/memberships`),
      request<ProjectAccess>(`/projects/${projectId}/access`),
    ])
      .then(([organization, project, rights]) => {
        if (active) {
          setDirectory(organization.items);
          setGrants(project.items);
          setAccess(rights);
        }
      })
      .catch((cause) => {
        if (active) {
          setError((cause as Error).message);
        }
      });
    return () => {
      active = false;
    };
  }, [projectId]);

  const canGrant = access?.role === 'owner' || access?.role === 'admin';
  const availableRoles =
    access?.role === 'owner' ? ['owner', 'admin', 'editor', 'viewer'] : ['editor', 'viewer'];
  return (
    <section className={SETTINGS_SECTION} aria-labelledby="project-members-heading">
      <div className={SETTINGS_INTRO}>
        <h2 id="project-members-heading" className="text-base font-semibold text-foreground">
          Project access
        </h2>
        <p className="text-sm text-foreground-muted">
          Organization membership and a project role are both required. Invitations are managed in
          Clerk.
        </p>
      </div>
      <div className="flex min-w-0 flex-col gap-4 desktop:col-span-2">
        {error && <InlineError>{error}</InlineError>}
        {grants.length > 0 && (
          <ul className={LIST} aria-label="Project members">
            {grants.map((grant) => {
              const member = directory.find((entry) => entry.user_id === grant.user_id);
              return (
                <li
                  key={grant.user_id}
                  className={cn(
                    LIST_ROW,
                    'flex min-h-row items-center justify-between gap-4 px-4 py-2 text-sm',
                  )}
                >
                  <span className="min-w-0 text-foreground wrap-anywhere">
                    {member?.identifier || grant.user_id}
                  </span>
                  <span className="text-xs text-foreground-muted capitalize">{grant.role}</span>
                </li>
              );
            })}
          </ul>
        )}
        {canGrant && (
          <form
            className="flex flex-col gap-4 md:flex-row md:items-end"
            onSubmit={async (event) => {
              event.preventDefault();
              setBusy(true);
              setError('');
              setNotice('');
              try {
                await postJson(`/projects/${projectId}/memberships`, { user_id: userId, role });
                const project = await request<{ items: ProjectMember[] }>(
                  `/projects/${projectId}/memberships`,
                );
                setGrants(project.items);
                setNotice('Project role saved.');
              } catch (cause) {
                setError((cause as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Label className="mb-0 min-w-0 md:flex-1">
              Organization member
              <NativeSelect
                className="mt-2"
                required
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
              >
                <NativeSelectOption value="">Select a member</NativeSelectOption>
                {directory.map((member) => (
                  <NativeSelectOption key={member.user_id} value={member.user_id}>
                    {member.identifier}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Label>
            <Label className="mb-0 md:w-sidebar">
              Project role
              <NativeSelect
                className="mt-2"
                value={role}
                onChange={(event) => setRole(event.target.value)}
              >
                {availableRoles.map((value) => (
                  <NativeSelectOption key={value} value={value}>
                    {value}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Label>
            <Button
              type="submit"
              loading={busy}
              disabled={busy || !userId || !availableRoles.includes(role)}
            >
              Save role
            </Button>
          </form>
        )}
        <Notice>{notice}</Notice>
        <Button
          variant="outline"
          className="self-start"
          onClick={() => clerk.openOrganizationProfile()}
        >
          Invite organization member
        </Button>
      </div>
    </section>
  );
}
