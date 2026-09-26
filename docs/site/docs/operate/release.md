---
verified_against: "481b4eca90c5 + docs phase 4 working tree (2026-09-26)"
title: Review a documentation release
slug: /operate/release/
---

Prepare a reviewable documentation revision tied to the current application tree without publishing it. You need repository access, the locked frontend/backend dependencies, an isolated PostgreSQL/pgvector test stack and a reviewer who can compare the guides with current UI/API behavior. This checklist is for local review; publication and external acceptance require separate authorization.

| Change owner | Required review when behavior changes |
| --- | --- |
| Feature owner | Update exact UI labels, outcome, failure/retry and capability boundary in the task guide; recapture any affected synthetic screenshot. |
| API owner | Run the canonical OpenAPI generator in check mode, inspect generated route/schema diffs and update authored auth/error/cost/workflow explanation. |
| Operator owner | Review deployment, key/retention, backup/restore, migrations, health, monitoring and shared-access gates. |
| Release reviewer | Run T1–T5 against the isolated stack, inspect desktop/720px/390px and keyboard flows, and record verified commit, config and known live gates. |

Run from the repository root. `npm ci` uses the locked site package; generated contracts require the locked backend Python environment. These read/build checks make no paid provider call:

```sh
backend/.venv/bin/python docs/site/scripts/generate_api_reference.py --check
cd docs/site
npm ci
npm run check
cd ../../frontend
npm run typecheck && npm run lint && npm run test -- --run && npm run build
```

Expected result: canonical OpenAPI and generated operation pages match, the Docusaurus build resolves every public route/link/asset, local search finds the task pages and no internal plans/QA files or test-only API routes enter the public build. Run backend API/security tests and browser tutorials on isolated PostgreSQL/pgvector before assigning a release identifier. A failure is a release blocker; fix source or docs and rerun the relevant check rather than suppressing validation.

Screenshots must come from a fictional isolated project and carry date, base app commit, viewport and scenario in `docs/site/screenshot-manifest.json`. Review full-size images for credentials, IDs and real source content; preserve readable alt text and a text alternative for diagrams. Re-capture when controls, copy or layout change. The current site has no previously published docs URL to migrate, so no historical redirect is active. If a published slug later changes, keep the old path as a real redirect to the new finished page and add a route check before release; do not leave a blank page or broken link.

To review the site locally, run `cd docs/site && npm run serve` and open [the local docs preview](http://127.0.0.1:3000). Compare it with the canonical [Vite application](http://127.0.0.1:5273). Search for every tutorial and API group, test keyboard search/sidebar, 1440px desktop, 720px equivalent and 390px mobile; verify code blocks and tables do not hide controls. Preserve test volumes and developer data. No hosting target, public domain, live model, external connector, OIDC issuer or KMS/Vault account has been approved or verified for this documentation release. See [deployment](./deploy.md), [security](./security.md), [backup and restore](./backup-restore.md), [troubleshooting](./troubleshooting.md), and [limits](../reference/limits-faq.md).
