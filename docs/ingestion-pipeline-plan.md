# Ingestion pipeline implementation plan

Status: Phases 1–3 complete on 2026-09-12. Existing Files ingestion is released; Phase 4 is next.

This plan adds a second saved pipeline kind for acquiring and indexing knowledge. It preserves the existing answer pipeline and the current charcoal/lavender workspace. The first complete slice uses existing project documents, the second adds bounded public-website ingestion, and later slices add credentialed connectors through the same source-node contract.

## 1. Outcome

Users can open **Pipelines**, switch between **Answer pipelines** and **Ingestion pipelines**, build a supported ingestion graph, save an immutable version, preview the selected source, run it through workers, inspect every stage and publish a ready index version. An answer pipeline can select that exact index version without knowing whether its content came from files, a website or a future connector.

The supported graph is configuration, not executable user code:

```text
Existing files ─┐
Website ────────┼──> Extract ──> Clean ──> Chunk ──> Embed ──> Publish index
Future source ──┘
```

Version 1 supports one to ten source nodes feeding exactly one linear processing chain. No other branches, cycles, arbitrary scripts, SQL or user-defined node types are accepted.

## 2. Existing implementation to preserve

- Answer pipelines already persist append-only versions in `backend/app/models/pipeline.py` and validate an exact Question → Retriever → Prompt → LLM → Answer graph in `backend/app/schemas/pipeline.py`.
- PDF/TXT uploads, processing versions and chunks already exist in `backend/app/services/documents.py`, `backend/app/workers/processing.py` and `backend/app/pipelines/parsing.py`.
- Index versions and embeddings already exist in `backend/app/services/indexes.py` and `backend/app/workers/indexing.py`.
- PostgreSQL is the durable source of job state; the dispatcher sends IDs to Celery and workers fence duplicate or stale deliveries.
- The frontend already has a React Flow editor, immutable-version controls, an unsaved-change guard and a single application stylesheet.

Do not replace these paths with a second parser, embedding provider or vector store. Extract reusable domain operations where necessary and keep old API behavior compatible while the new path is introduced.

One existing behavior must change deliberately: index creation currently includes the latest successful processing run for every document in a project. Ingestion pipelines require explicit source membership so unrelated content cannot enter an index silently.

## 3. Domain language

Use these terms consistently in schemas, API copy and documentation:

| Term | Meaning |
| --- | --- |
| Pipeline kind | `answer` or `ingestion`; existing rows become `answer` during migration. |
| Source connector | Backend adapter that discovers and fetches one source type. |
| Source connection | Project-scoped reference to server-held connector credentials and non-secret connection metadata. |
| Source node | Versioned selection and fetch settings for a connector. It never contains a credential. |
| Source item | Stable external identity such as a URL, S3 object key, Notion page ID or existing document ID. |
| Source revision | Immutable fetched content and provenance for one source item at a point in time. |
| Knowledge set | Stable project-scoped destination whose immutable index versions are selectable by answer pipelines. |
| Ingestion run | Durable execution of one saved ingestion-pipeline version. |
| Run item | Per-source-item status, error, revision and counters within an ingestion run. |

## 4. Supported nodes and configuration

### Source nodes

All source nodes implement the same backend contract but have discriminated, source-specific configuration.

**Existing files**

- Select explicit project document IDs; never imply all current or future documents.
- Reuse the selected document's latest successful processing version only when its parser and chunk settings match the pipeline, otherwise create a new processing version.
- Reject missing, cross-project, failed or still-processing documents before accepting a run.

**Website**

- Mode: single URL, explicit URL list, crawl from a start URL or sitemap.
- Allowed origins and optional include/exclude path patterns.
- Maximum pages, crawl depth, response bytes and total bytes.
- Per-request timeout, overall deadline, concurrency and requests-per-second.
- Redirect limit, user agent and robots.txt behavior.
- HTML only in the first website release. Linked PDFs and JavaScript rendering are separate additions.

**Credentialed connectors added later**

- S3: connection, bucket, prefix and file-type allowlist.
- Notion: connection plus selected pages/databases.
- Confluence: connection plus selected spaces/pages.
- Each connector receives its own implementation and acceptance slice. A catalog entry must not appear in the production UI until discovery, fetch, incremental refresh and failure handling work end to end.

### Extract node

- Dispatch by fetched media type through an application-owned extractor registry.
- Return title, clean text, section/page structure and source metadata.
- Keep extraction deterministic and versioned.
- Reject unsupported or empty content explicitly.

### Clean node

Initial deterministic operations:

- Normalize line endings and bounded whitespace.
- Remove configured repeated website boilerplate after extraction.
- Enforce minimum/maximum text size.
- Exact-content deduplication by hash.
- Optional language allowlist only when detection has a tested confidence/unknown policy.

Do not add LLM rewriting, summarization or translation in the initial implementation. Those operations change source meaning, add cost and require their own provenance and evaluation design.

### Chunk node

- Start with the existing character-window algorithm and limits.
- Configure size and overlap with the existing bounds and state the unit as characters.
- Never cross source-item boundaries; preserve PDF page and website heading metadata where available.
- Store offsets, ordinal, section path and source-revision identity on every chunk.
- Heading-aware, paragraph, token and semantic chunkers are separate versioned strategies added only with comparison tests.

### Embed node

- Use the configured embedding adapter and dimensions already used by indexing.
- Snapshot provider, model, dimensions and adapter/config version.
- Reuse a cached vector only for identical text, project and complete embedding configuration.
- Report unknown embedding cost as unknown, never zero.

### Publish-index node

- Select or create a project-scoped knowledge set.
- Create a new immutable index version for every successful ingestion run.
- Persist exact source revisions and chunks as index members.
- Publish atomically only when all required items and embeddings succeed.
- Keep a previous ready version searchable until the new version is fully ready.

## 5. Connector contract

Create an application-owned interface under `backend/app/connectors/`; downstream processing must not import an S3, Notion, Confluence or crawler SDK directly.

The conceptual contract is:

```python
class SourceConnector(Protocol):
    kind: str
    config_version: str

    def validate(self, config, connection) -> None: ...
    def test_connection(self, connection) -> ConnectionCheck: ...
    def discover(self, config, cursor=None) -> DiscoveryPage: ...
    def fetch(self, item, prior_revision=None) -> FetchResult: ...
```

Canonical results must include:

- stable external ID and display name;
- canonical URL/path when applicable;
- media type;
- bounded content bytes or a generated stored-object reference;
- content hash;
- provider revision/etag/modified time when available;
- parent/referrer and source-specific non-secret metadata;
- an unchanged result when the provider proves the prior revision is current;
- a typed, sanitized and retry-classified error.

Connector discovery and fetch are separate so the UI can preview scope and workers can checkpoint large runs. Connector-specific pagination tokens stay server-side in run state and never become executable configuration.

## 6. Persistence and migration

Use the next Alembic revision after `0007`. The exact table split may be adjusted while implementing, but the persisted responsibilities and constraints below are required.

### Pipeline compatibility

- Add `pipelines.kind` with allowed values `answer` and `ingestion`.
- Backfill every existing pipeline as `answer`, then make the column non-null.
- Treat version execution JSON as a discriminated schema selected by the parent pipeline kind.
- Existing answer pipeline URLs, versions, query-run foreign keys and responses must continue working.
- Reject running an ingestion version through the answer-run endpoint and vice versa.

### New records

- `source_connections`: project, kind, name, non-secret settings, encrypted-secret reference/version, status and timestamps.
- `knowledge_sets`: project, name, created timestamp and optional current-ready-index pointer.
- `source_items`: project, connection/source identity, stable external ID, canonical location and timestamps.
- `source_revisions`: source item, content hash, provider revision metadata, stored artifact reference, media type, fetch time and immutable provenance JSON.
- `ingestion_runs`: project, pipeline version, knowledge set, status, current stage, progress/counters, execution token, attempts, error and timestamps.
- `ingestion_run_items`: run, source node, external item identity, per-stage status, source revision, retry classification and sanitized error.

Extend index membership so each index can prove the ingestion run, source revision and chunk that produced it. Do not infer historical membership from the latest current source state.

### Constraints and indexes

- Composite project ownership constraints on pipelines, connections, knowledge sets, runs and index versions.
- Unique stable source identity within a connection.
- Unique pipeline-version number per pipeline and index-version number per knowledge set.
- Partial uniqueness preventing concurrent active runs for the same knowledge set unless explicit parallel-version behavior is designed later.
- Check constraints for status, stage, counters, attempt limits and non-negative bounded sizes.
- Access indexes for project listings, queued dispatch, stale recovery and per-run item inspection.
- No destructive cascades from source deletion into published index or experiment evidence.

Credential storage is not improvised. Public website and existing-file sources require no connection secret. Before S3/Notion/Confluence ships, define an encryption key or external secret-store mechanism, rotation behavior and redaction tests. Until authentication/authorization exists, credentialed connections remain local-development only.

## 7. Typed execution schema and validation

Add a separate ingestion schema module instead of weakening the existing answer `Execution` union.

Required validation:

- schema version is explicit;
- one to ten recognized source nodes;
- exactly one Extract, Clean, Chunk, Embed and Publish node;
- every source connects to Extract, followed by the exact linear chain;
- all node IDs are unique and layout contains exactly those IDs;
- connector kind and configuration discriminator agree;
- selected documents/connections/knowledge set belong to the project;
- all numeric limits are bounded server-side;
- configured embedding model and dimensions are compatible;
- unknown fields, node types and connector kinds are rejected;
- URL patterns are data, never regular expressions without bounded safe parsing;
- graph display labels and coordinates never enter execution parameters.

Frontend validation improves feedback but is not authoritative. The backend validates on preview, save and run.

## 8. API surface

Keep routes thin and project-scoped. Reuse the existing pipeline collection where practical:

```text
GET  /api/projects/{project}/pipelines?kind=answer|ingestion
POST /api/projects/{project}/pipelines
POST /api/projects/{project}/pipelines/{pipeline}/versions
GET  /api/projects/{project}/pipelines/{pipeline}/versions

GET  /api/projects/{project}/connectors/catalog
POST /api/projects/{project}/source-connections
GET  /api/projects/{project}/source-connections
POST /api/projects/{project}/source-connections/{connection}/test

POST /api/projects/{project}/ingestion-previews
GET  /api/projects/{project}/ingestion-previews/{preview}

POST /api/projects/{project}/pipelines/{pipeline}/versions/{version}/ingestion-runs
GET  /api/projects/{project}/ingestion-runs
GET  /api/projects/{project}/ingestion-runs/{run}
GET  /api/projects/{project}/ingestion-runs/{run}/items
POST /api/projects/{project}/ingestion-runs/{run}/cancel

GET  /api/projects/{project}/knowledge-sets
GET  /api/projects/{project}/knowledge-sets/{set}/indexes
```

Preview returns a persisted, expiring job ID when discovery can take longer than a normal request. It reports discovered, included, excluded, unchanged and failed items without embedding or publishing.

Collection endpoints use bounded pagination. Run detail contains aggregate counters; potentially large per-item results use their own paginated endpoint.

## 9. Durable execution

Follow the current PostgreSQL queue-relay and fenced-worker conventions instead of constructing a large Celery chain.

Stages:

1. Validate the immutable version and destination.
2. Discover source items page by page.
3. Fetch new or changed items with connector limits.
4. Extract and clean bounded content.
5. Chunk and persist provenance.
6. Embed in bounded batches, reusing compatible cached vectors.
7. Build immutable index membership.
8. Atomically publish the index and mark the run succeeded.

Each delivery claims work with a row lock and execution token, performs at most one bounded unit, saves a checkpoint and returns. Duplicate delivery must be harmless. Define per-stage soft/hard timeouts and retry classification; do not stack connector SDK, application, Celery and dispatcher retries.

Cancellation stops scheduling new work, invalidates the execution token and prevents index publication. In-flight network calls may finish, but their result cannot publish after cancellation. Stale recovery either resumes a safe checkpoint or records a terminal failure when a request may have produced an ambiguous external effect.

Version 1 uses strict publication: any required source-item failure prevents a new index from becoming ready. A future “publish with warnings” policy requires explicit configuration, visible skipped counts and separate acceptance tests.

## 10. Website connector security

Website ingestion is a server-side URL fetcher and must be treated as an SSRF boundary.

- Accept only `http` and `https`; reject credentials in URLs.
- Normalize and validate the hostname before every request and redirect.
- Resolve and block loopback, private, link-local, multicast, reserved and cloud-metadata destinations for IPv4 and IPv6.
- Revalidate redirects and prevent HTTPS-to-unsafe-scheme transitions.
- Bound redirect count, DNS/connect/read timeouts, response size, total run bytes, page count, depth, concurrency and rate.
- Restrict crawling to configured allowed origins; path filters cannot widen origin scope.
- Honor robots.txt by default and identify the application user agent.
- Reject unsupported media types before parsing; do not execute page JavaScript.
- Never send configured headers or credentials across origins after a redirect.
- Avoid logging response bodies, URL credentials, tokens or document text.
- Test DNS rebinding/redirect cases with controlled resolver and HTTP transports.

External content remains untrusted after extraction. It is stored and embedded as data, not interpreted as application instructions.

## 11. Frontend experience

Preserve `DESIGN.md`, the current page shell, semantic tokens, shadcn components and `frontend/src/app/styles.css` ownership. This feature extends the existing operating interface; it is not another visual redesign.

### Pipeline list

- Add URL-addressable **Answer pipelines** and **Ingestion pipelines** tabs.
- Filter through the real `kind` API; do not fetch everything and guess from graph JSON.
- Show name, latest version, source summary, destination knowledge set and last-run status for ingestion rows.
- Use distinct actions: **New answer pipeline** and **New ingestion pipeline**.
- Preserve tab choice across refresh/history without leaking it between projects.

### Ingestion editor

- Create a feature-owned ingestion editor and model; share canvas primitives where useful but do not turn the answer editor into a condition-heavy mega-component.
- New templates use the established vertical node layout and existing selection/settings pattern.
- The palette groups source nodes separately from processing nodes.
- Node cards show the real configured selection summary, not decorative metrics.
- Every setting is editable through labeled keyboard-accessible forms; dragging is optional.
- Save creates an immutable version. Running requires a valid saved version; draft preview never mutates a saved version.
- Existing unsaved-change, discard, version selection, responsive stacking, fit-view and focus behavior continue to apply.

### Source configuration and preview

- Adding a source node opens its settings and focuses the first required field.
- Credentialed nodes select a named server-side connection and never render secrets.
- **Test connection** reports real success/failure separately from **Preview source**.
- Preview shows included/excluded items, canonical location, estimated size, change state and exclusion reason in a paginated inspector.
- Large selections use search/filter and explicit select-all semantics; do not render thousands of checkboxes at once.

### Run inspection

- Show queued/running/succeeded/failed/cancelled with explicit text and progress.
- Show the current stage and counts for discovered, fetched, unchanged, processed, failed, chunked, embedded and published items.
- Provide a paginated per-item inspector with source provenance and sanitized errors.
- Provide cancellation while actionable and explain the in-flight boundary.
- Link a successful run to the exact ready index and allow opening it in Knowledge Base.
- Loading, empty, validation, unavailable-provider, network-retry and stale-selection states are required, not polish work.

### Knowledge Base integration

- Group immutable index versions by knowledge set.
- Show which ingestion pipeline version and run produced an index.
- Preserve the current document upload/inspection path during migration.
- Answer-pipeline Retriever options show knowledge-set name, index version and ready state.
- Never silently move an answer pipeline to a newer index; choosing a new version creates an answer-pipeline draft change.

## 12. Code ownership boundaries

Use the established repository layout and keep modules cohesive. The expected ownership is:

| Area | Responsibility |
| --- | --- |
| `backend/app/schemas/ingestion.py` | Discriminated ingestion graph, connector configs, run requests and read contracts. |
| `backend/app/models/ingestion.py` | Connections, knowledge sets, source identities/revisions and ingestion job records. Split only if the model becomes genuinely difficult to navigate. |
| `backend/app/connectors/base.py` | Canonical connector protocol, result types and error classification. |
| `backend/app/connectors/existing_files.py` | Adapter over project-scoped documents and processing versions. |
| `backend/app/connectors/website.py` | Bounded discovery/fetch behavior using a separately testable safe HTTP client. |
| `backend/app/services/ingestion.py` | Save/run use cases, stage transitions, validation against persisted project resources and publication coordination. |
| `backend/app/services/connections.py` | Connection creation, redacted reads, testing and later rotation. Do not mix secret handling into pipeline services. |
| `backend/app/workers/ingestion.py` | Bounded, fenced stage execution. Shared embedding operations may be extracted from the current indexing worker instead of copied. |
| `backend/app/api/ingestion.py` | Thin preview, connection, run and knowledge-set routes. Existing generic pipeline routes may remain in `api/pipelines.py`. |
| `backend/tests/test_ingestion_*.py` | Schema/service/worker/connector integration tests using PostgreSQL and controlled connector transports. |
| `frontend/src/features/ingestion-pipelines/` | Ingestion API, model, editor/controller and feature-owned panels. Keep transport-free contracts in `model.ts`. |
| `frontend/src/features/pipelines/PipelinesPage.tsx` | Shared answer/ingestion list tabs and create/open routing only. |
| `frontend/src/features/pipelines/components/` | Existing answer-pipeline behavior; extract a shared visual primitive only after both editors prove the same responsibility. |
| `frontend/tests/features/ingestion-pipelines/` | Validation, payload, async-state and component behavior mirroring source ownership. |
| `frontend/e2e/` | Complete user journeys against isolated services and deterministic connectors. |

Do not create a generic repository layer, event bus, node framework or connector SDK wrapper unless the completed slices demonstrate repeated behavior that those abstractions simplify. Conversely, do not copy parsing, hashing, embedding, pagination, polling or status logic merely to avoid a focused shared extraction.

## 13. Implementation sequence

Each phase is a reviewable vertical slice. Execute them in order. At the end of a phase, update this table and `docs/implementation-plan.md` with what was actually verified. Do not begin the next phase until the current exit gate passes.

| Phase | Scope | Depends on | Status |
| --- | --- | --- | --- |
| 1 | Contracts, pipeline kinds and ingestion graph persistence | Existing application | Complete |
| 2 | Knowledge sets and explicit index membership | Phase 1 | Complete |
| 3 | Existing-files ingestion end to end | Phase 2 | Complete |
| 4 | Public website discovery and preview | Phase 3 | Not started |
| 5 | Website ingestion and incremental refresh | Phase 4 | Not started |
| 6 | Secure connection-management foundation | Phase 5 and a credential-storage decision | Not started |
| 7A | S3 connector | Phase 6 | Not started |
| 7B | Notion connector | Phase 7A | Not started |
| 7C | Confluence connector | Phase 7B | Not started |
| 8 | Scheduling and operations | At least one reliable incremental connector | Not started |
| 9 | Final cross-feature hardening | Released connector phases | Not started |

### Phase 1 — Contracts, pipeline kinds and graph persistence

- Add acceptance criteria to `docs/implementation-plan.md` before code.
- Record final table/API/worker decisions in `docs/architecture.md` as they are made.
- Define canonical connector result types and deterministic connector test fixtures.
- Identify compatibility tests for existing answer pipelines and project-wide document indexing.

- Add/backfill pipeline kind through Alembic.
- Add strict ingestion graph/config/layout schemas.
- Update pipeline listing, save and version services to dispatch validation by kind.
- Add project isolation and legacy-answer compatibility tests.
- Add frontend API/model types and the two pipeline tabs, but label ingestion creation unavailable until the end-to-end slice exists.

Exit gate: schema/API names and migration behavior are recorded; existing answer tests pass unchanged in behavior; invalid ingestion graphs cannot persist; the production UI contains no fake executable ingestion controls.

### Phase 2 — Knowledge sets and explicit membership

- Add stable knowledge sets and associate index versions with them.
- Migrate existing project indexes into a generated default knowledge set without changing IDs.
- Refactor index creation to accept explicit processing-run/chunk membership.
- Keep a compatibility action for the existing Knowledge Base indexing flow that explicitly snapshots selected/default documents.
- Update index listings and Retriever choices.

Exit gate: an index can prove every included processing run and no project-global implicit selection remains in the new service path.

### Phase 3 — Existing-files ingestion end to end

- Implement the existing-files connector using explicit document IDs.
- Add ingestion runs/items, dispatcher integration and stage workers.
- Reuse parsing, chunking and embedding operations.
- Build the ingestion editor, run action, polling, cancellation and result inspector.
- Publish a ready index and select it from an answer pipeline.

Exit gate: browser journey selects two uploaded documents, saves a pipeline, runs it, inspects chunks/provenance and asks a grounded question against its exact ready index.

### Phase 4 — Public website discovery and preview

- Implement the safe URL client and website connector discovery modes.
- Add robots, origin/path rules, canonicalization and hard crawl budgets.
- Add async preview and paginated preview inspector.
- Cover redirects, duplicates, blocked targets, malformed HTML, timeouts and cancellation.

Exit gate: previewing a controlled test site reports exactly why every discovered URL is included or excluded and performs no embedding.

### Phase 5 — Website ingestion and incremental refresh

- Fetch/store immutable source revisions and website provenance.
- Add deterministic main-content extraction and cleaning.
- Use content hash plus safe provider validators such as ETag/Last-Modified to mark unchanged items.
- Define removed-page behavior: retain historical revisions, exclude removals from the new index and report them.
- Publish a new immutable index while the prior ready version remains usable.

Exit gate: a second crawl embeds only changed/new content, reports unchanged/removed pages and preserves both historical index snapshots.

### Phase 6 — Connection management foundation

- Implement project-scoped named connections with encryption/secret-store support, redacted reads, test connection and rotation.
- Add authorization boundaries before enabling this outside localhost.
- Add audit-safe metadata without request bodies or credentials.

Exit gate: secret round-trip/redaction/rotation tests pass and browser storage/network responses contain no secret values.

### Phase 7A, 7B and 7C — Credentialed connectors, one at a time

Recommended order: S3, Notion, then Confluence. For each connector:

1. Inspect and pin the official SDK/API contract.
2. Implement connection validation, paginated discovery and bounded fetch.
3. Map provider identities/revisions to canonical source items.
4. Add source-node settings and real preview.
5. Add deterministic provider doubles and opt-in bounded live verification.
6. Complete refresh, deletion and permission-loss behavior before showing it as available.

Exit gate: the connector satisfies the same end-to-end acceptance criteria as Website; a catalog card alone is not delivery.

### Phase 8 — Scheduling and operations

- Add disabled-by-default manual schedules only after idempotent refresh is proven.
- Prevent overlapping runs for one destination.
- Expose next/last run, pause and manual-run behavior.
- Document rate limits, backups, storage growth, secret rotation and deletion.

Exit gate: schedules survive process restarts, do not overlap and cannot publish a partial index.

### Phase 9 — Final hardening

- Run clean migration and supported upgrade-path tests.
- Run backend lint/format/full PostgreSQL suite.
- Run frontend format/lint/typecheck/unit/build.
- Run isolated Playwright journeys for existing files and website, plus all answer-pipeline regressions.
- Inspect desktop and mobile states once, fix findings in one bounded pass and confirm once.
- Run opt-in live connector checks only with user-authorized sources and bounded cost/traffic.
- Update README, architecture, development, deployment and implementation status with only verified claims.

## 14. Copy-paste prompts for each phase

Use one prompt at a time. Each prompt stops at its exit gate so the next phase cannot be implemented accidentally.

### Phase 1 prompt

~~~text
Implement Phase 1 only from docs/ingestion-pipeline-plan.md: contracts, pipeline kinds and ingestion graph persistence.

Read and follow AGENTS.md, docs/frontend-standards.md, DESIGN.md and the complete ingestion plan before changing files. Inspect Git status and preserve unrelated work.

Add acceptance criteria first. Implement the pipeline-kind migration with every existing row backfilled as an answer pipeline, separate strict answer/ingestion execution validation, kind-filtered project APIs and URL-addressable Answer/Ingestion tabs. Define canonical connector result contracts and deterministic fixtures for later phases. Preserve every existing answer pipeline, version, query run, route and browser workflow. Do not implement knowledge sets, workers, website fetching or functional connector controls.

Run the Phase 1 backend, migration, frontend and regression checks. Update docs/architecture.md and docs/implementation-plan.md with only verified results. Report changes, checks, limitations and the Phase 2 handoff. Do not continue into Phase 2.
~~~

### Phase 2 prompt

~~~text
Implement Phase 2 only from docs/ingestion-pipeline-plan.md: knowledge sets and explicit index membership.

First verify Phase 1 is marked complete and its exit gate passed. Read all repository instructions, inspect Git status and preserve unrelated work.

Add project-scoped knowledge sets, migrate existing index versions into a compatible default knowledge set without changing IDs, make new index construction accept explicit processing-run/chunk membership, and update Knowledge Base and answer-pipeline Retriever selection to show the knowledge set and exact ready index version. Preserve historical queries and experiments. Do not implement ingestion-run workers or website fetching.

Run clean/upgrade migration tests, project-isolation and membership tests, frontend checks and affected browser regressions. Update architecture and implementation status with actual results. Report the Phase 3 handoff and stop.
~~~

### Phase 3 prompt

~~~text
Implement Phase 3 only from docs/ingestion-pipeline-plan.md: the Existing Files ingestion pipeline end to end.

First verify Phases 1 and 2 are complete. Read all repository instructions and the full ingestion plan. Preserve the current frontend design and existing document/index behavior.

Implement the Existing Files source adapter with explicit project document selection; persisted ingestion runs and run items; PostgreSQL-backed dispatch; bounded, fenced and cancellable stage workers; reuse of existing extraction, chunking and embedding operations; atomic index publication; and the real ingestion editor, versioning, run progress, item inspection and published-index link. Complete the browser journey through selecting that exact index in an answer pipeline. Do not add website or credentialed connectors.

Run the full Phase 3 database, worker, frontend and isolated browser checks. Update architecture and implementation status with verified evidence, report limitations and the Phase 4 handoff, then stop.
~~~

### Phase 4 prompt

~~~text
Implement Phase 4 only from docs/ingestion-pipeline-plan.md: bounded public-website discovery and preview.

First verify Phase 3 is complete. Read all repository instructions and the full ingestion plan. Consult primary documentation for every new HTTP/parser dependency and pin compatible versions.

Implement the safe HTTP client and Website discovery modes for a single URL, explicit URL list, same-origin crawl and sitemap. Enforce the plan's SSRF, DNS, redirect, robots, origin, path, page, depth, size, timeout, concurrency and rate limits. Add persisted asynchronous preview and a real paginated frontend inspector showing included, excluded, duplicate and failed URLs with reasons. Preview must not embed or publish. Do not implement full website ingestion or credentialed connectors.

Run controlled transport/resolver security tests, API/frontend tests and the isolated website-preview browser journey. Update documentation with verified results, report the Phase 5 handoff and stop.
~~~

### Phase 5 prompt

~~~text
Implement Phase 5 only from docs/ingestion-pipeline-plan.md: website ingestion and incremental refresh.

First verify Phase 4 is complete. Read all applicable instructions and preserve existing ready indexes during new runs.

Persist immutable website source identities and revisions, implement deterministic main-content extraction and cleaning, retain URL/heading/fetch provenance through chunks, use content hashes and safe validators for unchanged items, report changed/unchanged/removed pages, reuse compatible embeddings and publish a new index atomically. A failed or cancelled run must never replace the previous ready index. Do not implement secret-bearing connections or S3/Notion/Confluence.

Verify first crawl, incremental recrawl, removal, failure, cancellation, stale recovery, provenance, embedding reuse and end-to-end answer retrieval against controlled sites. Update architecture and implementation status, report the Phase 6 decision needed and stop.
~~~

### Phase 6 prompt

~~~text
Implement Phase 6 only from docs/ingestion-pipeline-plan.md: secure connection management.

Do not begin until Phases 1–5 are complete and the user has approved the credential encryption or external secret-store design. Read all applicable instructions and official primary documentation for the selected mechanism.

Implement project-scoped named source connections, encrypted or externally referenced secrets, redacted API reads, connection testing, rotation and safe audit metadata. The frontend must create, select and test connections without placing secrets in URLs, DOM after submission, logs, browser storage or pipeline versions. Add authorization boundaries before enabling credentialed connections beyond localhost. Do not implement S3, Notion or Confluence fetching.

Run secret round-trip, redaction, rotation, cross-project, error-sanitization and frontend leakage tests. Update documentation with the exact security boundary and verified results, report the Phase 7A handoff and stop.
~~~

### Phase 7A prompt — S3

~~~text
Implement Phase 7A only from docs/ingestion-pipeline-plan.md: the S3 source connector.

First verify Phase 6 is complete. Use official S3 SDK/API documentation and pin a compatible dependency. Implement connection validation, bucket/prefix selection, paginated bounded discovery, allowed file types, stable object identity/version mapping, fetch, preview, incremental refresh, deleted-object handling, permission-loss errors, source-node settings and provenance. Use deterministic provider doubles for default tests and an opt-in bounded live check only with a user-authorized bucket.

Meet the same end-to-end exit gate as Website, update documentation, report the Phase 7B handoff and stop. Do not implement Notion or Confluence.
~~~

### Phase 7B prompt — Notion

~~~text
Implement Phase 7B only from docs/ingestion-pipeline-plan.md: the Notion source connector.

First verify Phase 7A is complete. Use official Notion API documentation and a pinned compatible client. Implement connection validation, paginated page/database discovery, explicit selection, bounded fetch, stable page/revision mapping, deterministic text extraction, preview, incremental refresh, archive/removal and permission-loss behavior, source-node settings and complete provenance. Use deterministic doubles by default and an opt-in bounded live check only against a user-authorized workspace.

Meet the shared connector exit gate, update documentation, report the Phase 7C handoff and stop. Do not implement Confluence.
~~~

### Phase 7C prompt — Confluence

~~~text
Implement Phase 7C only from docs/ingestion-pipeline-plan.md: the Confluence source connector.

First verify Phase 7B is complete. Use official Confluence API documentation and a pinned compatible client. Implement connection validation, paginated space/page discovery, explicit filters, bounded fetch, stable content/version mapping, deterministic extraction, preview, incremental refresh, deletion and permission-loss behavior, source-node settings and complete provenance. Use deterministic doubles by default and an opt-in bounded live check only against a user-authorized site.

Meet the shared connector exit gate, update documentation, report the Phase 8 handoff and stop.
~~~

### Phase 8 prompt

~~~text
Implement Phase 8 only from docs/ingestion-pipeline-plan.md: scheduling and ingestion operations.

Begin only after manual incremental reruns are proven for at least one released connector. Add disabled-by-default persisted schedules, non-overlapping destination runs, next/last-run visibility, pause and manual-run behavior, durable restart recovery and operational documentation for rate limits, storage growth, backups, deletion and secret rotation. Preserve manual runs and never publish partial indexes.

Verify scheduling across process restarts, overlap prevention, cancellation and failure recovery. Update documentation, report the Phase 9 handoff and stop.
~~~

### Phase 9 prompt

~~~text
Complete Phase 9 from docs/ingestion-pipeline-plan.md: final cross-feature hardening for the ingestion sources actually released.

Read the full verification matrix and definition of done. Do not add new connectors or features. Run clean and upgrade-path migrations, full PostgreSQL/pgvector backend tests, Ruff, frontend format/lint/typecheck/unit/build, isolated Playwright ingestion journeys and existing answer/Playground/experiment regressions. Inspect desktop and mobile states in one bounded visual pass and correct verified regressions. Run live connector checks only when explicitly authorized and bounded.

Update README, architecture, development, deployment and implementation status with actual results, remaining limitations and operational procedures. Do not claim production readiness unless every release requirement has been verified.
~~~

## 15. Verification matrix

### Backend

- Pipeline-kind backfill and old answer-version readability.
- Cross-project connection, document, pipeline, run, source and knowledge-set rejection.
- Graph shape, extra fields, limits and incompatible embedding validation.
- Duplicate delivery, lost dispatch, stale worker, cancellation and retry exhaustion.
- Exact source revision/chunk/index provenance and immutable historical reads.
- Incremental unchanged/changed/removed source behavior.
- Atomic publication and continued availability of the previous ready index.
- SSRF cases, redirects, DNS results, origin constraints, response bombs and timeouts.
- Credential encryption/redaction/rotation before credentialed connectors.
- PostgreSQL/pgvector behavior; no SQLite substitution for persistence/vector tests.

### Frontend

- Tab routing and project-switch isolation.
- Create/save/reopen/duplicate ingestion versions and dirty-navigation protection.
- Source-node add/remove/configuration with keyboard operation.
- Server validation mapped to the responsible node/field.
- Preview loading/empty/success/partial-error/failure/cancel states.
- Run polling without overlap or stale-response replacement.
- Per-item pagination, provenance inspection and ready-index link.
- Mobile canvas/settings layout without horizontal page overflow.
- No secret value in DOM, storage, URL or request payload after connection creation.

### Browser journeys

1. Upload files → configure existing-files ingestion → preview → save → run → inspect → use exact index in an answer pipeline.
2. Crawl controlled website → inspect exclusions → run → modify fixture → rerun → verify changed/unchanged/removed counts and version history.
3. Cancel during fetch and embedding; verify no partial ready index.
4. Refresh/back/project-switch during dirty edit and active run; verify state and scope.
5. Existing answer, Playground and experiment journeys remain operational against historical indexes.

## 16. Definition of done

The feature is not complete when nodes merely render. It is complete for each released source when:

- its real connector discovers and fetches through the backend;
- configuration is strictly validated and immutably versioned;
- a durable, cancellable and recoverable run publishes an explicit ready index;
- source-to-chunk-to-index provenance is inspectable;
- unchanged content does not require duplicate embedding;
- errors and partial work cannot masquerade as success;
- the frontend provides accessible configuration, preview, progress and inspection using real APIs;
- project isolation, SSRF/credential boundaries and migrations are tested;
- existing answer pipelines and historical results remain valid;
- documentation describes actual verified behavior and remaining limitations.

## 17. Explicit non-goals for the first release

- Arbitrary DAG execution, code nodes or user-authored scripts.
- JavaScript/browser-rendered crawling.
- Authenticated website crawling.
- OCR, audio/video transcription or image understanding.
- LLM-based cleaning, summarization or metadata generation.
- Automatic schedules before incremental manual reruns are reliable.
- Silent best-effort publication with missing required sources.
- Automatic switching of saved answer pipelines to the latest index.
- Advertising S3, Notion or Confluence as functional before each real integration is complete.

## 18. Decisions to confirm at implementation boundaries

The plan does not require these decisions before Phase 1, but implementation must not guess them when the relevant phase begins:

- Whether existing indexes appear under an automatically named default knowledge set or require a one-time user-selected name.
- The credential encryption/secret-store mechanism before Phase 6.
- Which owned or explicitly authorized website is suitable for an opt-in live crawl.
- Whether a later release may publish with warnings and what failure threshold is acceptable.
- Connector priority after Website; the current recommendation is S3 → Notion → Confluence.
