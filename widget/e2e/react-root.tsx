/* A local React shared-root-layout integration fixture. */
import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';

function SharedLayout() {
  const [route, setRoute] = useState(location.pathname);
  useEffect(() => {
    const script = document.createElement('script');
    script.async = true;
    script.src = 'http://127.0.0.1:5274/v1.0.0/loader.js';
    script.dataset.rqsDeploymentId = document.body.dataset.deploymentId || '';
    script.dataset.rqsTokenUrl = '/api/rag-widget/token';
    document.body.append(script);
    // A shared layout stays mounted as its child route changes.
  }, []);
  const go = (path: string) => { history.pushState({}, '', path); setRoute(path); };
  return <><header><h1>React customer layout</h1><nav><button onClick={() => go('/react')}>Overview</button><button onClick={() => go('/react/help')}>Help</button></nav><button onClick={async () => { await fetch('/login',{method:'POST'});location.reload(); }}>Sign in</button></header><main><h2>{route.endsWith('/help') ? 'Help route' : 'Overview route'}</h2><p>The assistant belongs to the shared root layout.</p></main></>;
}
createRoot(document.getElementById('app')!).render(<SharedLayout />);
