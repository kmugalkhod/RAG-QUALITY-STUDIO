import { useEffect, useState } from 'react';
import { useClerk } from '@clerk/react';
import { Button } from '../../../components/ui/button';
import { postJson, request } from '../../../lib/api';

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
    <section className="project-members py-7" aria-labelledby="project-members-heading">
      <h2 id="project-members-heading">Project access</h2>
      <p>
        Organization membership and a project role are both required. Invitations are managed in
        Clerk.
      </p>
      <Button variant="outline" onClick={() => clerk.openOrganizationProfile()}>
        Invite organization member
      </Button>
      {error && <p role="alert">{error}</p>}
      <ul>
        {grants.map((grant) => {
          const member = directory.find((entry) => entry.user_id === grant.user_id);
          return (
            <li key={grant.user_id}>
              {member?.identifier || grant.user_id} · {grant.role}
            </li>
          );
        })}
      </ul>
      {canGrant && (
        <form
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
          <label htmlFor="grant-user">Organization member</label>
          <select
            id="grant-user"
            required
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
          >
            <option value="">Select a member</option>
            {directory.map((member) => (
              <option key={member.user_id} value={member.user_id}>
                {member.identifier}
              </option>
            ))}
          </select>
          <label htmlFor="grant-role">Project role</label>
          <select id="grant-role" value={role} onChange={(event) => setRole(event.target.value)}>
            {availableRoles.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <Button type="submit" disabled={busy || !userId || !availableRoles.includes(role)}>
            Save role
          </Button>
        </form>
      )}
      {notice && <p role="status">{notice}</p>}
    </section>
  );
}
