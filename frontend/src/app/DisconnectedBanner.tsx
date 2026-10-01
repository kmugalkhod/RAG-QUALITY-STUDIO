import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { WifiOff } from 'lucide-react';
import { Button } from '../components/ui/button';
import { request } from '../lib/api';
import {
  getConnection,
  markChecking,
  markUnreachable,
  subscribeConnection,
} from '../lib/connection';

const POLL_DELAY_MS = 5000;

function useDocumentVisible() {
  const [visible, setVisible] = useState(() => !document.hidden);
  useEffect(() => {
    const update = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);
  return visible;
}

// Ask the readiness endpoint once. api.ts records the result in the connection store; any
// other failure (for example a 500) still counts as not reachable.
async function checkReadiness() {
  markChecking();
  try {
    await request('/ready');
  } catch (error) {
    if (getConnection().status === 'checking') {
      markUnreachable(error instanceof Error ? error.message : 'The server is not ready yet.');
    }
  }
}

function lastContact(lastOkAt: number | null) {
  if (lastOkAt === null) {
    return 'No successful response yet';
  }
  const time = new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(lastOkAt);
  return `Last successful response at ${time}`;
}

// Spec 0002, AC-7. Sits under the header and pushes the page down while the server cannot
// be reached, polling readiness 5 seconds after each response while the tab is visible.
export function DisconnectedBanner() {
  const connection = useSyncExternalStore(subscribeConnection, getConnection);
  const visible = useDocumentVisible();
  const { status, lastOkAt, message } = connection;

  useEffect(() => {
    if (status !== 'unreachable' || !visible) {
      return;
    }
    const timer = window.setTimeout(() => void checkReadiness(), POLL_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [status, visible, connection]);

  const retry = useCallback(() => void checkReadiness(), []);
  const checking = status === 'checking';

  return (
    <div role="status" aria-live="polite">
      {status === 'ok' ? null : (
        <div className="flex flex-col gap-3 border-b border-border bg-surface px-4 py-3 md:flex-row md:items-center md:px-6">
          <WifiOff aria-hidden="true" className="hidden size-4 shrink-0 text-danger md:block" />
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <p className="text-sm font-medium text-foreground">
              {checking ? 'Checking…' : 'Cannot reach the server'}
            </p>
            <p className="text-xs text-foreground-muted">
              {message ? `${message} · ` : ''}
              {lastContact(lastOkAt)}
            </p>
          </div>
          <Button variant="outline" size="sm" loading={checking} onClick={retry}>
            Retry
          </Button>
        </div>
      )}
    </div>
  );
}
