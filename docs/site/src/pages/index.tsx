import React from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';

const paths = [
  {title: 'Start with one cited answer', to: '/docs/start/first-workflow', detail: 'Upload a synthetic file, publish a collection and inspect its evidence.'},
  {title: 'Build an ingestion pipeline', to: '/docs/ingestion/pipelines', detail: 'Preview Existing Files, save a version and publish an index.'},
  {title: 'Integrate through the API', to: '/docs/api/overview', detail: 'Understand local and OIDC modes, errors and versioned jobs.'},
  {title: 'Run locally', to: '/docs/start/install', detail: 'Start PostgreSQL, workers, FastAPI and the canonical Vite frontend.'},
];
export default function Home(): React.JSX.Element {
  return <Layout title="Documentation" description="Task guides for RAG Quality Studio">
    <main className="home">
      <p>DOCUMENTATION · CURRENT LOCAL APPLICATION</p>
      <h1>From source material to an answer you can inspect.</h1>
      <p className="home-lead">Follow a complete local workflow, then choose the saved versions and evidence you need. Model-backed steps require your own configured provider and may incur charges.</p>
      <div className="home-grid">{paths.map(path => <Link className="home-card" key={path.to} to={path.to}><strong>{path.title} →</strong><span>{path.detail}</span></Link>)}</div>
    </main>
  </Layout>;
}
