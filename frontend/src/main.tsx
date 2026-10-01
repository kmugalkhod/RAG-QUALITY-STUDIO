import { StrictMode, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './app/App';
import { LoadingState } from './components/states/LoadingState';
import { Button } from './components/ui/button';
import {
  ArrowRight,
  ChartNoAxesCombined,
  Database,
  MessageSquareQuote,
  Workflow,
} from 'lucide-react';
import {
  ClerkProvider,
  OrganizationSwitcher,
  SignInButton,
  SignUpButton,
  TaskChooseOrganization,
  TaskResetPassword,
  TaskSetupMFA,
  UserButton,
  useAuth,
  useSession,
} from '@clerk/react';
import { shadcn } from '@clerk/ui/themes';
import { useLayoutEffect, useState } from 'react';
import { setTokenProvider } from './lib/api';
import { clerkElements, useClerkVariables } from './app/clerkAppearance';
import './app/styles.css';

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

function SignedOutScreen() {
  useEffect(() => {
    document.title = 'Sign in · RAG Quality Studio';
  }, []);

  return (
    <main className="grid min-h-dvh bg-background text-foreground md:grid-cols-2">
      <section
        className="flex min-w-0 flex-col gap-12 bg-surface p-6 md:p-12"
        aria-labelledby="auth-intro-title"
      >
        <div className="flex items-center gap-3 text-sm font-semibold">
          <span
            className="flex size-control-md items-center justify-center rounded-control bg-accent-fill text-accent-foreground"
            aria-hidden="true"
          >
            <Workflow className="size-(--icon-lg)" />
          </span>
          <span>RAG Quality Studio</span>
        </div>
        <div className="flex max-w-panel flex-col gap-4 md:my-auto">
          <h1 id="auth-intro-title" className="text-xl font-semibold text-balance">
            Make every answer traceable.
          </h1>
          <p className="text-base text-foreground-muted">
            Design retrieval pipelines, inspect the evidence behind answers, and compare experiments
            in one workspace.
          </p>
        </div>
        <ol
          className="hidden grid-cols-2 gap-4 border-t border-border pt-6 md:grid"
          aria-label="Studio workflow"
        >
          {(
            [
              [Database, 'Documents'],
              [Workflow, 'Pipelines'],
              [MessageSquareQuote, 'Answers'],
              [ChartNoAxesCombined, 'Evaluation'],
            ] as const
          ).map(([Icon, label]) => (
            <li key={label} className="flex items-center gap-2 text-sm text-foreground-muted">
              <Icon aria-hidden="true" className="size-4 shrink-0" />
              <span>{label}</span>
            </li>
          ))}
        </ol>
      </section>
      <section
        className="flex min-w-0 items-start justify-center border-t border-border p-6 md:items-center md:border-t-0 md:border-l md:p-12"
        aria-labelledby="auth-entry-title"
      >
        <div className="flex w-full max-w-panel flex-col gap-2">
          <h2 id="auth-entry-title" className="text-lg font-semibold">
            Welcome back
          </h2>
          <p className="text-sm text-foreground-muted">
            Sign in to continue to your organization’s workspace.
          </p>
          <div className="mt-6 flex flex-col gap-2">
            <SignInButton mode="modal">
              <Button size="lg" className="w-full justify-between">
                Sign in
                <ArrowRight aria-hidden="true" />
              </Button>
            </SignInButton>
            <SignUpButton mode="modal">
              <Button variant="outline" size="lg" className="w-full">
                Sign up
              </Button>
            </SignUpButton>
          </div>
          <p className="mt-6 border-t border-border pt-4 text-xs text-foreground-muted">
            Invited to an organization? Use the same email address.
          </p>
        </div>
      </section>
    </main>
  );
}

const AUTH_GATE =
  'flex min-h-dvh flex-col items-center justify-center gap-4 bg-background p-8 text-center text-foreground';

function ClerkWorkspace() {
  const { isLoaded, isSignedIn, orgId, getToken } = useAuth();
  const { isLoaded: sessionLoaded, session } = useSession();
  const [ready, setReady] = useState(false);
  useLayoutEffect(() => {
    setTokenProvider(isSignedIn ? () => getToken() : null);
    setReady(true);
    return () => setTokenProvider(null);
  }, [getToken, isSignedIn, orgId]);
  if (!isLoaded || !sessionLoaded || !ready) {
    return (
      <div className={AUTH_GATE}>
        <LoadingState label="Loading workspace…" rows={2} className="w-full max-w-panel" />
      </div>
    );
  }
  if (session?.status === 'pending') {
    return (
      <div className={AUTH_GATE}>
        {session.currentTask?.key === 'choose-organization' ? (
          <TaskChooseOrganization redirectUrlComplete="/" />
        ) : session.currentTask?.key === 'reset-password' ? (
          <TaskResetPassword redirectUrlComplete="/" />
        ) : session.currentTask?.key === 'setup-mfa' ? (
          <TaskSetupMFA redirectUrlComplete="/" />
        ) : (
          <p className="text-sm text-foreground-muted">
            Complete your Clerk account setup to continue.
          </p>
        )}
      </div>
    );
  }
  if (!isSignedIn) {
    return <SignedOutScreen />;
  }
  if (!orgId) {
    return (
      <div className={AUTH_GATE}>
        <h1 className="text-lg font-semibold">Select an organization</h1>
        <p className="text-sm text-foreground-muted">
          Create or select an organization to continue.
        </p>
        <OrganizationSwitcher hidePersonal />
        <UserButton />
      </div>
    );
  }
  return <App key={orgId} />;
}

function ThemedClerkProvider({ publishableKey }: { publishableKey: string }) {
  const variables = useClerkVariables();
  return (
    <ClerkProvider
      publishableKey={publishableKey}
      appearance={{ theme: shadcn, variables, elements: clerkElements }}
      localization={{
        signIn: {
          start: {
            title: 'Sign in to RAG Quality Studio',
            subtitle: 'Use your organization account to continue.',
          },
        },
        signUp: {
          start: {
            title: 'Join RAG Quality Studio',
            subtitle: 'Create an account to join or start an organization.',
          },
        },
      }}
      taskUrls={{ 'choose-organization': '/session-tasks/choose-organization' }}
    >
      <ClerkWorkspace />
    </ClerkProvider>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {publishableKey ? <ThemedClerkProvider publishableKey={publishableKey} /> : <App />}
  </StrictMode>,
);
