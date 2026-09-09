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

Embeddings and index publication (remaining Milestone 2), model access, question answering, canvas execution, evaluations and shared access remain deferred. Milestone 2A implements upload, parsing and chunk inspection only.

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
