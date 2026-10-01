// Whether the API server is reachable (spec 0002, AC-7). Fed only by src/lib/api.ts; the
// shell reads it to show the disconnected banner and poll readiness.

export type ConnectionStatus = 'ok' | 'checking' | 'unreachable';

export type ConnectionState = {
  status: ConnectionStatus;
  /** Time of the last 2xx response, or null before the first one. */
  lastOkAt: number | null;
  /** A safe message for the banner, never a response body or connection detail. */
  message: string;
};

let state: ConnectionState = { status: 'ok', lastOkAt: null, message: '' };
const listeners = new Set<() => void>();

function set(next: ConnectionState) {
  state = next;
  for (const listener of listeners) {
    listener();
  }
}

export function subscribeConnection(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getConnection(): ConnectionState {
  return state;
}

export function markReachable() {
  set({ status: 'ok', lastOkAt: Date.now(), message: '' });
}

export function markUnreachable(message: string) {
  set({ ...state, status: 'unreachable', message });
}

export function markChecking() {
  set({ ...state, status: 'checking' });
}

/** Test helper: forget every response seen so far. */
export function resetConnection() {
  set({ status: 'ok', lastOkAt: null, message: '' });
}
