# Documentation site authoring

This Docusaurus site is reviewed local documentation. `docs/` contains public authored and generated pages, and `static/` contains approved public fixtures, diagrams, screenshots and the checked OpenAPI schema. Parent repository plans and QA records are not site input. Local preview and browser checks use `http://127.0.0.1:3000`; publishing is a separate decision.

```sh
cd docs/site
npm ci
npm run check
npm run serve
```

From the repository root, after installing locked backend dependencies, regenerate or check endpoint contracts against canonical `app.openapi()`:

```sh
backend/.venv/bin/python docs/site/scripts/generate_api_reference.py
backend/.venv/bin/python docs/site/scripts/generate_api_reference.py --check
```

Review generated diffs and the authored [API reference overview](docs/api/reference.md) together. The generator validates schema references, classifies every path and excludes the three test-only fixture endpoints that the isolated browser stack adds at runtime. The separate `scripts/verify_api_recipes.py` refuses a non-fixture backend before creating its fictional project. Run it only with the isolated `rag-docs-e2e` stack on port 8002; it preserves the database and named volumes.

For any page or screenshot change, verify current UI labels/API behavior, add `verified_against`, outcome, prerequisites, tested steps, expected and failure states, related links and live capability boundaries. Keep screenshot captures synthetic, record their origin in `screenshot-manifest.json`, and add SHA-256 hashes to `static/examples/README.md`. `route-contract.json` freezes reviewed local slugs; this unpublished site has no historical redirects. If a published route later changes, implement and test a real redirect before adding it to the contract. `npm run check` validates built links/routes, public assets, app Help targets, local search, diagram descriptions, screenshot metadata, common secret patterns and shell/JSON/Python snippet syntax. Execute the relevant Playwright tutorial and docs-site journeys on the isolated PostgreSQL/pgvector stack, then visually review desktop and mobile output. No paid or live external check is implied by deterministic test transport.

The operator recovery rehearsal uses `scripts/rehearse_restore.py` only against the isolated provider-fixture API. It refuses an ordinary backend and creates no Docker resources itself. Use distinct Compose projects and an external mode-0600 test key file, keep the seed ID record outside the repository, take the PostgreSQL and document-volume archives with writers stopped, and verify the restored project/index/query plus a new processing run. The public [backup and restore guide](docs/operate/backup-restore.md) records the checked command order. Do not remove developer volumes or commit the key file, record or archives.
