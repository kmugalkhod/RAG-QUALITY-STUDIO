# Implementation plan

## Milestone 1 — Foundation

Acceptance criteria (recorded before implementation):

- React and strict TypeScript shell presents projects from the real API.
- Users create projects with validated names and optional descriptions; projects survive service restarts.
- FastAPI exposes paginated listing, creation, liveness and database readiness.
- PostgreSQL schema is managed by Alembic; Compose uses a named volume and localhost ports.
- UI handles loading, empty results, validation, request errors and submission progress accessibly.
- Backend and frontend tests cover completed behavior; production build passes.
- Run the application and verify creation in a browser where tooling permits.
- README documents setup, URLs, checks and limitations.

Status: complete for Milestone 1. Verified locally on 2026-09-09.

Implemented:

- React 19, strict TypeScript, Vite, Tailwind and shared shadcn-style Button.
- Responsive projects page with real creation/listing, pagination, loading, empty, validation, submitting, success, retry and error states.
- FastAPI project routes, Pydantic validation, request-scoped SQLAlchemy sessions and generic database errors.
- PostgreSQL project metadata with UUIDs, timestamps, length constraints and a listing index; initial Alembic migration.
- Compose database, one-shot migration, backend and nginx-served production frontend; named persistent volume and loopback-only ports.
- Isolated PostgreSQL test Compose stack, API tests, UI tests and an opt-in real browser journey.
- README setup/check instructions and architecture notes.

Verification:

- `docker compose up --build -d`: passed; development services left running.
- `npm run lint`, `npm run typecheck`, `npm run build`: passed.
- `npm run test -- --run`: 5 passed.
- `npm audit --audit-level=moderate`: zero vulnerabilities.
- Isolated `compose.test.yaml` run: 15 backend tests passed, including clean migration, schema drift, downgrade/upgrade, and PostgreSQL creation/listing.
- `docker compose exec backend python -m pytest -q`: 13 passed, 2 intentionally skipped without TEST_DATABASE_URL; those two passed in the isolated suite.
- Backend `ruff check .` and `ruff format --check .`: passed.
- `npm run test:e2e`: 1 Chromium journey passed, creating a project through the actual UI and finding it after reload.
- Manual Browse verification: empty state, project creation and mobile form checked. Desktop (1440 × 1000) and mobile (390 × 844) screenshots inspected.
- Restarted database and backend, then reloaded the browser: both verification projects remained persisted.
- Live liveness, readiness and nginx-proxied project listing passed.
- Mechanical interface detector reported no findings.

Initial failures resolved: npm's shared cache permissions (used a temporary cache); npm 10 dependency-update resolver crash (used npm 11 for the update); invalid Testing Library type options; transaction isolation applied too late in a test-bound session (configured at engine creation); initial frontend tooling advisories (patched and pinned versions).

Remaining limitations: local unauthenticated use only; project names may repeat; no editing/deletion; interrupted creation responses require refreshing before retrying. Tests emit one nonblocking upstream Starlette/AnyIO deprecation warning. Two real browser verification projects remain in the local database. No checks for later milestones were run because those features are outside scope.

Milestone 1 is retained as the foundation. The requested Milestone 2A increment is recorded below.

## Deferred

Milestone 2B below now scopes embeddings, index publication and dense retrieval. Question answering, canvas execution, evaluations and shared access remain deferred. Milestone 2A implements upload, parsing and chunk inspection only.

## Milestone 2A — Upload, processing and chunk inspection

Acceptance criteria (recorded before implementation):

- Open a selected project's Knowledge Base; upload exactly one PDF or UTF-8 TXT per request. Show paginated documents, byte size, upload time, processing state and safe errors.
- Enforce configurable upload limits, validate content, use generated persistent storage names, retain filename/hash/project metadata and keep repeated uploads separate. Failed uploads leave no visible document with a missing file.
- Save immutable numbered processing runs with character chunk size/overlap, parser/algorithm versions and separate chunk sets. Validate positive size and overlap smaller than size.
- Execute parsing/chunking in Celery/Redis with IDs only. PostgreSQL owns queued/running/succeeded/failed/cancelled state, progress and publication. Duplicate delivery cannot duplicate chunks; retries are bounded and failed runs can be retried as new versions.
- Parse text PDF and strict UTF-8 TXT, reject empty/invalid input and scanned PDFs requiring OCR, retain PDF page and character offsets. Publish all chunks atomically after success.
- Scope every document/run/chunk route to its project; support cancellation and recovery of stale jobs without publishing superseded results.
- UI exposes loading, empty, upload, validation, processing/progress, cancellation, retry, success and failure states, saved configuration and paginated version-specific chunks.
- Verify parsing/boundaries/provenance, upload validation, project isolation, duplicate delivery, failure/retry/cancellation/recovery, migrations, real UI journey and persistence across restarts using isolated test storage/database. Run Milestone 1 regressions.
- Update README and architecture; no embeddings, indexes, models, canvas or evaluation.

Implementation plan:

1. Add document, processing-run and chunk models/migration plus bounded upload/storage service and project-scoped APIs.
2. Add deterministic parsing/chunking, Celery worker and periodic PostgreSQL queue dispatch/stale recovery. Fence writes with run state and execution token; commit complete chunk sets atomically.
3. Extend project navigation with Knowledge Base upload, configuration, document status, run history and chunk pagination.
4. Add isolated backend/browser coverage, run regression and restart checks, and record outcomes/operational limits.

Status: complete for Milestone 2A. Full Milestone 2 (embeddings/indexing) remains deferred.

Implemented:

- Project Knowledge Base route, multipart upload, bounded document/history/chunk pagination, character configuration, saved versions, worker progress, safe errors, cancellation and retry via a new version.
- Persistent generated filenames with original metadata, SHA-256, byte size, project and upload time; separate duplicate uploads. Bounded request streaming and file validation; failure-safe staging and documented ambiguous-commit/orphan handling.
- Reviewed migration `0002` for documents, processing runs and chunks; project ownership chains, configuration/status constraints, immutable version keys and one-active-run constraint. Verified clean migration, schema drift, round trip and preservation of a Milestone 1 project during upgrade.
- Pinned Celery/Redis, pypdf and multipart dependencies; shared file volume, bounded worker processes and PostgreSQL queue dispatcher/recovery. No Celery result backend; all status/progress belongs to PostgreSQL.
- Deterministic page-local character windows, strict UTF-8/text PDF processing, page offsets/provenance, scanned/encrypted/malformed PDF errors, extraction/chunk/output/time bounds and atomic publication.
- Duplicate-delivery claim locking and execution-token checks prevent obsolete attempts from publishing. Transient/stale retries stop after three attempts. Cancelled jobs cannot publish in-flight results.
- Isolated PostgreSQL/storage tests and a complete separate browser stack on 5174/8001. Added dynamic nginx backend resolution to survive API container recreation.
- README workflow/API/operations and architecture decisions/limits updated.

Verification on 2026-09-09:

- Backend isolated PostgreSQL suite: 50 passed, including the final cleanup-error regression. Includes actual parsing, invalid/empty/oversized/chunked uploads, scoping, concurrent duplicate tasks, stale token fencing, cancellation, partial-failure rollback, safe retries, broker outage and migrations.
- Frontend `npm run lint`, `npm run typecheck`, `npm run test -- --run`, `npm run build`: passed; 11 component tests including the original five project tests.
- `npm run test:e2e` against isolated Compose: all 4 Chromium journeys passed (project creation/reload, TXT upload/settings/pagination/reload/focus, parsing failure/new version, PDF/page provenance).
- Desktop 1440×1000 and mobile 390×844 captures reviewed; mobile overflow assertion passed. Mechanical UI detector returned no findings. Independent review resolved both findings: persistent upload-settings errors/retry and keyboard focus after pagination.
- Restarted PostgreSQL, Redis, API, worker, dispatcher and frontend: 3 completed chunk sets compared unchanged through the API; all 5 stored test files matched persisted SHA-256 and byte size before/after. Existing chunks were reopened through the actual UI after restart. Force-recreating only the backend also preserved API access and the same 3 chunk sets through nginx without restarting the frontend.
- Backend lint/format checks passed. One existing Starlette/AnyIO deprecation warning remains; Playwright emits a nonblocking terminal color environment warning.

Resolved failures: an existing project browser test selected both loading and success status regions; its assertion now targets the creation message. Recreating the backend exposed stale nginx upstream DNS; the proxy now resolves Docker service names dynamically. UI polling previously cleared settings/action errors and pagination lost focus; state separation, retained controls and explicit heading focus fixed these cases.

Remaining limits: local unauthenticated use only; no OCR, embeddings/indexes/search, LLMs, canvas or evaluation. PDF extraction may be incomplete on pages mixing text and images. Cancellation cannot interrupt a parser call immediately; publication is prevented and execution is time-bounded. Crashes/ambiguous commits may leave unreferenced files requiring offline inspection. Backup/restore automation and deletion are not implemented. Browser verification data lives only in the separate test volumes; developer data was not reset.

Next actionable step: start/rebuild the local application with `docker compose up --build -d`, open a project and upload a source file. Any embedding/index milestone needs its own scope and provider decision.

## Milestone 2B — Vector indexing and retrieval

Acceptance criteria (recorded before implementation):

- Implement one real embedding provider behind a backend interface, selected by the user if no existing configuration exists. Credentials remain server-side and environment-driven; missing configuration returns an actionable error, never synthetic vectors. Record provider, model, dimensions and relevant embedding settings.
- Enable pgvector through Alembic. Immutable numbered project index snapshots identify exact processing runs and chunks and retain their embedding configuration. Validate dimensions and model compatibility; preserve previous ready versions while replacements build. Publish readiness only when all snapshot chunks have embeddings.
- Reuse Celery, Redis and the PostgreSQL durable queue/status patterns: bounded batched requests, concurrency, timeouts and retries; execution-token fencing; duplicate-delivery safety; cancellation; stale recovery; persisted batch progress. Partial failures cannot publish incomplete indexes. Reuse vectors only for exactly matching text and embedding configuration, scoped to the project.
- Provide project-scoped index creation, history/status and cancellation plus dense retrieval accepting an explicit ready index UUID, nonempty bounded query and integer top_k from 1 to 50. Use the index's embedding configuration for queries; reject unavailable or incompatible configurations. Return ranked text, source document/processing/chunk identity, filename, PDF page/offsets and cosine distance (lower is closer; not confidence).
- Extend the existing Knowledge Base with Index documents, persisted indexing progress/cancellation and distinct processed/indexing/indexed/failed states. Test retrieval exposes query, top_k and ready index selection, displays the exact version used and ranked source chunks, and handles loading, empty, validation and error states. No answers or chat.
- Test configuration/dimension compatibility, project/index isolation, partial failures, safe retries, duplicate delivery, cancellation and stale fencing. Use real isolated PostgreSQL/pgvector for database behavior and deterministic provider doubles only in tests. Verify clean and upgrade migrations, relevant backend/frontend regressions and frontend production build.
- Keep live embedding checks opt-in and bounded. Verify a small live document set through the UI when credentials are configured; otherwise explicitly report live checks unverified. Document exact setup, score semantics, retry/cancellation behavior and limitations.
- Do not introduce reranking, hybrid retrieval, React Flow, RAGAS or LLM answer generation.

Implementation plan:

1. Confirm embedding provider/model, inspect its official API documentation, and implement environment configuration, a typed embedding interface and strict response validation.
2. Add reviewed pgvector/index snapshot/job/embedding migrations and models, with exact chunk references, compatibility constraints and project-scoped services/APIs. Snapshot the latest successful processing version per eligible document at index creation; later processing cannot change that snapshot.
3. Extend the existing dispatcher and Celery worker registration for indexing. Reuse row-lock claims, execution tokens, bounded attempts and cancellation checks; persist complete validated batches and atomically publish only a complete index. Use exact cosine retrieval initially, without an approximate search index.
4. Integrate indexing and retrieval controls into the existing Knowledge Base and API module, retaining the established polling, error and accessible form patterns.
5. Run isolated migration/database/provider/worker tests, frontend regressions/build and browser verification; perform bounded live checks when configured. Update architecture, setup documentation and this status with actual results.

Status: Milestone 2B application implementation and automated verification delivered. After the user configured `OPENROUTER_API_KEY`, the bounded live OpenRouter adapter test passed. A full live document indexing/retrieval UI acceptance check remains pending.

Provider decision: the user initially chose OpenAI, then explicitly changed the provider to **OpenRouter**. The implemented adapter uses `openai/text-embedding-3-small`, 1536 dimensions, `https://openrouter.ai/api/v1`, server-side `OPENROUTER_API_KEY` and cosine distance. No live synthetic embeddings or fallback provider exists.

Implemented application behavior:

- Typed embedding contract and real OpenRouter HTTP adapter: strict model, vector count/order, finite/nonzero values and dimension validation; safe credential/credit/rate-limit/service errors; bounded inputs/responses/timeouts and no internal retries. Config is saved with provider/model/dimensions/endpoint fingerprint/revision. A shared Redis request budget covers indexing and retrieval.
- Alembic `0003` enables pgvector and creates `index_versions` and exact `index_chunks` membership/vector storage. Composite dimension constraints and nonzero checks protect vector compatibility. Project version allocation and one-active-build constraints preserve older ready indexes.
- Real project-scoped index creation/history/status/cancellation and retrieval endpoints. Creation snapshots latest successful processing runs; later processing cannot alter membership. Retrieval requires an explicit ready index and returns ranked text, document/run/chunk identity, source hash, filename, PDF page/character offsets and cosine distance.
- Celery indexing reuses the existing dispatcher, Redis broker and PostgreSQL job patterns. Up to 16 chunks per delivery, persisted checkpoints, exact-text/config/project reuse, token fencing, cancellation and 180-second stale recovery. Three consecutive failures per batch bound retries; incomplete builds never become searchable. Retry via UI creates a new version.
- React Knowledge Base indexing controls, safe configuration state, persisted progress/history, cancellation, ready-version selection and retrieval form with input validation, loading/errors, results and evidence metadata. Processing remains before indexing in the page flow; shell copy now reflects Milestone 2B.
- Environment/Compose wiring, schema readiness checks, test-only browser transport, opt-in live adapter check, setup and architecture documentation.

Verification on 2026-09-09:

- Isolated PostgreSQL/pgvector suite: **92 passed, 1 intentionally skipped** (live embedding test without `RUN_LIVE_EMBEDDINGS=1`). Covers 2A regressions, clean migration, Alembic drift check, downgrade/upgrade, preserving existing 2A chunks, provider errors, scoping, exact reuse, partial failures/resume, dimension constraints, bounded retries, concurrent duplicate delivery, cancellation and stale-token fencing.
- Frontend lint, strict type check and production build: passed. Vitest: **16 passed**, including five indexing/retrieval panel tests and all prior tests.
- Full browser fixture stack: **5 Chromium journeys passed, 1 configuration-specific case skipped**. The new journey uses actual upload/processing, Redis, dispatcher, Celery, PostgreSQL/pgvector, API and React, with only provider HTTP responses replaced by a module under `backend/tests/`. Confirms index persistence after reload, explicit version selection, retrieval and source evidence. All four existing project/document journeys passed.
- Normal local `docker compose up --build -d`: passed. Upgraded the existing database from `0001` to `0003`, preserved all three projects, and verified frontend-proxied health/readiness, index history and missing-key guidance. The normal app remains running on port 5173; temporary verification stacks were stopped without deleting persistent volumes.
- Default credential-free browser configuration: the missing-key journey passed separately (**1 passed**), with indexing disabled and document management available.
- Restarted the isolated database, Redis, backend, worker, dispatcher and frontend; one saved ready index retained byte-equivalent serialized vectors and returned its original evidence through the test transport.
- Backend Ruff lint/format and `git diff --check`: passed. Mechanical interface detector: no findings. Desktop/mobile screenshots captured and reviewed; fixes applied for processing-before-indexing order, mobile control spacing and stale shell copy. Independent UI verdict: **ship**, all three findings resolved.

Resolved verification issues: old Knowledge Base test mocks initially made unintended index API calls; fixtures now include those API responses. A new resume test mistakenly counted a retrieval query as repeated indexing and was corrected. Existing test ports were occupied; this run used isolated 8002/5175 ports without stopping the older stack. A restart-check subprocess initially omitted its test transport import and received a credential rejection with the fixture key; corrected transport setup then verified persistence and retrieval. No successful live provider call is claimed.

Remaining limits: live OpenRouter credential/model availability, paid indexing and semantic retrieval quality are pending. Each input is conservatively bounded to 8,191 UTF-8 bytes and each project index to 50,000 chunks. Exact search has no ANN index. Only one configured provider/model combination is active at a time; querying older incompatible indexes requires restoring their settings. Cancellation cannot undo a provider request already in flight or its cost. No token/cost accounting, deletion, answers, reranking, canvas, evaluation or shared authentication was added.

Next actionable step: set `OPENROUTER_API_KEY` locally and run `docker compose up --build -d`; process a small document, select **Index documents**, choose its ready version and run **Test retrieval**. Run the opt-in live adapter test if desired. Automated fixture verification does not replace this remaining live acceptance check.


### Live credential follow-up

The user supplied `OPENROUTER_API_KEY` locally. Backend, worker and dispatcher were recreated to load it. A real response returned `text-embedding-3-small` rather than the namespaced request ID `openai/text-embedding-3-small`. The adapter now accepts only the exact supported upstream alias as well as the namespaced ID; it still rejects other models and validates vector dimensions. No model fallback was introduced.

Verification: 29 targeted adapter/vector/model-alias tests passed; the opt-in live embedding test passed (two short inputs, 1536 dimensions). Backend Ruff checks passed. The key was not printed or committed. Earlier missing-key limitations above describe the initial verification run; credential access and live embedding generation are now verified. Full live document indexing/retrieval through the UI remains to be exercised. Next: open a project, process a small document, select **Index documents**, then use its ready index for **Test retrieval**.


### Live indexing/retrieval follow-up

Investigated the disabled retrieval control: one document had successfully processed into eight chunks, but its project had no index. Created index version 1 through the real API; the normal dispatcher/Celery worker embedded all eight chunks through OpenRouter and published the index successfully. A live project-scoped retrieval request against that explicit index returned one source chunk. No source text or credentials were printed. The UI still requires **Use index 1** to select that ready version before **Test retrieval** is enabled; live API indexing/retrieval are now verified, while the complete browser workflow has previously been verified with the isolated test transport.

## Milestone 3 — Grounded answers and playground

Acceptance criteria (recorded before implementation):

- Separate server-side OpenRouter chat configuration and provider interface; reuse credentials, require an explicit chat model, bound requests and sanitize failures.
- Single-turn execution accepts a project, ready index, question and top_k 1–50; reuses scoped retrieval, budgets the complete prompt with reserved output, and snapshots only evidence actually supplied with stable labels and full provenance.
- Evidence is untrusted data. Prompt requests evidence-only answers, source references and explicit insufficient evidence; no similarity threshold or claim of guaranteed grounding/injection prevention.
- Validate reference membership, flag invalid/missing citations without replacing them, and distinguish membership from semantic support.
- Persist successful, insufficient and failed runs, exact messages/configuration/evidence, model, usage when returned, stage timings and unavailable cost unless reported. Retain interrupted runs as failures after a bounded stale interval.
- Playground supports ready index selection, question/top_k, answer and clickable sources, evidence inspection, all request states and paginated persisted history without conversation carryover.
- Verify PostgreSQL migrations/isolation/persistence, context limits, citation validation, empty retrieval and failures with deterministic doubles; run regressions/build and full browser journey. Run two bounded live questions once the user supplies a chat model ID; report blockers honestly.

Status: implemented and verified on 2026-09-10. The user selected `openai/gpt-5.6-luna` after confirming the OpenRouter catalog ID. Existing embeddings remain unchanged.

Application files changed:

- `backend/app/providers/generation.py`: answer-provider protocol, OpenRouter non-streaming adapter, bounded requests, safe failures, usage/cost parsing and explicit incomplete-completion handling.
- `backend/app/pipelines/generation.py`: versioned single-turn prompt, whole-chunk context budgeting, stable labels and citation membership validation.
- `backend/app/models/query.py`, `schemas/query.py`, `services/queries.py`, `api/queries.py`: persisted execution, history/detail, scoped ready-index validation, snapshots, timings and interrupted-run recovery.
- `backend/migrations/versions/0004_query_runs.py`, model registry and index model: query table, listing index and composite project/index ownership constraint.
- `backend/app/core/config.py`, `main.py`, `compose.yaml`, `.env.example`: separate chat configuration and route registration. Local ignored `.env` now selects the user-approved chat model; secrets were not printed or committed.
- `frontend/src/features/playground/{api.ts,Playground.tsx}`, `app/App.tsx`, `app/styles.css`, `features/documents/KnowledgeBase.tsx`, `lib/api.ts`, `frontend/nginx.conf`: accessible playground/navigation, independent question form, source focus/evidence panel, statuses/history/pagination, safe API errors and longer query response timeouts.
- Backend query tests, test-only provider transport, frontend component/browser tests and isolated Compose fixture configuration cover the completed workflow.
- README and architecture document configuration, API, provenance, limitations, costs and operations.

Verification actually run:

- Isolated PostgreSQL/pgvector Compose suite: **113 passed, 1 skipped** (opt-in live embedding test). Includes clean migration, Alembic schema drift check, downgrade/upgrade and preservation tests; scoped query runs and ready-index rejection; context bounds, invalid/missing references, empty retrieval, generation/retrieval/configuration failures, sanitized unexpected errors, stale recovery, incomplete-completion usage and durable snapshots. Existing ingestion/indexing regressions passed.
- Frontend `npm run lint`, `npm run typecheck`, `npm run build`: passed. `npm run test -- --run`: **19 passed**.
- Isolated Chromium suite on ports 5175/8002: **6 passed, 1 skipped** (credential-missing case intentionally excluded in the configured fixture stack). Complete playground journey starts with upload, processing and indexing, then answers/citation focus, insufficient evidence and saved history after reload. Existing projects, TXT/PDF processing, failures and retrieval journeys passed.
- Backend `ruff check .`, `ruff format --check .` and `git diff --check`: passed. Mechanical UI detector returned no findings.
- Desktop/mobile evidence screenshots reviewed. One focus outline overlapped explanatory text; added spacing and restored the incumbent green focus color, with a targeted browser rerun for confirmation.
- Rebuilt local development services and applied migration without resetting persistent data. A separate test stack used alternate ports after detecting an older test stack already occupying 5174/8001.

Bounded live verification (actual OpenRouter embedding and chat calls):

- Created a clearly named local verification project, uploaded/processed/indexed a 58-byte orchard TXT source. Ready index publication succeeded with real embeddings.
- “What does the orchard grow, and when does harvest begin?” → “The orchard grows apples, and harvest begins in September. [S1]”. Status `succeeded`, valid S1, one included source, 173 total tokens, retrieval 1.084 s, generation 2.049 s, total 3.143 s. Provider-reported generation cost $0.0000536.
- “What is the launch code for the spaceship?” → explicit insufficient evidence; no fabricated citation. Status `insufficient_evidence`, same source supplied, 177 total tokens, retrieval 0.743 s, generation 1.614 s, total 2.361 s. Provider-reported generation cost $0.0000614.
- Opened the live persisted runs in Chromium, clicked S1 and inspected evidence. These two examples verify the integration, not general answer quality or prompt-injection resistance. Generation charges exclude embedding calls; no total-query cost was invented.

Remaining limitations: unauthenticated localhost use; single-turn, non-streaming synchronous execution; no cancellation; manual retry after failures, with stale recovery triggered by reads after five minutes. Context uses a conservative UTF-8-byte budget with an operator-configured model ceiling, not an exact tokenizer. Reference validation does not judge semantic support. Network/DB interruptions can make a response ambiguous; inspect history before retrying. No reranking, hybrid search, React Flow, RAGAS or shared-access release work was added. One existing Starlette/AnyIO deprecation warning remains.

Next actionable step: open `http://localhost:5173`, select your project and **Open RAG playground**, then ask questions against a ready index. The live orchard verification project remains available with both saved runs.

Final confirmation: both live run responses compared exactly unchanged after backend/frontend recreation. The test frontend initially retained its old image despite rebuilding; explicit recreation loaded the new asset, and the final targeted playground journey passed again against the updated application.

Final UI reviewer disposition: **ship**. Evidence focus spacing/color: **resolved** on desktop and mobile; no remaining visible regressions from the fix. `DESIGN.md` and `.impeccable/design.json` record the inherited interface styles for future changes.

## Milestone 4 — Saved visual pipelines

Acceptance criteria (before implementation): exactly one Question → Retriever → Prompt → LLM → Answer graph; accessible React Flow palette/canvas/settings; ready project index and bounded top_k; safe question/context prompt variables with application citations; server-allowed chat model/output/temperature settings; project-scoped immutable execution versions separated from layout; create/save/reopen/duplicate and unsaved-state display; reuse existing RAG services and persist exact version/effective settings; real persisted run progress, failures and evidence inspection. Verify graph/API isolation, version history and execution settings with provider doubles, PostgreSQL migrations, browser journey, regressions/build and a bounded configured live call. Evaluation and other graph types remain deferred.

Status: implemented and verified on 2026-09-10. Milestone 4 is complete within the requested five-node scope; evaluations and shared-access release work remain deferred.

Actual code changes:

- `frontend/src/features/pipelines/{PipelineEditor.tsx,api.ts,api.test.ts}`: pinned React Flow editor with structured nodes inspired by the supplied AI Elements workflow, click/drag palette, canvas connections/deletion/keyboard controls, selected-node settings, ready-index/model options, safe prompt guidance, immutable-version selection, save/reopen/duplicate, canonical unsaved comparisons, API run polling and history. Responsive readable canvas defaults and visible selection preserve the existing interface.
- `backend/app/{schemas,models,services,api}/pipeline*.py`: strict discriminated graph/configuration/layout schemas, project pipelines and append-only versions, scoped persistence and execution APIs, serialized version allocation and ready-index/model validation.
- Migration `0005_pipelines.py`, model registry, query model/schema and readiness: new persistent tables, composite project/version references from query runs, and schema checks. No persistent developer data was reset.
- Existing `services/queries.py`, `pipelines/generation.py` and provider adapter: reused retrieval/context/generation/citation engine; literal one-pass template rendering; captured pipeline version/configuration; real background API execution with existing persisted failure recovery. Playground still uses the same synchronous path.
- Server config, Compose and `.env.example`: optional `CHAT_MODELS` allowlist with credentials remaining server-side. App navigation and shared RunResult expose editor and effective prompt/model snapshots. README, architecture and inherited design records updated.
- `backend/tests/test_pipelines.py` and `frontend/e2e/pipelines.spec.ts`: direct invalid-graph API tests, project isolation, save/reopen/layout/duplication, effective top_k/prompt/model/parameter changes, unchanged historical versions/runs, failure/recovery and browser execution/citations.

Final checks actually run:

- Isolated PostgreSQL/pgvector backend suite: **129 passed, 1 skipped** (opt-in standalone live embedding test). Includes clean migrations, schema drift, downgrade/upgrade, prior data preservation and all existing ingestion/index/query regressions.
- Frontend: **23 Vitest tests passed**; lint, strict TypeScript and production build passed. React Flow is pinned in package.json/lockfile; installation audit reported zero vulnerabilities.
- Final isolated Chromium suite: **7 passed, 1 skipped** (missing-credential scenario excluded in the configured fixture stack). Editor journey creates/configures/drags/saves/reopens/runs/inspects citations, changes versions, verifies unsaved execution protection, duplicates, deletes/re-adds nodes and checks validation. Existing Knowledge Base/Playground journeys passed.
- Ruff lint/format and `git diff --check`: passed. Mechanical UI detector: no findings. Desktop/mobile screenshots reviewed; final independent UI disposition **ship**, with readable-node zoom and synchronized selection both resolved.
- Rebuilt the normal local Compose services and applied `0005` without deleting persistent data. Reopened the real live pipeline/run in Chromium, focused S1 evidence, and compared the saved live run exactly unchanged after recreation. Normal app remains available on port 5173.

Resolved verification failures: initial browser tests started before the new isolated frontend was ready; retry after startup passed. Wrapped select labels needed explicit accessible names. PostgreSQL JSONB key ordering initially made a saved graph appear dirty; canonical comparison and a regression test fixed it. The visual review found tiny fit-to-canvas defaults and a mismatch between form selection and canvas highlight; readable pan/zoom defaults and shared selection fixed both. TypeScript caught a union narrowing error while adding keyboard selection synchronization; corrected before the final build.

Remaining limitations: localhost unauthenticated use, one fixed graph template, invalid drafts held only in browser memory, shared operator-configured model context ceiling, non-streaming background API execution without cancellation or a durable generation queue. Interrupted tasks become failed on a detail/history read after five minutes; paid requests are never retried automatically. Citation membership is checked but semantic support is not scored. One existing Starlette/AnyIO deprecation warning and Playwright terminal-color warning remain. No live credential/model blocker.

Next action: open a project at `http://localhost:5173`, choose **Open pipeline editor**, then **New pipeline**, select a ready index, configure/save a version and run a question. The existing live orchard project also contains the completed verification pipeline.

Live check on 2026-09-10: saved a version-1 pipeline in the existing live orchard project and executed one question using the real configured `openai/gpt-5.6-luna` chat model and existing OpenRouter embeddings. Answer: “The orchard grows apples. [S1]”; succeeded, valid S1, no invalid citations, 209 reported tokens, 2.780 seconds total execution, provider-reported generation cost $0.0000548 (excludes query embeddings). No live credential/model blocker. Verification pipeline and run remain in local storage.


Milestone 4 usability follow-up: moved the question/run form above the canvas so it is visible before graph configuration, and added a synchronized question field to the Question node settings. Execution still requires an immutable saved version; this does not change graph parameters or create a new version when the run question changes.
Follow-up verification: frontend lint/typecheck/build and all 23 unit tests passed. Rebuilt the local frontend; Chromium confirmed that the question form precedes the canvas, both question fields stay synchronized, a saved version enables Run pipeline, and mobile has no horizontal overflow. Desktop/mobile captures inspected. No additional paid provider call was needed for this layout change.

Save usability follow-up: save blockers now appear immediately beneath Save version, including missing index/model/graph/name, loading/run state and an already-saved explanation. A Choose ready index action selects Retriever and focuses its index field. Index selection and invalid top_k now have separate messages. Verified against the real Customer Support project in Chromium: missing-index reason visible, shortcut focuses index selector, selecting its existing Index 1 enables Save version, and an empty name reports its specific blocker. No pipeline was saved or paid call made in this UI check. Frontend lint/typecheck/build and all 23 tests passed; rebuilt the local frontend.

Outstanding user report before GitHub handoff: Save version reportedly remains disabled after selecting an index in the user's current browser draft. A fresh browser check of the same Customer Support project enabled saving with Index 1, the configured model, and the default prompt/graph. The current unsaved draft is not available through backend APIs; a screenshot of its validation message was requested. This specific report remains unresolved despite the passing fresh-workflow checks.

## Project workspace refactor — evaluation paused

Acceptance criteria (scope for this refactor): persistent project switcher and active/responsive navigation; direct project/page/editor/version links; state-derived Overview; focused Knowledge Base details and pipeline editor; one shared Playground answer/evidence implementation; read-only supported Settings; warnings before discarding unsaved pipeline changes; frontend regression checks and isolated browser journeys; updated architecture documentation. No evaluation, schema changes, backend rebuild or additional dependencies.

Implementation: project shell and route parser; Overview and Settings backed by existing APIs; saved pipeline list; editor Save/Test toolbar and collapsible palette; pipeline/version selection and execution moved into Playground; expandable run history and metadata; document detail links, advanced processing disclosure and bounded chunk list. Existing direct-index generation, retrieval diagnostics, upload/processing/index jobs, cancellation, pipeline duplication and immutable versions are preserved.

Verification is in progress. Initial frontend suite: 25 tests passed, lint/typecheck/build passed. Initial browser pass: six passed, one intentionally skipped, two failed. Failures exposed rejected browser-Back navigation leaving a dirty editor (route guard corrected) and an outdated test expecting New pipeline to be a button rather than a link (test updated). Desktop/mobile review also corrected inherited palette grid placement and excessive chunk-list height. Final results are recorded below.


Final verification: **25 frontend tests passed**, strict typecheck, lint and production build passed. Isolated Chromium suite: **8 passed, 1 skipped** (credential-free configuration scenario is intentionally excluded from the configured provider fixture stack). Verified upload → processing → index → pipeline configure/save/reopen/version/duplicate → Playground answer/citation journey, direct URLs and refresh, project isolation, browser Back/Forward, rejected unsaved navigation and mobile menu. Desktop/mobile screenshots were inspected. Fixed a primary-link foreground contrast regression found in Overview. No paid provider calls were made. Backend source, migrations and developer data were unchanged.

Remaining UI limitations: project settings are read-only because the API has no update endpoint; unsaved drafts are not recovered after a confirmed exit; cancelling native history navigation can retain a duplicate history entry; long graphs require canvas pan/zoom, especially on mobile. Model availability is configured availability rather than a connectivity check. Evaluation remains paused.

Next action: review the project workspace in the local app and use Knowledge Base → Pipelines → Test pipeline to exercise an existing ready index. Screenshots are generated in `frontend/test-results/` (ignored test artifacts).

Local handoff: rebuilt and recreated only the normal frontend service at port 5173. Read-only browser inspection of the existing Customer Support project confirmed its actual Overview counts and contextual Playground action. Final desktop/mobile captures are `frontend/test-results/final-overview-desktop.png` and `final-overview-mobile.png`; the primary link foreground was checked as white after the contrast fix. Mechanical source UI scan and `git diff --check` passed. The separate `rag-workspace-e2e` verification stack was stopped without removing its volumes.

## Linear visual direction — Knowledge Base pilot

The user rejected the initial green/serif workspace and explicitly selected Linear as the design reference. This increment is limited to Knowledge Base and its surrounding shell: compact neutral navigation, sans-serif type, document table, separate Documents/Indexes views, upload disclosure and a right-hand inspector that becomes a full-width mobile detail view. Existing upload validation, processing/cancellation, chunks/provenance and indexing/retrieval behavior are retained. The view query survives refresh. Other pages remain on the previous visual system until this first screen is reviewed.

Verified: 25 frontend tests, strict TypeScript, lint and production build passed. Full isolated Chromium suite passed 8 tests with 1 intentional missing-credential skip. Desktop/mobile inspection caught and fixed two inherited-style collisions (green button color and the desktop mobile-menu toggle). The final view-query change is covered by a targeted index browser test. No backend or evaluation development, no paid provider calls, and no developer data changes.

Pilot follow-up verification: targeted index browser test passed after adding persisted Documents/Indexes view selection. Inter is self-hosted from its official repository with the OFL license included, matching Linear's documented typography; the generic-font detector exception is tied to the user's explicit reference. Final screenshots are `.lavish/linear-pilot/desktop.png` and `mobile.png`. Review this single surface before expanding its theme across other routes.

### Workspace design extension — 2026-09-10

Extended the user-selected Linear direction to Overview, saved pipelines, the viewport-height editor, Playground, Settings and project management. Added collapsible node settings and initial graph fit; kept all execution in Playground. Reviewed real-state desktop/mobile screenshots in `.lavish/linear-workspace/`. Verification: 25 frontend tests, TypeScript, ESLint and production build passed; isolated Chromium suite passed 8 tests with 1 missing-credentials scenario skipped because this stack configures deterministic providers. The pipeline journey additionally checks canvas height and width reclaimed by hiding settings. No evaluation or backend behavior added. Small-screen graph editing still requires pan/zoom; labeled node forms remain available below the canvas.

### Dark reference editor — 2026-09-10

Implemented the user's supplied charcoal/lavender design across the shared theme. The editor has a prominent editable name, larger vertical nodes, readable selection, a node-specific inspector, and an explicit reversible Arrange vertically action. Existing saved positions and APIs remain compatible. Refitting responds to container size changes. Fixed stale connector geometry on orientation changes and a save/refresh URL race found by Chromium. Route changes reset page scroll to prevent the mobile header/content opening partway down the prior page.

Verified: 25 unit tests, typecheck, lint and production build; isolated Chromium suite 8 passed, 1 skipped (missing-credentials scenario excluded with configured provider fixtures). Desktop/mobile screenshot review performed with real developer data; no new paid model calls or saved developer pipeline changes. Mobile shows the full vertical graph fitted into its canvas, with zoom/pan and node forms below. Existing horizontal graphs require Arrange vertically and Save to adopt the new layout. No evaluation development.
