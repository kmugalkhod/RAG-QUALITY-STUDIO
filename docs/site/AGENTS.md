# Documentation site

## Overview

This area is a separate Docusaurus app that publishes reviewed local documentation for RAG Quality Studio. Authored pages live in `docs/`, and `static/` holds approved public fixtures, diagrams, screenshots and the checked OpenAPI schema. Parent repository plans and QA records are not site input; read `README.md` here and `../../AGENTS.md` before changing pages, scripts or fixtures.

## Key files

| File | Owns |
|---|---|
| `docusaurus.config.ts` | Site config; broken links and broken markdown links throw, and `DOCS_SITE_URL` overrides the local `http://127.0.0.1:3000` origin |
| `sidebars.ts` | Section order for `docs/answers`, `api`, `concepts`, `experiments`, `ingestion`, `knowledge-base`, `operate`, `reference` and `start` |
| `route-contract.json` | Frozen list of reviewed local slugs; a published route change needs a real tested redirect before the contract changes |
| `screenshot-manifest.json` | Origin, viewport and review notes for every screenshot under `static/img/screenshots/` |
| `scripts/check-public.mjs` | The `check:public` gate: links, routes, public assets, Help targets, search, diagram descriptions, screenshot metadata, secret patterns and snippet syntax |
| `scripts/generate_api_reference.py` | Renders `docs/api/reference/` from the backend `app.openapi()`; `--check` diffs instead of writing |
| `scripts/verify_api_recipes.py` | Runs the API read examples and the synthetic upload and query recipe against the isolated `rag-docs-e2e` stack only |
| `scripts/rehearse_restore.py` | Seeds or verifies an isolated encrypted artifact restore against the provider fixture API only |
| `static/examples/` | Reviewed fictional sample files with SHA-256 hashes recorded in its `README.md` |
| `static/openapi.json` | Checked copy of the backend schema that the generated reference is compared against |

## Commands

From `docs/site/`, you can run `npm ci`, `npm run start`, `npm run build`, `npm run serve`, `npm run typecheck`, `npm run check:public` and `npm run check` (typecheck, build and public check together). Local preview and browser checks use `http://127.0.0.1:3000`.

From the repository root, with locked backend dependencies installed, `backend/.venv/bin/python docs/site/scripts/generate_api_reference.py` regenerates the endpoint reference and `--check` verifies it. `verify_api_recipes.py` and `rehearse_restore.py` refuse an ordinary backend and need the isolated stack on port 8002.

## Conventions

- Verify current UI labels and API behavior before changing a page or screenshot, and record `verified_against`, outcome, prerequisites, tested steps, expected and failure states, related links and live capability boundaries on the page.
- Keep screenshot captures synthetic. Record each capture in `screenshot-manifest.json` and add the hash of any new example file to `static/examples/README.md`.
- Review generated API reference diffs together with the authored API overview page; the generator excludes the three test only fixture endpoints.
- Do not add a route to `route-contract.json` for a published slug change until a real redirect is implemented and tested. The site is unpublished, so it has no historical redirects yet.
- Deterministic test transport means no paid or live external check is implied by the docs journeys. Publishing is a separate decision from local review.

## Gotchas

- `build/` and `node_modules/` are ignored; `npm run check` builds into `build/` and reads it, so run it after content changes rather than trusting an old build.
- `rehearse_restore.py` creates no Docker resources. Use distinct Compose projects, an external mode 0600 key file, and keep the seed record and archives outside the repository. Never remove developer volumes.
- Playwright tutorial and docs site journeys run on the isolated PostgreSQL and pgvector stack, then need a visual review of desktop and mobile output.

## Related documents

See `README.md` in this folder, `../documentation-plan.md`, `../development.md` and `../deployment.md`.

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
