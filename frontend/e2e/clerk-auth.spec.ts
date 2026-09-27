import { randomBytes } from 'node:crypto';
import { createClerkClient } from '@clerk/backend';
import { clerk, clerkSetup, setupClerkTestingToken } from '@clerk/testing/playwright';
import { expect, test, type BrowserContext } from '@playwright/test';

test('development Clerk sign-up presents the required organization task', async ({ page }) => {
  test.setTimeout(60_000);
  test.skip(
    !process.env.CLERK_SECRET_KEY || !process.env.CLERK_PUBLISHABLE_KEY,
    'Requires opt-in Clerk development keys.',
  );
  const emailAddress = `rqs-signup+clerk_test_${Date.now()}@example.com`;
  const organizationName = `RQS Signup QA ${Date.now()}`;
  const password = `${randomBytes(24).toString('base64url')}Aa9!`;
  const backend = createClerkClient({ secretKey: process.env.CLERK_SECRET_KEY });
  try {
    await clerkSetup();
    await setupClerkTestingToken({ page });
    await page.goto('/');
    await page.getByRole('button', { name: 'Sign up' }).click();
    await expect(page.locator('input[name=emailAddress]')).toBeVisible();
    await page.locator('input[name=emailAddress]').fill(emailAddress);
    await page.locator('input[name=password]').fill(password);
    const verification = page.waitForResponse((response) =>
      response.url().includes('prepare_verification'),
    );
    await page.getByRole('button', { name: 'Continue', exact: true }).click();
    await verification;
    await page
      .getByRole('textbox', { name: 'Enter verification code' })
      .pressSequentially('424242');
    await expect(page.getByRole('heading', { name: 'Setup your organization' })).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole('textbox', { name: 'Name' }).fill(organizationName);
    await page.getByRole('button', { name: 'Continue', exact: true }).click();
    await expect(
      page
        .getByRole('heading', { name: 'Invite new members' })
        .or(page.getByRole('heading', { name: 'Projects', exact: true })),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Open organization switcher' })).toContainText(
      organizationName,
    );
    await expect(
      page.getByRole('heading', { name: 'Your first project starts here' }),
    ).toBeVisible();
  } finally {
    const organizations = await backend.organizations.getOrganizationList({ limit: 100 });
    for (const organization of organizations.data) {
      if (organization.name === organizationName) {
        await backend.organizations.deleteOrganization(organization.id);
      }
    }
    const users = await backend.users.getUserList({ emailAddress: [emailAddress] });
    for (const user of users.data) {
      await backend.users.deleteUser(user.id);
    }
  }
});

test('development Clerk organization and invitation flow', async ({ page, browser }) => {
  test.setTimeout(90_000);
  test.skip(
    !process.env.CLERK_SECRET_KEY || !process.env.CLERK_PUBLISHABLE_KEY,
    'Requires opt-in Clerk development keys.',
  );
  const stamp = Date.now();
  const primaryEmail = `rqs-primary+clerk_test_${stamp}@example.com`;
  const primaryOrganizationName = `RQS Auth QA Primary ${stamp}`;
  const organizationName = `RQS Auth QA Secondary ${stamp}`;
  const invitationEmail = `rqs-invite+clerk_test_${stamp}@example.com`;
  const backend = createClerkClient({ secretKey: process.env.CLERK_SECRET_KEY });
  let primaryUserId: string | undefined;
  let invitedUserId: string | undefined;
  let invitedContext: BrowserContext | undefined;
  try {
    const primaryUser = await backend.users.createUser({
      emailAddress: [primaryEmail],
      password: `${randomBytes(24).toString('base64url')}Aa9!`,
    });
    primaryUserId = primaryUser.id;
    await backend.organizations.createOrganization({
      name: primaryOrganizationName,
      createdBy: primaryUser.id,
    });
    const invitedUser = await backend.users.createUser({
      emailAddress: [invitationEmail],
      password: `${randomBytes(24).toString('base64url')}Aa9!`,
    });
    invitedUserId = invitedUser.id;
    await clerkSetup();
    await page.goto('/');
    await clerk.signIn({ page, emailAddress: primaryEmail });
    await expect(
      page
        .getByRole('heading', { name: 'Choose an organization' })
        .or(page.getByRole('heading', { name: 'Projects', exact: true })),
    ).toBeVisible();
    const orgChoice = page.getByRole('button', {
      name: new RegExp(`${primaryOrganizationName}'s logo`),
    });
    if (await orgChoice.isVisible()) {
      await orgChoice.click();
    }
    await expect(page.getByRole('heading', { name: 'Projects', exact: true })).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Your first project starts here' }),
    ).toBeVisible();
    await page.getByRole('button', { name: 'Open organization switcher' }).click();
    await page.getByRole('button', { name: 'Create organization' }).click();
    await page.getByPlaceholder('Organization name').fill(organizationName);
    await page.getByRole('button', { name: 'Create organization', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Open organization switcher' })).toContainText(
      organizationName,
    );
    await page.getByPlaceholder('example@email.com, example2@email.com').fill(invitationEmail);
    await page.getByRole('button', { name: 'Send invitations' }).click();
    await expect(page.getByText('Invitations successfully sent')).toBeVisible();
    const organizations = await backend.organizations.getOrganizationList({ limit: 100 });
    const created = organizations.data.find(
      (organization) => organization.name === organizationName,
    );
    expect(created).toBeDefined();
    const invitations = await backend.organizations.getOrganizationInvitationList({
      organizationId: created!.id,
    });
    expect(invitations.data.some((invitation) => invitation.emailAddress === invitationEmail)).toBe(
      true,
    );
    invitedContext = await browser.newContext();
    const invitedPage = await invitedContext.newPage();
    await invitedPage.goto('http://127.0.0.1:5273/');
    await clerk.signIn({ page: invitedPage, emailAddress: invitationEmail });
    await expect(
      invitedPage.getByRole('heading', { name: 'Choose an organization' }),
    ).toBeVisible();
    await invitedPage.getByRole('button', { name: 'Join', exact: true }).click();
    await invitedPage
      .getByRole('button', { name: new RegExp(`${organizationName}'s logo`) })
      .click();
    await expect(invitedPage.getByRole('heading', { name: 'Projects', exact: true })).toBeVisible();
    const accepted = await backend.organizations.getOrganizationInvitationList({
      organizationId: created!.id,
    });
    expect(
      accepted.data.find((invitation) => invitation.emailAddress === invitationEmail)?.status,
    ).toBe('accepted');
    const inviteeToken = await invitedPage.evaluate(async () => {
      const instance = (
        window as unknown as {
          Clerk?: { session?: { getToken: () => Promise<string | null> } };
        }
      ).Clerk;
      return instance?.session?.getToken();
    });
    expect(inviteeToken).toBeTruthy();
    const requestHeaders = { Authorization: `Bearer ${inviteeToken}` };
    const accessible = await fetch('http://127.0.0.1:8000/api/projects', {
      headers: requestHeaders,
    });
    expect(accessible.status).toBe(200);
    if (process.env.E2E_FOREIGN_PROJECT_ID) {
      const foreign = await fetch(
        `http://127.0.0.1:8000/api/projects/${process.env.E2E_FOREIGN_PROJECT_ID}`,
        { headers: requestHeaders },
      );
      expect(foreign.status).toBe(404);
    }
    await backend.organizations.deleteOrganizationMembership({
      organizationId: created!.id,
      userId: invitedUserId,
    });
    const removed = await fetch('http://127.0.0.1:8000/api/projects', {
      headers: requestHeaders,
    });
    expect(removed.status).toBe(403);
    await page.getByRole('button', { name: 'Finish' }).click();
    await page.getByRole('button', { name: 'Open organization switcher' }).click();
    await page
      .getByRole('button', { name: new RegExp(`${primaryOrganizationName}'s logo`) })
      .click();
    await expect(page.getByRole('button', { name: 'Open organization switcher' })).toContainText(
      primaryOrganizationName,
    );
    await page.getByRole('button', { name: 'Open organization switcher' }).click();
    await page.getByRole('button', { name: new RegExp(`${organizationName}'s logo`) }).click();
    await expect(page.getByRole('button', { name: 'Open organization switcher' })).toContainText(
      organizationName,
    );
    await page.getByRole('button', { name: 'Open user menu' }).click();
    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page.getByRole('heading', { name: 'RAG Quality Studio' })).toBeVisible();
  } finally {
    await invitedContext?.close();
    const organizations = await backend.organizations.getOrganizationList({ limit: 100 });
    for (const organization of organizations.data) {
      if (organization.name === organizationName || organization.name === primaryOrganizationName) {
        await backend.organizations.deleteOrganization(organization.id);
      }
    }
    if (invitedUserId) {
      await backend.users.deleteUser(invitedUserId);
    }
    if (primaryUserId) {
      await backend.users.deleteUser(primaryUserId);
    }
  }
});
