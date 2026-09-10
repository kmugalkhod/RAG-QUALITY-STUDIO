import { useEffect, useState } from 'react';

export function parseRoute(hash: string) {
  const [path, query = ''] = hash.replace(/^#/, '').split('?');
  const match = /^\/projects\/([a-f0-9-]{36})(?:\/(overview|knowledge-base|pipelines|playground|settings))?(?:\/([a-zA-Z0-9-]+))?$/.exec(path);
  return { projectId: match?.[1], page: match ? match[2] || 'knowledge-base' : path && path !== '/' ? 'not-found' : 'projects', detail: match?.[3], query: new URLSearchParams(query) };
}
let blocker: { href: string; allow: () => boolean } | undefined;

export function useRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const update = () => {
      if (blocker && window.location.href !== blocker.href && !blocker.allow()) window.history.replaceState(null, '', blocker.href);
      setHash(window.location.hash);
    };
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  return parseRoute(hash);
}
export function useUnsavedChanges(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    let approved = false;
    const guard = { href: window.location.href, allow: () => approved || window.confirm('Discard unsaved pipeline changes?') };
    blocker = guard;
    const before = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    const click = (event: MouseEvent) => {
      const link = (event.target as Element).closest('a');
      if (link && link.href !== window.location.href && link.getAttribute('href') !== '#main') {
        approved = window.confirm('Discard unsaved pipeline changes?');
        if (!approved) { event.preventDefault(); event.stopImmediatePropagation(); }
      }
    };
    window.addEventListener('beforeunload', before);
    document.addEventListener('click', click, true);
    return () => { if (blocker === guard) blocker = undefined; window.removeEventListener('beforeunload', before); document.removeEventListener('click', click, true); };
  }, [dirty]);
}
