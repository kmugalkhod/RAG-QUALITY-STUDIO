import { StrictMode, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './app/App';
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
import './app/styles.css';

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

function SignedOutScreen() {
  useEffect(() => {
    document.title = 'Sign in · RAG Quality Studio';
  }, []);

  return (
    <main className="auth-landing">
      <section className="auth-intro" aria-labelledby="auth-intro-title">
        <div className="auth-brand">
          <span className="auth-brand-mark" aria-hidden="true">
            <Workflow />
          </span>
          <span>RAG Quality Studio</span>
        </div>
        <div className="auth-intro-copy">
          <h1 id="auth-intro-title">Make every answer traceable.</h1>
          <p>
            Design retrieval pipelines, inspect the evidence behind answers, and compare experiments
            in one workspace.
          </p>
        </div>
        <ol className="auth-workflow" aria-label="Studio workflow">
          <li>
            <Database aria-hidden="true" />
            <span>Documents</span>
          </li>
          <li>
            <Workflow aria-hidden="true" />
            <span>Pipelines</span>
          </li>
          <li>
            <MessageSquareQuote aria-hidden="true" />
            <span>Answers</span>
          </li>
          <li>
            <ChartNoAxesCombined aria-hidden="true" />
            <span>Evaluation</span>
          </li>
        </ol>
      </section>
      <section className="auth-entry" aria-labelledby="auth-entry-title">
        <div className="auth-entry-content">
          <h2 id="auth-entry-title">Welcome back</h2>
          <p>Sign in to continue to your organization’s workspace.</p>
          <div className="auth-entry-actions">
            <SignInButton mode="modal">
              <Button size="lg" className="auth-entry-primary">
                Sign in
                <ArrowRight aria-hidden="true" />
              </Button>
            </SignInButton>
            <SignUpButton mode="modal">
              <Button variant="outline" size="lg" className="auth-entry-secondary">
                Sign up
              </Button>
            </SignUpButton>
          </div>
          <p className="auth-entry-note">Invited to an organization? Use the same email address.</p>
        </div>
      </section>
    </main>
  );
}

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
    return <p role="status">Loading workspace…</p>;
  }
  if (session?.status === 'pending') {
    return (
      <div className="auth-gate">
        {session.currentTask?.key === 'choose-organization' ? (
          <TaskChooseOrganization redirectUrlComplete="/" />
        ) : session.currentTask?.key === 'reset-password' ? (
          <TaskResetPassword redirectUrlComplete="/" />
        ) : session.currentTask?.key === 'setup-mfa' ? (
          <TaskSetupMFA redirectUrlComplete="/" />
        ) : (
          <p>Complete your Clerk account setup to continue.</p>
        )}
      </div>
    );
  }
  if (!isSignedIn) {
    return <SignedOutScreen />;
  }
  if (!orgId) {
    return (
      <div className="auth-gate">
        <h1>Select an organization</h1>
        <p>Create or select an organization to continue.</p>
        <OrganizationSwitcher hidePersonal />
        <UserButton />
      </div>
    );
  }
  return <App key={orgId} />;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {publishableKey ? (
      <ClerkProvider
        publishableKey={publishableKey}
        appearance={{ theme: shadcn }}
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
    ) : (
      <App />
    )}
  </StrictMode>,
);
