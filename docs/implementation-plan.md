# Implementation plan

## Robust ingestion roadmap — Phase 1 acceptance criteria (2026-09-24)

Status: **Phase 1 complete on 2026-09-24** on
`codex/robust-ingestion-roadmap`; Phase 2 is next.

- Add strict application-owned extracted/cleaned document, page, block, source-span,
  finding, measurement, transform-audit and chunk-span contracts with bounded metadata
  and deterministic identifiers/hashes.
- Add only additive immutable derivation, block and chunk-span records. Composite
  foreign keys must prove project/document/processing ownership and prevent a chunk
  from claiming lineage from another processing run.
- Persist a complete extracted derivation, cleaned derivation, their blocks and exact
  chunk-to-cleaned-block spans atomically with successful schema-v2 processing. Failed,
  cancelled or fenced work must not expose partial successful derivations.
- Adapt schema-v2 Existing Files, Website, S3, Notion and Confluence paths to emit the
  same canonical IR. Preserve page numbers and available heading/provider provenance;
  represent unclassified native blocks explicitly as `unknown`.
- Make the legacy character chunker consume cleaned blocks while reproducing Phase 0
  schema-v2 evidence text and offsets. Schema-v1 execution and historical indexes,
  queries and experiments remain unchanged and report block lineage as unavailable.
- Add project-scoped, paginated derivation and block reads plus bounded chunk-span
  reads. The ingestion run inspector gains read-only Extracted and Cleaned tabs for v2
  items and truthful unavailable/empty/error states for legacy history.
- Verify strict contract rejection, deterministic ordering/hashes, ownership
  constraints, cross-block mappings, atomic failure/cancellation, migration
  downgrade/re-upgrade preservation, pagination/query plans, all native regressions and
  Agent Browser desktop/narrow/mobile inspector journeys.

Phase 1 does not add layout engines, bounding-box synthesis, OCR, quality scoring,
semantic or parent/child chunking, near-duplicate detection or sensitive-data policy.

Implementation and verification evidence:

- Strict Pydantic contracts now define versioned extracted and cleaned documents,
  ordered pages/blocks, normalized optional geometry, bounded JSON attributes,
  discriminated source spans, findings, measurements, transform audits and exact
  chunk-to-block spans. Stable block IDs and document hashes are deterministic.
- Migration `0021` adds immutable project/document/processing-owned derivations,
  bounded block rows and exact span rows. Composite foreign keys require each span to
  reference a chunk and the cleaned derivation from the same processing run; content
  blocks are inserted in bounded batches in the caller's success transaction.
- Existing Files, Website, S3, Notion and Confluence schema-v2 execution now construct
  the same canonical IR, retain available pages/headings/provider IDs and route the
  existing character-window output through cleaned blocks. Schema-v1 paths and stored
  history remain unchanged and expose canonical lineage as unavailable.
- Project-scoped reads list derivations, paginate blocks through the composite primary
  key and return bounded chunk spans. The ingestion run inspector provides keyboard-
  accessible Extracted/Cleaned tabs, measurements, type/page/heading/source context,
  pagination and explicit legacy/unavailable/empty/error states.
- Backend Ruff lint/format passed. A fresh isolated PostgreSQL/pgvector run passed
  **268 tests with 4 opt-in live tests skipped**; focused tests cover every connector,
  deterministic IR, malformed contracts, joined/split spans, cleaned-run ownership,
  project isolation, atomic failure/cancellation and the indexed block query plan.
  Populated migration downgrade to `0020`, legacy processing/chunk preservation and
  re-upgrade to `0021` passed.
- Frontend formatting, structure/ESLint, strict TypeScript, all **106 Vitest tests
  across 29 files**, and the production build passed. Agent Browser completed a real
  v2 upload/process/save/run/inspect journey at the canonical Vite URL, switched both
  inspector tabs by keyboard, verified the legacy unavailable state and found no app
  console errors or horizontal overflow at 1440, 1024 or 390 pixels.

## Robust ingestion roadmap — Phase 0 acceptance criteria (2026-09-24)

Status: **Phase 0 complete on 2026-09-24** on
`codex/robust-ingestion-roadmap`; Phase 1 is next.

- Freeze schema-v1 TXT, PDF, Website, S3, Notion and Confluence extraction/cleaning/
  character-window output before refactoring. Historical schema-v1 pipeline versions
  must remain readable and executable without changing their persisted JSON or output.
- Introduce application-owned current-behavior extractor, cleaner and chunker
  interfaces with stable runtime versions and typed, safe stage errors. Connector code
  may retain discovery, identity and source-specific extraction/provenance, but it may
  not own a separate general-purpose whitespace/boilerplate cleaner or character
  window loop.
- Add a strict schema-v2 ingestion envelope. New pipelines use v2, while a saved v1
  version remains labelled **Legacy character extraction** and changes to v2 only
  through an explicit **Upgrade as draft** action that does not mutate or save the
  historical version.
- Define `normalize_whitespace=false` for v2 as preserving source whitespace exactly
  except for explicitly configured literal boilerplate removal. V1 retains its
  historical collapse-and-trim behavior for reproducibility. The same selected
  semantics must apply to every connector.
- Execute v2 Existing Files through the saved Extract, Clean and Chunk nodes. Changing
  any v2 extraction, cleaning or chunk setting creates a new immutable processing run;
  an exact compatible successful run may be reused.
- Include extractor, cleaner and chunker runtime versions plus canonical configuration
  in deterministic processing hashes. Persist and expose the exact versions used by
  completed v2 processing/run items without fabricating lineage for v1 history.
- Make v2 Clean controls keyboard-accessible and editable, map server validation to
  actionable draft errors, retain dirty-navigation behavior, and keep unsupported
  layout/OCR controls absent.
- Verify focused contracts and parity, Existing Files execution, remote connector
  regressions, duplicate delivery, cancellation, stale recovery, project isolation,
  clean/populated migration and downgrade preservation, Ruff, frontend formatting/
  lint/typecheck/Vitest/build, existing answer/Playground/experiment regressions, and
  Agent Browser desktop/narrow/mobile journeys at the canonical Vite URL.

Phase 0 does not add Docling, OCR, layout extraction, derivation tables, semantic or
parent/child chunking, near-duplicate detection, sensitive-data processing, new source
formats, or live paid/provider calls.

Implementation and verification evidence:

- Schema-v1 and schema-v2 are separate strict backend contracts. New drafts use v2;
  historical v1 JSON remains unchanged and is explicitly upgraded only in a detached
  unsaved draft.
- One application-owned module now owns native TXT/PDF extraction, deterministic
  versioned cleaning, character windows, processing identity and safe stage errors.
  Website, S3, Notion and Confluence retain source-specific extraction/provenance but
  consume the shared cleaner and chunker.
- Existing Files v2 now executes its saved Clean settings, preserves whitespace when
  normalization is disabled, persists canonical configuration/runtime versions and
  output hashes, and reuses only an exact successful processing identity. V1 retains
  its prior parser/chunker execution path.
- Migration `0020` adds nullable processing identity/output metadata. Clean migration,
  downgrade to `0019`, legacy row/chunk preservation and re-upgrade were verified.
- Backend Ruff lint and format passed. The isolated PostgreSQL/pgvector suite passed
  **264 tests with 4 opt-in live tests skipped**. Frontend formatting, structure/ESLint,
  strict TypeScript, all **104 Vitest tests across 28 files**, and the production build
  passed.
- Agent Browser verified new-v2 and legacy-upgrade workflows at 1440, 1024 and 390
  pixels. A long-provenance mobile overflow found during the pass was fixed and
  rechecked at an exact 390-pixel viewport; application errors were empty and console
  output contained only Vite/React development messages.

## Evidence-first workspace refinement — 2026-09-24

Status: implemented; final verification recorded below.

- Consolidated the dark workspace tokens around low-chroma charcoal surfaces, a single
  desaturated periwinkle interaction accent, readable secondary text, semantic
  sage/ochre/brick statuses, consistent radii, visible focus and restrained 150ms
  transitions. The single authored stylesheet convention remains intact.
- Made the shell quieter and denser. Active navigation now uses a subtle tonal state
  and one-pixel indicator; mobile navigation retains 44px targets and Escape handling.
- Added a real-data lifecycle to Overview, including correct handling for historical
  ready collections, and replaced the Knowledge Base's oversized dashed empty area
  with a compact onboarding action wired to the existing upload flow.
- Pipeline rows now retrieve their real latest immutable version, updated date and
  validated test/run readiness. Answer editor nodes are denser; selected-node settings,
  graph behavior, saved coordinates and unsaved-state behavior remain unchanged.
- Playground keeps its evidence-first layout while replacing generic sparkle cues with
  source-review iconography. Experiments now presents dataset, candidate and
  metrics/execution stages with a sticky desktop run summary and collapsible mobile
  sections, preserving drafts, metric warnings, costs and result inspection.
- Browser review covered representative Overview, Knowledge Base, Pipelines, editor,
  Playground and Experiments views at 1440px, 1024px and 390px. No page-level overflow
  or application console errors were observed; Vite development/HMR messages were the
  only console output.

Verification:

- Frontend Prettier, structure/ESLint, strict TypeScript, all **103 Vitest tests
  across 28 files**, and the route-split production build passed. The largest output
  chunk is 242.87 kB and Vite emitted no size advisory.
- Agent Browser reviewed representative desktop, tablet and 390px mobile states for
  Overview, Knowledge Base, Pipelines, the answer editor, Playground and Experiments.
  Mobile pages measured exactly 390px with no document overflow. Navigation closes on
  Escape and restores focus to its trigger; the document onboarding action opens the
  real upload region; experiment stages and dataset import disclosure toggle correctly.
- The one required Impeccable detector run reported only five Inter-font warnings.
  These are intentional exceptions: the user explicitly required preserving Inter,
  `DESIGN.md` records that decision, and the self-hosted font and OFL license are
  committed. It reported no other mechanical design findings.

## Data management, recovery, and reusable-index handoff — 2026-09-24

Status: implemented and verified.

- Knowledge Base documents have explicit, confirmed deletion with backend
  protection for active processing, immutable index membership, and ingestion
  history. Eligible deletion removes the stored upload and only its unreferenced
  processing data. The complete document catalog can be sorted newest or oldest
  before pagination.
- Missing/deleted project routes clear stale project state and return to Projects.
  Transient failures use specific recovery actions instead of an unexplained
  generic Retry control. The first-project creation form has clearer guidance,
  responsive actions, character counts, and no duplicate empty state beneath it.
- The ingestion boundary is now labeled **Embed → Publish reusable index**.
  Publication exposes the completed vectors without embedding passages again.
  Successful runs and ready source snapshots link the exact index directly into a
  new answer pipeline. Optional variant work is labeled **Reprocess saved source**
  or **Create another index version** so it is not confused with the normal handoff.
- Final `main` verification passed 86 focused tests against an isolated
  PostgreSQL/pgvector database, backend Ruff lint/format, frontend formatting,
  structure/ESLint, strict TypeScript, all 103 Vitest tests across 28 files, and
  the route-split production build.

## Production-quality audit and hardening — started 2026-09-23

Overall status: **Complete — all four phases finished on 2026-09-23.** This section is
the source of truth for the current whole-codebase quality pass. Earlier dated
sections remain historical delivery records; where their interim status or test
counts differ, this section and the final verification record below take precedence.

### Phase 0 — audit baseline and prioritized plan

Status: **Complete on 2026-09-23.** The clean linked `main` worktree at
`/private/tmp/rag-quality-studio-main` matched `origin/main` at `8ec4d63` before the
audit. The separate `feature/source-snapshot-index-variants` worktree had one local
commit and a substantially different 46-file tree; it was inspected and left
unchanged. Generated output, dependencies, locks, screenshots, binaries and build
artifacts were excluded from source-quality judgment.

Reviewed scope: repository instructions and Git topology; all application/test file
inventories; backend API, settings, database/session boundary, models, migrations,
services, connector/provider adapters and workers; frontend routing, shared transport,
features, primitives, CSS, unit/browser tests and build configuration; Compose and
environment configuration; README and architecture/development/deployment/frontend
standards. Static scans covered unsafe execution/deserialization, secret-like tracked
content, broad exception boundaries, direct database work in routes, HTTP timeouts,
project-scoped queries, accessibility semantics, focus/motion, raw controls,
hard-coded colors, storage, oversized modules and duplicated persistence flows.

Baseline evidence:

- Frontend Prettier, structure/ESLint and strict TypeScript passed; 88 Vitest tests
  across 24 files passed. The production build passed but emitted one 659.92 kB
  minified / 204.33 kB gzip JavaScript chunk advisory.
- Backend Ruff lint/format passed. Local pytest passed 140 tests and explicitly
  skipped 117 PostgreSQL/live-dependent tests. The isolated PostgreSQL/pgvector
  Compose suite then passed 253 tests with four opt-in live-provider checks skipped.
  Constraint-violation log entries were expected assertions. One upstream
  Starlette/AnyIO test-client deprecation warning remains.
- `npm ci` reported zero known npm vulnerabilities. No tracked credential or private
  key signature was found. Provider calls, external source fetches and destructive
  persistent-data operations were not run.
- Read-only browser inspection used the canonical Vite URL at 1280 px and 390 px.
  Projects, Overview, Pipelines, the ingestion editor, Knowledge Base and Experiments
  loaded without JavaScript exceptions or page-level horizontal overflow. Controls
  exposed accessible names, editor stages remained keyboard-reachable, status used
  text as well as color, and reduced-motion CSS disables execution animation.
  React Flow emitted one attribution-policy warning. The user's original Vite process
  was restored after inspection.
- The Impeccable detector reported two generic-font warnings for Inter. Those are
  false positives for this product because `DESIGN.md` explicitly selects the
  self-hosted font and its OFL file is tracked. The detector found no other mechanical
  pattern violation.

Frontend audit score: **14/20 (Good; weak dimensions require hardening)**.

| Dimension | Score | Evidence |
| --- | ---: | --- |
| Accessibility | 3/4 | Semantic landmarks, labels, focus handling, text statuses and reduced-motion behavior are present; primitive submit defaults and a few raw feature controls weaken the floor. |
| Performance | 2/4 | The application eagerly loads every route and React Flow into a 659.92 kB entry chunk. |
| Responsive design | 4/4 | The inspected desktop/mobile routes had no page overflow, and editor settings stack at 390 px. |
| Theming | 3/4 | Semantic dark tokens are coherent; a few documented legacy color literals and a large incumbent cascade remain. |
| Implementation integrity | 2/4 | Product-specific behavior is strong, but a 2,465-line editor, 989-line connector worker, four copied persistence flows, a stray JSX glyph and hidden attribution reduce confidence. |

### Audit findings and disposition

Every finding below has an implementation destination. `P1` means release-significant,
`P2` means important maintainability/correctness work, and `P3` means bounded polish.
There is no observed `P0` data-loss or core-workflow blocker.

| ID / severity | Evidence and affected files | Proposed change and acceptance criteria | Dependencies, risks and verification |
| --- | --- | --- | --- |
| Q-01 / P1 | `frontend/src/app/WorkspacePage.tsx` statically imports every route. `npm run build` produces one 659.92 kB minified entry chunk and warns above 500 kB. | Lazy-load feature routes behind one accessible loading boundary. The entry chunk must fall below Vite's default advisory without raising the threshold; direct hash URLs, focus restoration and errors must behave unchanged. | Phase 2. Risk: Suspense timing can destabilize focus/tests. Verify build chunk report, route unit tests and direct-link/back-forward Chromium journeys. |
| Q-02 / P1 | `frontend/src/features/ingestion-pipelines/IngestionPipelineEditor.tsx` is 2,465 lines and owns source defaults, four connector forms, graph rendering, catalog loads, preview/run polling, schedules and most markup. This conflicts with the feature ownership rules in `docs/frontend-standards.md`. | Extract connector settings, graph presentation and cohesive controller responsibilities with explicit typed props. Preserve API payloads, immutable-draft behavior, polling fencing, stage focus and layout. No arbitrary pass-through wrappers. | Phase 2 after Q-06/Q-08. High regression risk in the broadest UI; use existing focused unit/browser suites plus desktop/mobile screenshots and the detector. |
| Q-03 / P1 | `backend/app/services/{website,s3,notion,confluence}_ingestion.py` repeat source-item lookup, immutable-revision reuse, file/document/run/chunk persistence, cleanup and outcome selection. | Introduce a small application-owned immutable-artifact persistence boundary with connector-specific extraction/provenance callbacks. Exact identities, hashes, timestamps, cleanup and transactions must remain connector-tested. | Phase 3. Risk: provenance or retry semantics could drift. Verify all connector, ingestion, snapshot, cancellation and migration/integration tests. |
| Q-04 / P2 | `backend/app/workers/ingestion.py` is 989 lines and mixes common orchestration with Website/snapshot and three credentialed connector paths. | Separate remote-source advancement from job lifecycle/fencing and use an explicit connector strategy map where behavior is genuinely shared. Keep Website snapshot reuse distinct and retain bounded checkpoints/cancellation. | Phase 3 after Q-03. Risk: duplicate delivery and paid-work fencing are sensitive; require full PostgreSQL suite and deterministic connector browser journeys. |
| Q-05 / P2 | `frontend/src/components/ui/button.tsx` does not set a default HTML type. Most call sites rely on context; implicit submit is intentional in only a small number of forms. | Default the primitive to `type="button"` when it renders a button and mark every real submit explicitly. Add regressions proving secondary form actions do not submit and submit actions still do. | Phase 1. Risk: missed submit call sites. Verify component tests plus all form-related frontend tests and Chromium journeys. |
| Q-06 / closed | An initial concatenated source excerpt appeared to contain a stray JSX glyph in `IngestionFlowNode`. A focused reread of the clean `main` file confirmed it was only the root tag's normal closing delimiter. | No code change. Keep this correction in the audit so the initial suspicion is not repeated as a defect. | Closed during Phase 1 before implementation; TypeScript/build remain the verification boundary. |
| Q-07 / P2 | The ingestion `<ReactFlow>` sets `proOptions={{ hideAttribution: true }}`; `frontend/e2e/ingestion-layout.spec.ts` requires zero attribution nodes. The browser warns on every editor load. Upstream policy asks non-Pro users to keep attribution visible; no entitlement is recorded. | Restore the unobtrusive attribution and update layout tests. Acceptance: no console warning, no overlap at desktop/mobile, and the attribution link remains keyboard-safe. | Phase 1. Risk: canvas overlay collision. Verify focused Playwright/layout screenshots and console. If the owner later confirms Pro entitlement, record it before reconsidering. |
| Q-08 / P2 | Canonical runtime guidance requires `127.0.0.1:5273`, but `README.md`, `compose.yaml`, `backend/app/core/config.py`, its CORS test and Playwright defaults still use 5173/5174. | Make Vite's script, CORS defaults, Compose/local documentation and browser defaults consistently use 5273. Keep isolated backend/data services separate and never point fixtures at developer data. | Phase 1. Risk: port collisions and stale operator muscle memory. Verify config tests, Compose rendering, README commands and canonical-browser startup. |
| Q-09 / P2 | The top of this plan still called snapshot slices 3–5 pending while later sections mark them complete; recent historical records claim 89/90 frontend tests while the clean baseline has 88. `docs/frontend-standards.md` also says the Inter license is missing although it is tracked. | Reconcile current status and operational docs with the verified tree; retain old dated evidence as history but label superseded interim status. Current commands/counts/URLs must be accurate. | Phase 4, with the most misleading plan status corrected in Phase 0. Verify links, `rg` for obsolete current instructions, and final command output. |
| Q-10 / P2 | `frontend/src/app/styles.css` is 3,766 lines. The standards document notes a substantial legacy cascade; hard-coded non-token literals remain in Overview, run badges, shadows and React Flow variables. | While extracting Q-02, remove superseded/duplicate touched selectors and map safe literals to existing semantic tokens. Do not split the single authored stylesheet or attempt a wholesale cascade rewrite. | Phase 2. Visual regression risk is high because unlayered rules outrank utilities. Verify computed layout at representative routes, detector, screenshots and all frontend gates. |
| Q-11 / P3 | Backend tests pass with a Starlette `TestClient` reference to AnyIO's deprecated `BlockingPortal` alias (`starlette==0.47.3`, `anyio==4.15.1`). | Investigate the smallest compatible pinned FastAPI/Starlette update. Upgrade only if official compatibility and the full suite are clean; otherwise record the upstream warning as deferred instead of suppressing it. | Phase 4. Dependency-lock churn and transitive RAGAS compatibility are risks. Verify frozen lock export, Ruff and full PostgreSQL suite. |
| Q-12 / P1 deferred boundary | The application intentionally has no authentication/project authorization, deletion/retention API or verified public deployment. Live S3/Notion/Confluence/model checks require credentials and can incur external cost. Evidence: `README.md`, `docs/deployment.md`, AGENTS release sequence. | Do not broaden this quality pass into roadmap work or paid calls. Keep ports loopback-only, keep connection routes disabled by default, document retained artifacts/orphan inspection, and state that the product is not verified production-ready for shared use. | Explicitly deferred: requires product architecture, identity/data-ownership decisions and user-authorized credentials/cost. Verify documentation and loopback Compose bindings only. |

Positive findings to preserve: project-scoped service queries and composite database
constraints are exercised by integration tests; published indexes are fenced and atomic;
provider HTTP clients have bounded timeouts and redirects disabled where applicable;
Website fetching has an explicit SSRF-safe transport; connection secrets use
AES-256-GCM with project/connection/type AAD and redacted reads; frontend API errors do
not echo request bodies; polling generally fences stale responses; semantic tokens,
mobile stacking, focus rings, loading/empty/error states and evidence provenance are
well established.

### Implementation phases

#### Phase 1 — correctness and release hygiene

Status: **Complete on 2026-09-23.** Addressed Q-05, Q-07 and Q-08. Q-06 was
closed as an audit false positive after the clean source showed a normal JSX closing
delimiter rather than rendered text.

Implemented:

- The shared button primitive now defaults real buttons to `type="button"` while
  preserving Radix `asChild` behavior. The three implicit submit actions in experiment
  creation and snapshot index construction are explicit, and a regression proves that
  secondary form actions cannot submit their parent form.
- Restored the supported React Flow attribution instead of hiding it without a recorded
  Pro entitlement. The focused browser journey now requires the attribution to remain
  visible; desktop/mobile inspection found no overlap or horizontal overflow and the
  browser console contains no React Flow attribution warning.
- Standardized Vite, Compose, Playwright defaults, backend CORS and current README
  commands on `http://127.0.0.1:5273`. Vite uses a strict canonical port and a
  server-only `API_PROXY_TARGET` for isolated test APIs. Browser-stack instructions no
  longer start the nginx frontend beside Vite.
- Corrected stale ingestion browser assertions to the released Website action language.
  A bounded desktop toolbar row keeps exact canvas geometry stable across source-form
  variants and connector-kind changes without affecting stacked mobile behavior.

Verification:

- Frontend Prettier, structure/ESLint, strict TypeScript, **89 Vitest tests across 25
  files**, and the production build passed. The known 659.94 kB entry-chunk advisory is
  unchanged and remains Phase 2 work. The Impeccable detector returned no findings.
- Focused Chromium verification passed **10 ingestion editor journeys** in one worker,
  covering desktop, tablet, 390 px mobile, keyboard stage access, save/discard, errors,
  validation, node checkpoints and restored attribution. Agent Browser confirmed 390 px
  document width, a visible attribution link and no application warning in the console.
- Backend CORS coverage passed (**13 passed, 6 database-dependent skips**) with the
  known upstream Starlette/AnyIO deprecation warning. Both normal and browser Compose
  configurations rendered successfully with placeholder local credentials.
- An initial combined browser command accidentally included a project-kind journey
  against the already-running local development API and created clearly test-named
  project rows. No persistent data was deleted or reset; subsequent browser checks used
  request-mocked journeys or read-only inspection. This does not affect application
  behavior but remains an operator cleanup limitation because the current product has
  no deletion API.

#### Phase 2 — frontend ownership and loading performance

Status: **Complete on 2026-09-23.** Addressed Q-01, Q-02 and the bounded Q-10
cleanup without changing editor behavior or adding dependencies.

Implemented:

- Every workspace feature route now loads through `React.lazy` behind one accessible
  `role="status"` Suspense boundary. Direct hash-route dispatch remains centralized in
  `WorkspacePage`; no route-specific loading state leaked into feature ownership.
- Reduced `IngestionPipelineEditor.tsx` from 2,464 to 1,117 lines. Connector forms now
  live in `components/SourceSettings.tsx`, graph presentation and React Flow policy in
  `components/IngestionPipelineCanvas.tsx`, node configuration in
  `components/IngestionNodeSettings.tsx`, preview/run presentation in
  `components/IngestionResults.tsx`, and pure defaults/draft/presentation logic in
  `editorModel.ts`. The stateful request lifecycle remains in the editor because its load,
  unsaved guard, preview, run, schedule and fenced-poll state form one controller;
  splitting it further would create pass-through wrappers rather than clearer ownership.
- Consolidated repeated touched React Flow/workflow selectors and replaced the remaining
  non-token surface, status, shadow, canvas-dot and edge literals with semantic tokens or
  `color-mix`. The single authored stylesheet and incumbent visual language are preserved.

Verification:

- Frontend Prettier, structure/ESLint, strict TypeScript, **92 Vitest tests across 26
  files**, and the production build passed. Route splitting reduced the former 659.94 kB
  entry bundle to a 180.74 kB entry plus bounded feature/vendor chunks; the largest is
  241.37 kB and Vite emits no size advisory.
- All **10 focused Chromium ingestion-layout journeys** passed in one worker after the
  final CSS change, covering desktop, tablet, 390 px mobile, exact canvas geometry,
  accessible node settings, save/discard, validation, polling checkpoints and direct
  reload restoration. A broader first command had one transient checkpoint timing miss;
  the journey then passed alone and again in the complete focused file.
- Desktop and 390 px screenshots were reviewed in one bounded pass: settings remain
  reachable, node status is legible, attribution does not overlap controls, and neither
  layout has page-level horizontal overflow. Static Impeccable detection reported only
  the two previously documented Inter warnings, which remain false positives against
  the product's explicit self-hosted typography decision. URL-mode detection was not
  used because its optional Puppeteer dependency is not installed; Playwright supplied
  the rendered-browser coverage instead.

#### Phase 3 — backend ingestion cohesion

Status: **Complete on 2026-09-23.** Addressed Q-03 and Q-04 without changing connector
contracts, persistence schemas or infrastructure.

Implemented:

- Added one application-owned immutable source-artifact persistence boundary for
  Website, S3, Notion and Confluence. It owns the repeated source identity/revision,
  artifact, document, synthetic processing-run, chunk and cleanup transaction, while
  connector callbacks retain exact extraction, processing hashes, media types and
  provenance.
- Reduced `app/workers/ingestion.py` from 989 to 277 lines by moving remote discovery
  and publication advancement to `app/workers/remote_ingestion.py`. An explicit
  supported-kind strategy map replaces the prior conditional dispatch; Website stored
  snapshots remain a distinct path and the main worker still owns claim/fencing,
  Existing Files, embedding checkpoints and terminal lifecycle.

Verification:

- Backend Ruff lint and format checks, bytecode compilation and the local dependency
  suite passed (**140 passed, 118 skipped**; skips require the isolated database).
- A fresh isolated PostgreSQL/pgvector Compose run migrated to head and passed the
  complete backend suite: **253 passed, 4 skipped**. Connector persistence, incremental
  refresh, source snapshots, cancellation, stale recovery and atomic publication are
  included. The only warning is the tracked Starlette/AnyIO deprecation addressed in
  Phase 4.
- The complete deterministic Chromium connector coverage remains part of the final
  Phase 4 gate so it runs once against the final combined tree.

#### Phase 4 — documentation, dependency decision and final verification

Status: **Complete on 2026-09-23.** Q-09 documentation reconciliation is implemented.
For Q-11, the dependency change is deferred: AnyIO 4.15 deprecated the alias used by
Starlette's `TestClient`, and the upstream report reproduces the warning even with Starlette 1.6.0,
the latest release available during this review. The fix is merged upstream but is not
yet in a Starlette release, so a broad FastAPI/Starlette upgrade would add compatibility
risk without removing the warning. The warning is not suppressed and should be
revisited after a fixed Starlette release is supported by FastAPI. References:
[Starlette issue 3497](https://github.com/Kludex/starlette/issues/3497),
[FastAPI version guidance](https://fastapi.tiangolo.com/deployment/versions/).

Final regression work also corrected two issues exposed only by broad execution:

- Concurrent document workers now serialize shared ingestion-node transitions by
  locking the ordered node set. A database regression proves repeated Extract, Clean
  and Chunk callbacks advance monotonically instead of risking a transaction
  serialization failure or regressing visible state.
- The ingestion editor fetches terminal run items and schedule metadata before
  publishing the terminal run state, so effect cleanup cannot discard those final
  reads. Deterministic connector fixtures now patch the refactored remote worker, and
  browser assertions use the released navigation, schedule and status semantics.

Verification:

- Frontend Prettier, structure/ESLint, strict TypeScript, **92 Vitest tests across 26
  files**, and the production build passed. The entry remains 180.74 kB and the largest
  feature/vendor chunk 241.37 kB; Vite reports no size advisory.
- Backend Ruff lint/format, bytecode compilation and the local suite passed (**140
  passed, 118 skipped**). A fresh isolated PostgreSQL/pgvector stack migrated to head
  and passed **254 tests with 4 opt-in live-provider tests skipped**. The only warning
  is the intentionally unsuppressed upstream Starlette/AnyIO deprecation above.
- The complete deterministic Chromium suite passed in one uninterrupted, single-worker
  run against canonical Vite and a fresh isolated API: **28 passed, 1 intentionally
  skipped credential-free variant**. It covered all four remote connector fixtures,
  Existing Files, documents/PDFs, indexing/retrieval, answer pipelines, experiments,
  routing, responsive layout, accessibility state, cancellation and recovery. No live
  provider or paid-model request was made. The skipped missing-credentials journey then
  passed separately against a second fresh credential-free stack (**1 passed**).
- `git diff --check` and the final source/status review passed before the phase commit.

Remaining limitations: authentication and server-side project authorization, deletion
and retention behavior, public deployment, and credentialed live-provider validation
remain outside this pass. The application is therefore **not verified production-ready
for shared access**. An early browser command was accidentally proxied to the existing
developer API and left clearly test-named rows there; no data was deleted or reset
because the product has no deletion API. Final browser verification used an empty,
isolated database.

Recommended next action: design authentication/authorization and retention ownership
before any shared deployment, then run separately authorized bounded live-provider
checks. Revisit Q-11 when FastAPI supports a Starlette release containing the upstream
warning fix.


## Source snapshots and reusable index variants — implementation started 2026-09-22

Historical interim status after Slice 2. All five slices were subsequently completed
and verified; the authoritative completion record appears under **Reusable Website
snapshots — Slice 5 complete** below.

- Slice 1 adds migration `0018`, immutable project-scoped Website source snapshots,
  exact source-item/revision membership, collecting/ready/failed/cancelled states,
  links from ingestion runs and indexes, conservative historical backfill, and
  paginated snapshot/detail/item/downstream-index reads. Snapshot APIs expose only
  safe source identity summaries; full stored source configuration remains server-side.
- Verified on an isolated PostgreSQL/pgvector database: clean upgrade through head,
  Alembic model drift check, and eight Website ingestion tests covering exact
  membership, pagination, project isolation, immutable API behavior,
  ready/failed/cancelled states, index linkage, stored-artifact compatibility and a
  populated `0017 → 0018` backfill that preserved both index IDs and inherited only
  proven lineage. Complete backend Ruff formatting/lint and whitespace checks pass.
- Slice 2 adds the discriminated refresh/snapshot execution input, a temporary
  `reuse_stored` compatibility adapter, explicit existing/new destination choices,
  authoritative project/status/source-configuration validation, and an offline
  worker path that reads only immutable snapshot membership and never constructs a
  Website connector. Independent destinations retain normal atomic index publication,
  fencing, cancellation, embedding reuse, and cost metadata behavior.
- Verified against the rebuilt backend image on an isolated PostgreSQL/pgvector
  database: 32 Website, Existing Files, scheduling and contract tests pass. Coverage
  includes independently named destinations, different chunk settings, compatible
  vector reuse, a connector factory that fails if called, ready/config/project and
  destination validation, legacy request compatibility, cancellation and existing
  ingestion regressions. Backend Ruff format/lint and whitespace checks also pass.
- The snapshot-build API is complete, but the Knowledge Base does not expose its
  user workflow yet. That is the Slice 3 boundary.

The next scoped ingestion improvement is documented in [Source snapshots and reusable index variants](source-snapshot-index-variants-plan.md). It covers one Website collection producing an immutable source snapshot, multiple independently named index families built from that snapshot, clear Knowledge Base lineage, exact-index answer-pipeline handoff, and same-snapshot experiment comparison.

This plan does not authorize implementation by itself. It explicitly excludes new connectors, arbitrary graph branching, per-pipeline embedding-provider selection, automatic configuration search, new evaluation metrics, schedule redesign, and snapshot deletion/retention UI.

## Desktop canvas position correction — 2026-09-22

This supersedes the natural-document-scroll desktop design described below. Reproduced an 87px canvas jump when switching from a deeply scrolled Website inspector to Extract: the shorter document clamped window scroll even though graph dimensions and zoom were unchanged.

The desktop editor now occupies a stable viewport-height workspace with a compact heading, anchored stage navigation and an independently scrolling right inspector. Selecting a node resets inspector scroll, not document scroll. Schedules stay beneath settings in that inspector; validation also stays inside settings so changing source type cannot resize the canvas. Tablet/mobile retain stacked document scrolling.

Verification: Agent Browser clicked all six nodes on the user's saved version at 1440×900. Canvas bounds remained x232/y294/848×605, document height 900 and graph transform identical across all stages, including after inspector scrolling. Eight isolated browser tests pass, now explicitly checking screen position and document scroll as well as dimensions/zoom. Frontend lint, TypeScript and production build pass; the existing bundle-size advisory remains. No live ingestion, saved configuration or schedule was changed.

## Ingestion schedule placement — 2026-09-22

Moved saved-version schedules from the full-width footer into the right-hand inspector immediately below stage settings. Both sections share aligned padding; schedule inputs and the create action stack to the panel width. Existing schedule rows wrap their actions within the inspector. The mobile layout keeps the same settings-then-schedules reading order and normal page scrolling.

Verification: Agent Browser checked the user's saved Website pipeline at 1920×1080 and 390×844; schedule and inspector edges align, and mobile has no horizontal overflow. TypeScript, lint and all eight ingestion browser regression tests passed, including a new desktop placement/mobile overflow assertion. No schedule was created or enabled during the live visual check.

## Ingestion UI follow-up after user rejection — 2026-09-22

The earlier nested-inspector implementation and its narrow verification were insufficient. This follow-up supersedes that scrolling design.

- The ingestion editor now uses normal document scrolling for all settings. The desktop canvas has an explicit viewport-based height independent of form content and stays beside the form while scrolling. Tablet layouts (up to 1100px) stack instead of squeezing a graph beside a 360px inspector.
- Selecting a stage brings its heading into view, including after scrolling to the bottom of expanded source settings. Mobile stage selection goes directly to the settings. Graph geometry remains independent of source form variants and stage content.
- Removed the unconditional delayed observer refit; initial fitting belongs to React Flow, and subsequent fitting only responds to an actual canvas dimension change. Tests wait for explicit Fit View completion before checking preservation of the user's view.
- Added field-level chunk bounds/accessibility hints, automatic navigation to newly started preview/run feedback, and focus on actionable request failures.
- Agent Browser walkthrough used the exact user-provided saved version (`fde11169-cc8f-427c-b717-3b86848e09e9`): expanded source settings, wheel scrolling to the last field, stage changes after deep scrolling, zoom, panning, invalid chunk editing/discard, saved-version switching, desktop/tablet/mobile inspection. No saved project data or paid execution was changed by this walkthrough.
- Eight isolated browser tests cover real wheel scrolling, stage heading visibility, node clicks, graph geometry/view preservation, all website discovery modes, empty existing-file selection, tablet/mobile layout, edits/discard, preview cancellation/error feedback and initial configuration failure. API fixtures are isolated from developer data and providers.

Verification and runtime handoff: frontend formatting, lint, TypeScript, 78 Vitest tests and production build passed. All eight browser tests also passed against the rebuilt frontend on port 5173. Agent Browser confirmed the exact saved URL loads bundle `index-C5YvKYUw.js`, the expanded source form scrolls normally (document scroll 1147px, no inspector clipping), and the graph stays 588px tall at 1366×768. Follow-up screenshots are in `test-results/ingestion-ui-followup/`. The existing bundle-size advisory remains; these UI checks do not certify live provider behavior or shared deployment security.

## Ingestion editor layout and scrolling — 2026-09-21

Acceptance criteria: stage selection must preserve canvas size and user zoom; long source forms and below-canvas schedules must remain scrollable; every stage must be keyboard-selectable; desktop/mobile layouts must avoid overlap and horizontal overflow; saved versions, validation and execution actions must retain their existing API behavior.

Status: complete for the requested ingestion UI improvement.

- Bounded the canvas independently of inspector content, replacing content-driven resizing (Website previously expanded the graph to 1,400px). Wheel scrolling over the graph now scrolls the page; explicit zoom controls and pinch zoom remain available.
- Added an accessible six-stage navigator, persistent inspector heading and independently scrolling desktop fields. Mobile uses a stacked canvas/settings layout and normal page scrolling. Removed the inherited mobile canvas margin responsible for overlapping settings.
- Grouped pipeline identity/version separately from actions, retained the charcoal/lavender design system, added explicit discard for saved drafts, and grouped website scope/fetch limits in an expandable section. Extract, Clean and Embed now expose actual recorded configuration rather than a generic placeholder.
- Corrected failed initial loading so missing embedding configuration displays the actionable error and retry control.
- Applied stable desktop canvas sizing and non-overlapping mobile stacking to the answer editor as well. Its existing explicit node-centering behavior is preserved; all five stages measured 660px high at 1440×900. Wheel scrolling over either editor no longer traps page scrolling.
- Verification: lint, strict TypeScript, 78 Vitest tests, production build and four isolated Playwright UI regression tests passed. Browser fixtures intercept API requests and do not write developer data or execute providers. Agent Browser verified the live saved pipeline at desktop/mobile sizes; all six stages retained the same 539px canvas and identical viewport transform at 1440×900. Checked 390px, 768px and 1280px widths for horizontal overflow and confirmed mobile canvas/settings boundaries no longer overlap. Captures are in `test-results/ingestion-ui/`.
- Remaining limitations: the existing large-bundle build advisory remains. This UI verification does not certify shared deployment security or live connector/provider reliability. No source fetch, embedding run or schedule was started during the browser review.

Next step: use the rebuilt local frontend at http://localhost:5173 and review the existing ingestion pipeline with the new stage navigation.

## Knowledge Base and RAG configuration correction — 2026-09-14

Status: complete.

- Replaced the flat index-history page with a responsive knowledge-set catalog and adjacent index inspector. The selected immutable version exposes real paginated pgvector records, passage text, source provenance, vector dimensions/norm and a bounded value preview, followed by a retrieval-only check.
- Diagnosed the manual acceptance pipeline's incorrect answers: saved version 1 targeted an obsolete one-passage index while the current website ingestion index contained 2,987 passages. The editor and Playground now warn on this exact mismatch and can move a draft to the current index; new pipelines preselect the newest current-ready index.
- Website source entry now begins empty and infers allowed origins from valid entered URLs, avoiding the prior `example.com` scope mismatch. Chunk settings add explicit recall/noise/cost guidance and editable precise, balanced and broad-context presets.
- Added a distinct **Reprocess stored pages** action for Website pipelines. After saving changed chunk settings, it uses the current index's stored immutable page artifacts without constructing the Website connector or making another network scrape, then publishes a new versioned index. A normal **Refresh website & run** remains separate. Re-embedding the new chunks can still incur provider cost.
- Corrected the website chunker itself: adjacent HTML elements are now joined before character-window chunking, rather than embedding fragments such as “Create agents” independently. Heading provenance and deterministic offsets remain inspectable. Playground results now surface index version, supplied-passage count, citation-link count and stage-aware failure guidance.
- Created `Manual orchard answers` version 2 against `Ingested knowledge` version 3 and verified a grounded answer with a real local configured provider call and cited evidence.

Live correction follow-up: saved Website ingestion version 2 at `1000` characters / `120` overlap and reprocessed all 43 stored pages without a network refresh. `Ingested knowledge` version 4 published successfully with 284/284 meaningful passages, replacing the prior current version's 2,987 mostly element-sized fragments. Saved answer pipeline version 3 against index version 4 with Top k 10. Live Playground checks answered both “How do I create an agent?” and “Give me a template of an agent.”; the latter returned a structured template with evidence links S1, S3 and S4. Transient OpenRouter retrieval/generation timeouts were retained as explicit failed runs and succeeded on manual retry.

Verification: backend Ruff, focused offline-reprocessing checks and the complete isolated PostgreSQL/pgvector suite passed (**250 passed, 4 opt-in live checks skipped**). Frontend formatting, lint, strict TypeScript, **78 Vitest tests** and production build passed. Agent Browser verified the real index catalog/vector inspector, stale-index correction, stored-page reprocessing, meaningful version-4 retrieval, saved answer pipeline version 3, cited agent instructions/template, the inline quality check and responsive layouts. The existing Vite bundle-size advisory remains.

## Ingestion pipelines — Phase 9 acceptance criteria

Recorded before implementation on 2026-09-14:

- Verify a clean migration to head, model/schema drift, the supported populated lexical downgrade/upgrade path, and forward upgrade from the pre-schedule schema with existing application rows. Confirm guarded connector downgrade boundaries rather than deleting immutable evidence.
- Run backend Ruff format/lint and the full isolated PostgreSQL/pgvector suite; run frontend Prettier, structure/ESLint, strict TypeScript, unit tests and production build.
- Run the complete isolated Chromium suite, including existing-files and website ingestion plus every released S3, Notion and Confluence connector journey and answer/Playground/experiment regressions. Make no live provider or paid-model calls without explicit authorization.
- Inspect representative desktop and mobile states once, correct verified regressions in one bounded pass, and confirm the corrected states once.
- Reconcile README, architecture, development, deployment and implementation status with actual verification results, operational procedures and remaining limitations. Do not claim production readiness while shared-access authentication/authorization and live connector verification remain incomplete.
- A final finish review must return PASS, all temporary Phase 8/9 Docker resources must be removed without touching the user's persistent application stack, and the completed phase must be committed and pushed to `main`.

Status: complete for ingestion-pipeline Phase 9. Verified on 2026-09-14.

Implemented and hardened:

- Reconciled the public documentation with the released Existing Files, Website, S3, Notion, Confluence, encrypted connection-vault and scheduling behavior. The local-only security boundary, immutable history, backup/keyring requirements and unsupported shared deployment remain explicit.
- Replaced ingestion-run polling with a run-ID-scoped sequential loop. A prior request cannot overwrite a newer manual or scheduled run, transient read failures retry, and terminal item/schedule refreshes ignore results after navigation.
- Experiment comparison polling now also recovers after transient HTTP failures instead of leaving a completed PostgreSQL job displayed as queued. Browser isolation pauses its created schedule, and the pipeline journey verifies dirty/discard behavior without timing-sensitive pointer dragging.

Verification:

- A fresh PostgreSQL/pgvector database migrated to head with no model drift. The populated lexical downgrade/upgrade path passed, and upgrading from pre-schedule revision `0016` retained an existing answer project, pipeline and immutable version before `alembic check` reported no operations. Connector migrations continue to refuse destructive downgrades when immutable connector evidence exists.
- Backend Ruff lint/format and compile checks passed. The full isolated suite passed **248 tests**, with **4 opt-in live-provider checks skipped** because no live source or paid-call authorization was supplied.
- Frontend Prettier, structure/ESLint, strict TypeScript, **78 Vitest tests across 23 files**, and the production build passed. The build retains the known non-blocking approximately 633 kB minified chunk advisory.
- The clean deterministic-provider Chromium stack passed **16 journeys with 1 credential-free scenario intentionally skipped**, and the full two-version experiment journey passed separately in **2.2 minutes**. A separate credential-free stack passed the missing-embedding-credentials journey. Together these cover all 18 browser journeys without live-provider traffic.
- Desktop/mobile Knowledge Base, connection-vault, Confluence schedule/refresh and experiment comparison/evidence states were inspected. The final captures had no blocking overflow, hierarchy, accessibility or inert-control finding.
- Final finish review returned **PASS** after the polling and test-isolation corrections. Temporary Phase 8/9 Docker resources were removed without touching the persistent local application stack.

Remaining limitations: this is a loopback-only unauthenticated workspace, not a shared/public deployment. S3, Notion and Confluence have deterministic complete integration coverage but no user-authorized live verification in this phase. Daily schedules are API-only; schedules and immutable history have no delete endpoint or automatic retention. Browser-test provider doubles do not establish real-provider availability or answer quality.

Next actionable step: add authentication and server-side project authorization before any shared deployment, then perform individually authorized bounded live connector checks where required. The ingestion plan itself has no remaining phase.

## Ingestion pipelines — Phase 8 acceptance criteria

Recorded before implementation on 2026-09-13:

- Add disabled-by-default, project-scoped persisted schedules that reference one immutable ingestion pipeline version and expose timezone-aware cadence, enabled/paused state, next due time, last run/outcome and safe operational error metadata.
- Schedule dispatch is durable across restarts and duplicate delivery. PostgreSQL locking/fencing advances due time transactionally and creates at most one active run per destination; due schedules never overlap queued/running manual or scheduled destination runs.
- Preserve manual runs. Users can create, edit, pause/resume and trigger schedules through authoritative APIs and accessible frontend controls; reject invalid, cross-project, answer-pipeline, deleted-version and unsafe cadence requests.
- Coalesce missed intervals, recover stale claims and prove overlap prevention, cancellation and failure recovery. Partial indexes never publish and failures never silently disable a schedule.
- Document rate limits, storage growth, backup/restore, retention/deletion and AES-256-GCM rotation. Clean backend/frontend/browser gates and finish review must pass before completion.

Status: complete for ingestion-pipeline Phase 8. Verified on 2026-09-14.

Implemented:

- Migration `0017` adds project-scoped schedules bound to one immutable ingestion version, interval or timezone-aware daily cadence, paused/enabled state, next/last execution metadata and composite project/run constraints. New schedules start paused.
- The PostgreSQL dispatcher uses bounded `SKIP LOCKED` claims, stale-claim recovery and exact schedule/run identity. It coalesces missed time, adopts runs created before an interrupted checkpoint, prevents destination overlap, classifies safe failures, and preserves concurrent pause/cadence edits.
- Project-scoped APIs and accessible editor controls create, edit, pause, enable and run schedules. Credentialed sources retain loopback/vault protection, manual ingestion remains unchanged, and run records identify manual versus scheduled triggers without exposing credentials.
- Operations documentation covers provider-rate planning, process restart behavior, storage growth, coordinated PostgreSQL/artifact/keyring backups, AES-256-GCM key rotation, pause behavior and the absence of automatic historical deletion.

Verification:

- Fresh PostgreSQL/pgvector migration and Alembic model check passed. Backend Ruff/format passed; the full suite passed with **248 tests and 4 explicitly gated live-provider checks skipped**.
- Frontend Prettier, structure/ESLint, strict TypeScript, **77 Vitest tests across 22 files**, and production build passed; the known non-blocking approximately 633 kB bundle advisory remains.
- Isolated Chromium created a paused schedule, enabled it, ran its exact saved Confluence version, refreshed incrementally, published exact index v2 and answered from that index. Desktop/mobile inspection found no blocking overflow, accessibility or hierarchy regression.
- Finish review found answer-version validation, non-HTTP failure recovery, post-commit adoption and concurrent edit races; regression-tested fixes were applied and repeated review returned **PASS**. No live provider or paid-model request was made.

Remaining limits: the editor authors fixed-interval schedules; timezone-aware daily schedules are API-only. Schedules are retained with their immutable history and have no delete endpoint or automatic retention policy. Shared-access authorization remains a release prerequisite.

Next actionable step: Phase 9 performs the final clean/upgrade-path, full browser, visual and documentation hardening pass without adding features.

## Ingestion pipelines — Phase 7C acceptance criteria

Recorded before implementation on 2026-09-13:

- Implement the current official Confluence Cloud REST API v2 contract through the pinned HTTP client. Construct clients only from decrypted project-scoped connections, require canonical HTTPS `*.atlassian.net` sites, send preemptive email/API-token Basic authentication only to that origin, revalidate redirects/DNS, and enforce bounded requests, timeouts, retries, rate-limit delays, and fixed sanitized errors.
- Add a strict Confluence source configuration containing only an opaque connection ID, explicit space/page selection, optional title/label filters, and page/request/body/time limits. Authoritative pipeline validation rejects missing, disabled, wrong-kind, and cross-project connections; credentials never enter graph JSON, snapshots, URLs, logs, responses, DOM, or browser storage.
- Connection testing uses a bounded read-only API call. Cursor-paginated space/page discovery has stable ordering, exact inclusion/exclusion reasons, and hard limits. Page ID is the stable source identity; page version number/creation time are the provider revision, with space, parent, status, web location, and version metadata preserved.
- Fetch requests one exact current page with an explicit body representation, rejects revision changes between discovery and fetch, converts Confluence storage content deterministically to inert text without executing macros/scripts/embeds, and retains page/section hierarchy through artifact, revision, chunk, index, and retrieval provenance.
- Preview and durable fenced ingestion support first publication, compatible unchanged reuse without body fetch/embedding, new/changed/deleted-or-no-longer-visible classification, exact replacement membership, cancellation/stale/duplicate delivery, and permission-loss failure while preserving every earlier ready index and the current-ready pointer.
- The ingestion editor exposes Confluence only when the encrypted local vault and real adapter are enabled. Users select a redacted connection, configure scope/filters/bounds, run real preview/execution, and inspect paginated provenance and refresh outcomes accessibly on desktop/mobile.
- Deterministic doubles cover authentication, cursor pagination, filters, bounds, extraction, concurrent changes, first/refresh runs, removal, permission loss, isolation, retrieval, cancellation, stale recovery, and duplicate delivery. A separate opt-in bounded live check is disabled unless a user-authorized site/space or page is explicit.
- Fresh migration/full backend and frontend gates, isolated Chromium ingestion/answer regressions, desktop/mobile inspection, and the required finish review must pass before Phase 7C is marked complete and pushed.

Status: complete for ingestion-pipeline Phase 7C. Verified on 2026-09-13.

Implemented:

- Added a real read-only Confluence Cloud REST API v2 adapter through pinned `httpx==0.28.1`. Root HTTPS `*.atlassian.net` validation, public-DNS checks, disabled redirects, single-origin Basic email/API-token authentication, streamed response bounds, shared request budgets, bounded retries and sanitized errors protect decrypted AES-256-GCM values.
- Strict configuration supports site, numeric space or numeric page selection, title-prefix and label filters, and explicit limits. Page ID plus version number/timestamp provide stable identity/revision semantics; deterministic storage-body extraction retains page/space/parent/status/version, element ordinal and heading provenance without executing markup.
- Migration `0016` adds Confluence source/document kinds and refuses unsafe downgrade. Preview and fenced ingestion resolve only project-owned connection IDs, check cancellation before every provider request, avoid unchanged body/embedding work, report exact refresh outcomes and preserve prior ready indexes after failure.
- The editor provides accessible Confluence connection, scope, filter and bound settings, real preview/run inspectors and responsive desktop/mobile layouts. A bounded one-page live check remains disabled without explicit authorization.

Verification:

- Backend Ruff passed. Fresh PostgreSQL/pgvector migrations and full suite: **240 passed, 4 skipped**; only explicitly gated live Confluence, Notion, S3 and embedding checks skipped.
- Frontend Prettier, structure/ESLint, strict TypeScript, **76 Vitest tests across 22 files**, and production build passed; the known non-blocking approximately 629 kB bundle advisory remains.
- Isolated Chromium Confluence first/refresh publication, exact-index answering and responsive checks passed, as did nine connector/ingestion/pipeline/Playground/experiment regressions after one stale pre-S3 assertion was corrected.
- Finish review found request-budget, early-page-bound and cancellation gaps; these were fixed with regression tests and repeated review returned **PASS**. No live Atlassian or paid-model request was made.

Remaining limits: only Confluence Cloud `*.atlassian.net` REST v2 is supported; attachments, comments, whiteboards and rendered macro/embed expansion are not fetched. Basic API-token authentication remains loopback-only; OAuth and authenticated multi-user authorization remain future work. Historical artifacts have no automatic retention deletion.

Next actionable step: Phase 8 adds disabled-by-default durable schedules and operational controls without changing manual refresh or atomic publication behavior.

## Ingestion pipelines — Phase 7B acceptance criteria

Recorded before implementation on 2026-09-13:

- Pin a compatible official Notion client/API contract and construct provider clients only from decrypted project-scoped Notion connections. Requests use an explicit Notion version, bounded timeouts/retries and fixed safe authentication, permission, throttling, timeout and provider error mappings.
- Add a strict Notion source configuration containing only an opaque connection ID, bounded page/database selection filters and page/request/block/text limits. Saved versions, previews, runs, responses, logs, routes and browser storage never contain the integration token; authoritative validation rejects missing, wrong-kind and cross-project connections.
- Paginated discovery supports explicitly shared pages and selected databases/data sources with stable ordering, bounded cursors and inspectable inclusion/exclusion. Stable identity uses the Notion page ID; provider revision uses the page's last-edited time plus available immutable identifiers.
- Fetch traverses page block children with bounded pagination and depth, converts supported rich-text blocks deterministically without executing embeds or instructions, records page/database/block hierarchy provenance and rejects content that changes outside the discovered revision contract.
- Preview and durable ingestion use the existing fenced job paths. First ingestion publishes an exact immutable index; refresh embeds only new/changed pages, reuses compatible unchanged revisions/vectors, reports archived, deleted or no-longer-shared pages as removed, and leaves the prior current-ready index unchanged after required failures or permission loss.
- The ingestion editor exposes Notion only when the encrypted connection vault and real adapter are enabled. Users select a redacted connection, configure explicit selection and bounds, run real async preview/execution, and inspect paginated provenance and new/changed/unchanged/removed/failed outcomes on desktop/mobile.
- Deterministic provider doubles cover connection validation, cursor pagination, page/database filters, bounded nested blocks, rich-text extraction, first run, incremental refresh/removal, permission loss, cancellation, stale recovery, duplicate delivery, isolation and retrieval. A separate opt-in live check remains disabled unless a user-authorized workspace/page is explicitly configured.
- Clean/upgrade migrations, full backend/frontend gates, isolated Chromium ingestion and answer regressions, desktop/mobile inspection and the required finish review pass before Phase 7B is marked complete and pushed.

Status: complete for ingestion-pipeline Phase 7B. Verified on 2026-09-13.

Implemented:

- Added the real Notion REST adapter using the explicit official `2026-03-11` contract through pinned `httpx==0.28.1`. Project-scoped AES-256-GCM connections are decrypted only inside connection-test, preview, and worker calls; request counts, timeouts, retries, rate-limit delays, and safe provider errors are bounded.
- Strict source configuration supports shared-workspace, explicit page UUID, and data-source UUID selection plus page/API-request/block/depth/text/time limits. Discovery is cursor-paginated and stable, page UUID and last-edited revision identities are preserved, and trash/duplicate/failure outcomes remain inspectable.
- Recursive block extraction converts supported rich text, headings, lists, tasks, quotes, equations, child titles, and table rows to inert text. Page/block/type/depth/section and official API-version provenance flows through immutable artifacts, revisions, chunks, run items, index membership, and retrieval evidence. A final page read rejects concurrent revision changes.
- Migration `0015` adds Notion document/source kinds and refuses downgrade while Notion history exists. The fenced remote coordinator now shares safe S3/Notion mechanics: unchanged compatible pages avoid block fetch and embedding, refresh reports new/changed/unchanged/removed, and permission/extraction/embedding failure cannot advance the current-ready index.
- The ingestion editor exposes Notion only with the encrypted local vault enabled, selects redacted connection IDs, edits discovery/budget settings, previews and runs real durable jobs, and displays exact refresh outcomes. The source and extraction nodes use connector-accurate labels, and resize-aware graph fitting keeps every node visible on mobile.
- Added deterministic connector, persistence, incremental refresh, provenance, isolation, permission-loss, retrieval, and Chromium fixtures plus a disabled-by-default one-page authorized live check. Production code never imports the deterministic transport.

Verification:

- Backend Ruff lint/format passed. Fresh isolated PostgreSQL/pgvector migration and full suite: **232 passed, 3 skipped**; the authorized Notion, S3, and live-embedding checks remained skipped because no credentials were supplied. Focused Notion connector tests additionally cover cursor pagination, request and nesting bounds, safe errors, stable revisions, and unchanged fetch avoidance.
- Frontend Prettier, structure/ESLint, strict TypeScript, **76 Vitest tests across 22 files**, and production build passed. The known non-blocking approximately 625 kB bundle advisory remains.
- Isolated Chromium Notion preview, first publication, incremental new/unchanged/removed refresh, exact index selection, and grounded answer passed. Website, S3, Existing Files, pipeline-kind/version, and answer regressions also passed (**6 browser tests**), followed by a final rebuilt Notion pass with explicit source-label and mobile node-bound assertions.
- Desktop/mobile captures were inspected. The required finish review found and then verified fixes for the incorrect source-node label and React Flow mobile recentering; final result: **PASS**. No live Notion or paid model call was made.

Remaining limits: the connector extracts supported Notion block text but does not download file/image embeds or execute synced/external content. Workspace search is limited to pages visible to the integration; explicit inaccessible pages fail safely instead of being inferred as removed. `last_edited_time` is Notion's available provider revision, so the worker rechecks it after extraction but cannot request an immutable historical page version. Historical artifacts/revisions have no automatic retention deletion. Credentialed connections remain restricted to the unauthenticated loopback workspace until real user authentication and project authorization exist.

Next actionable step: Phase 7C implements Confluence with the same complete connection, preview, bounded discovery/fetch, refresh/removal, provenance, and browser exit gate before it is exposed as available.

## Ingestion pipelines — Phase 7A acceptance criteria

Recorded before implementation on 2026-09-13:

- Pin a compatible Boto3 release and construct S3 clients only from decrypted project-scoped S3 connections. Clients use explicit region, bounded connect/read timeouts, standard bounded retries and no ambient credential fallback. Connection checks perform a real bounded S3 operation and map authentication, authorization, throttling, timeout and provider failures to fixed safe application errors.
- Add a strict S3 source-node configuration containing only an opaque connection ID, bucket, optional prefix, bounded object/page/byte limits, expected owner and an explicit TXT/PDF allowlist. Pipeline versions, preview/run snapshots, URLs, logs and responses never contain credentials; authoritative validation rejects missing, wrong-kind and cross-project connections.
- Discovery uses bounded `ListObjectsV2` pagination, stable key ordering and hard page/object limits. It rejects folder markers, unsupported extensions, oversized or unavailable storage-class objects with inspectable reasons and records stable identity from bucket/key plus provider revision from VersionId when available or ETag/size/last-modified otherwise.
- Fetch requests the exact discovered object revision where supported, streams no more than the configured per-object and total budgets, verifies provider metadata did not change between discovery and fetch, stores immutable artifacts under generated identities and carries bucket/key/version/ETag/size/last-modified provenance into source revisions, chunks and index membership.
- Preview, ingestion and refresh use the existing durable fenced job paths. First ingestion extracts supported TXT/text PDFs, cleans/chunks/embeds and atomically publishes an exact immutable index. Refresh reuses unchanged compatible revisions/vectors, embeds only new/changed objects, reports keys absent from the new listing as removed, preserves prior indexes and leaves the current-ready pointer unchanged after any required failure or permission loss.
- The ingestion editor exposes S3 only when connection management and the real adapter are enabled. Users select a redacted S3 connection, bucket, prefix, allowlist and bounds; run real async preview, inspect paginated inclusion/exclusion/provenance, save an immutable version, execute it and inspect new/changed/unchanged/removed/failed outcomes without secrets entering browser state.
- Deterministic provider doubles cover connection validation, pagination, prefix/allowlist/budget handling, versioned and unversioned identity, first run, incremental new/change/unchanged/removal, exact-version fetch, permission loss, cancellation, stale recovery, duplicate delivery, project isolation and answer retrieval from preserved versions. The opt-in live check remains disabled unless a user-authorized bucket is explicitly configured.
- Clean/upgrade migrations, full backend/frontend gates and isolated desktop/mobile Chromium journeys pass before Phase 7A is marked complete. Documentation records IAM permissions, bounds, versioning behavior, operational limits and exact verification performed.

Status: complete for ingestion-pipeline Phase 7A. Verified on 2026-09-13.

Implemented:

- Pinned Boto3 1.43.93 and added a real S3 tester/connector built only from decrypted, project-scoped AES-256-GCM connection values. Explicit regions, bounded timeouts/retries, safe provider errors and loopback-only credentialed preview/run entry points preserve the Phase 6 boundary.
- Added strict bucket/prefix/expected-owner/TXT-PDF/budget configuration, bounded paginated discovery, stable canonical keys, VersionId or ETag/size/modified revision mapping, exact conditional fetch and provider-change rejection. Preview items expose inclusion reasons and provider revisions.
- Migration `0014` adds S3 source/document support and processing-configuration-aware immutable revisions. S3 TXT and text-based PDF artifacts use generated storage names, deterministic extraction/clean/chunk processing and complete source/chunk/index provenance. Downgrade refuses to discard existing S3 history.
- Durable refresh classifies new, changed, unchanged and removed objects, reuses compatible revisions and vectors, avoids GET/embedding for unchanged content and atomically advances only a fully ready index. Permission loss, cancellation, stale recovery and duplicate delivery cannot replace the prior ready version.
- The ingestion editor exposes S3 only with the local encrypted vault enabled, selects redacted connection IDs, configures every bound, runs real preview/execution and renders paginated locations, provider revisions and refresh outcomes on desktop/mobile. No credential enters graph JSON, API reads, DOM summaries, routes or browser storage.
- Added a separately gated live S3 test that lists no more than five objects on one page and fetches one object up to 1 MB only when `RUN_LIVE_S3_AUTHORIZED=1` and an explicit authorized bucket/prefix credential set is provided.

Verification:

- Backend Ruff formatting/lint passed. Fresh isolated PostgreSQL/pgvector suite: **224 passed, 2 skipped**; the skips are the opt-in live embedding and authorized S3 checks. A final clean migration/schema/downgrade/upgrade pass after widening provider revisions added **19 passed**.
- Frontend Prettier, structure/ESLint, strict TypeScript, **76 Vitest tests across 22 files** and production build passed. The known non-blocking approximately 622 kB bundle advisory remains.
- Isolated deterministic Chromium S3 journey passed: encrypted connection reference, preview, first publication, incremental new/unchanged/removed refresh, exact version selection and grounded answer. Desktop/mobile screenshots were inspected with no page overflow. The finish review caught and resolved the saved-version select contrast issue; the rebuilt recapture passed.
- Existing Website, pipeline and Playground regressions passed four parallel journeys. The Existing Files journey completed after the parallel run's 120-second polling timeout and passed alone; the application run itself was durable and succeeded. No real AWS or paid provider call was made.

Remaining limits: only text-based PDFs are supported; scanned documents need OCR outside this phase. Glacier/Deep Archive objects require restoration. Unversioned buckets use an ETag precondition plus size/last-modified verification rather than immutable object versions. Historical artifacts/revisions have no automatic retention deletion. S3 credentials remain restricted to the unauthenticated loopback workspace until real user authentication and project authorization exist. The live S3 check was not run because no authorized bucket was supplied.

Next actionable step: Phase 7B implements Notion with the same complete connection, preview, bounded fetch, refresh, removal, provenance and browser exit gate before it is exposed as available.

## Ingestion pipelines — Phase 6 acceptance criteria

Recorded before implementation on 2026-09-13 after the user approved AES-256-GCM:

- Alembic adds project-scoped named source connections and append-only audit events. A connection stores only AES-256-GCM ciphertext, a unique 96-bit nonce, key version, schema version and intentionally redacted metadata; project/name/kind constraints and composite ownership keys reject cross-project references.
- Encryption uses a pinned maintained library, a freshly generated nonce per write and authenticated associated data binding schema/project/connection/kind. Versioned 32-byte keys and one active key come only from server environment configuration. Missing, malformed, unknown or unauthentic keys fail closed without exposing ciphertext, submitted credentials or cryptographic errors.
- Typed create and credential-rotation requests accept only the fields supported for S3, Notion or Confluence foundations. Redacted reads never return credential fields, ciphertext, nonce, authentication tag or encryption-key version. Rotation is transactional, changes the nonce/ciphertext and records safe audit metadata; master-key rewrap to the configured active version preserves the credential and is separately testable.
- Connection testing decrypts only inside the service boundary and invokes an application-owned tester interface. Production reports a clear unavailable state until that connector phase supplies its real adapter; deterministic doubles verify successful/failed checks and exception sanitization without presenting mock success in production.
- Connection endpoints are disabled without valid key configuration and are restricted to the local deployment boundary. Local Host/Origin checks and loopback-only Compose bindings prevent this unauthenticated application from enabling credential management on a shared/public origin; future shared deployment requires authenticated server-side project authorization.
- The Settings UI loads real project-scoped connection state, creates typed connections, selects one, tests it, rotates credentials and rewraps encryption without placing secret values in URLs, rendered copy, browser storage or pipeline versions. Submitted secret controls clear after every attempt and expose loading, unavailable, safe-error and empty states accessibly on desktop and mobile.
- Secret round-trip/tamper/AAD/key-version/unique-nonce tests, API redaction and raw-database scans, rotation/rewrap, cross-project isolation, safe audit/error tests, frontend DOM/storage/URL leakage checks, clean/upgrade migrations and isolated browser verification pass before Phase 6 is marked complete.

Status: complete for ingestion-pipeline Phase 6. Verified on 2026-09-13.

Implemented:

- Alembic `0013` adds project-scoped named source connections and append-only lifecycle events with composite ownership constraints. Credential payloads are stored only as AES-256-GCM ciphertext using fresh 96-bit nonces, authenticated project/connection/kind/schema context and an environment-supplied versioned 32-byte keyring.
- Typed S3, Notion and Confluence connection APIs create, list, read, test, rotate and rewrap credentials. Reads expose deliberately limited hints only; decryption and connector-tester invocation remain inside the service boundary, arbitrary provider errors are sanitized, and audit events contain no request bodies or credential values.
- Credential management is disabled by default and fails closed for absent, malformed, retired or unauthentic keys. The unauthenticated development application restricts the vault to loopback Host/Origin requests and loopback-bound Compose services; documentation explicitly requires authentication and project authorization before any shared deployment.
- Project Settings now provides a responsive connection vault with honest connector-unavailable behavior, accessible selection state, typed secret-entry forms and real create/test/rotate/rewrap API flows. Secret controls are cleared after every attempt and values never enter route state, browser storage, rendered summaries or response bodies.
- Deployment and development documentation now covers key generation, enablement, rotation/rewrap, backup dependencies and the exact localhost-only security boundary.

Verification:

- Clean isolated PostgreSQL/pgvector suite: **216 passed, 1 skipped**, including encryption round-trip, unique nonce, AAD/tamper/unknown-key failure, redaction/raw-database scans, all credential kinds, rotation/rewrap, audit safety, project isolation and exception sanitization. Backend Ruff lint and formatting checks passed.
- Frontend structure/ESLint, strict TypeScript, **76 Vitest tests across 22 files** and production build passed. Vite retains the known non-blocking approximately 618 kB chunk advisory.
- The isolated Chromium vault journey passed after a production rebuild: **1 passed**. It verifies DOM, URL, browser-storage and API-response leakage boundaries, unavailable testing, rotation, rewrap, desktop/mobile rendering and mobile overflow. Runtime logs were scanned for submitted test secrets with no matches.
- The required finish review returned **PASS** after the selected connection received a programmatically exposed pressed state.

Remaining limits: Phase 6 deliberately supplies no live connector success path; test actions report unavailable until the matching real adapter is installed. The loopback boundary is not a substitute for user authentication, so source connections must remain disabled for shared/public deployments. Rotation retains old keys until all records are rewrapped; losing an in-use key makes those credentials intentionally undecryptable.

Next actionable step: Phase 7A adds S3 first, using the pinned official SDK contract, bounded paginated discovery/fetch and complete incremental provenance before S3 becomes available in production.

## Ingestion pipelines — Phase 5 acceptance criteria

Recorded before implementation on 2026-09-12:

- Alembic adds project-scoped stable source identities and immutable revisions plus explicit website run-item/revision/index membership. Every revision records canonical URL, fetch time, media type, content hash, safe validator metadata, stored-artifact identity and deterministic extraction/cleaning configuration; published chunks retain URL, heading/section and revision provenance.
- Starting a saved Website pipeline snapshots the exact version, source selection, processing/cleaning/chunking/embedding configuration and current prior-ready index. Discovery/fetch consumes only that snapshot and reuses Phase 4 SSRF, redirect, robots and budget enforcement; it never resolves historical membership from mutable current source state.
- First ingestion fetches, extracts, cleans, chunks and embeds every included HTML page. Refresh uses safe ETag/Last-Modified validators and content hashes to classify new, changed and unchanged pages, reuses only exactly compatible vectors, reports previously indexed URLs no longer discovered as removed, and retains every historical revision and index snapshot.
- Each bounded worker checkpoint is PostgreSQL-backed and execution-token fenced. Duplicate delivery, cancellation, retry exhaustion and stale recovery cannot duplicate revisions, repeat completed paid embedding work or publish a partial index. Any required discovery/fetch/extract/embed failure leaves the previous ready index/current pointer unchanged.
- Successful execution atomically publishes a new immutable index with exact source-revision membership and advances the destination's current-ready pointer only after all required items and embeddings succeed. The preceding ready version remains selectable and searchable by saved answer pipelines.
- Project-scoped run/item APIs and the ingestion editor expose discovered/new/changed/unchanged/removed/failed counters, stage progress, safe errors, exact revision/provenance and the published immutable index. Website run is enabled only for a valid saved unchanged pipeline; Existing Files behavior stays compatible.
- Controlled-site tests verify first crawl, incremental new/change/unchanged/removal, validator fallback, deterministic extraction/cleaning, embedding reuse, duplicate delivery, cancellation, stale recovery, failure rollback, project isolation and grounded answer retrieval from both preserved index versions. Clean/upgrade migrations, backend/frontend gates and isolated Chromium pass before Phase 5 is marked complete.

Status: complete for ingestion-pipeline Phase 5. Verified on 2026-09-12.

Implemented:

- Alembic `0012` adds project-scoped stable website items, immutable source revisions, exact index/revision/source-node membership and per-URL run outcomes. Raw HTML is stored under generated artifact identities; chunks retain canonical URL, revision and heading/section provenance.
- Saved Website versions now execute through the durable ingestion coordinator. Runs snapshot the exact graph, destination, prior-ready index and embedding configuration; the existing SSRF-safe connector performs bounded fetches and safe conditional requests.
- Deterministic extraction ignores executable and common layout content, prefers main/article content, preserves heading hierarchy and creates section-local character chunks. Content hashes classify new, changed and unchanged revisions; identical extracted content is deduplicated and compatible embeddings are reused.
- Refreshes explicitly report removals, retain historical revisions, and build indexes from exact revision membership. A new knowledge-set version becomes current only after its entire embedding job succeeds; failures and cancellation leave the previous ready index selectable.
- Project-scoped run/item reads expose Website outcome counts, safe reasons, immutable revision IDs and canonical locations. The ingestion editor runs only saved unchanged graphs, displays progress and per-item provenance, and reveals the published-index link only after successful atomic publication. Retrieval evidence now exposes source URL and section hierarchy.

Verification:

- Clean isolated PostgreSQL/pgvector suite: **208 passed, 1 skipped**, including first crawl, incremental refresh, new/change/unchanged/removal, conditional validators, deterministic extraction, vector reuse, duplicate delivery, cancellation, stale recovery, failed refresh rollback, project isolation and retrieval from preserved versions.
- Backend Ruff formatting/lint passed. Frontend ESLint, strict TypeScript, **72 Vitest tests** and production build passed; Vite retains the known non-blocking approximately 608 kB chunk advisory.
- Isolated Chromium journeys passed for Website preview → first publication → unchanged refresh → exact v2 answer retrieval and for the Existing Files regression: **2 passed**. Desktop 1440×1000 and mobile 390×844 captures were inspected and the mobile horizontal-overflow assertion passed.

Remaining limits: Website ingestion supports bounded server-rendered HTML only; JavaScript rendering, linked PDFs and authenticated sites remain unsupported. Required-page failures are fail-closed. A transaction failure after an artifact file is durably written can leave an unreferenced artifact for later cleanup, but it cannot publish or enter index membership. No live public-site or paid-provider call was used.

Next boundary: Phase 6 must not begin until the credential encryption/secret-store mechanism is selected. That choice controls connection persistence, rotation and deployment behavior.

## Ingestion pipelines — Phase 4 acceptance criteria

Recorded before implementation on 2026-09-12:

- A dedicated safe HTTP boundary accepts only credential-free HTTP(S), canonicalizes host/port/path, resolves before every request and redirect, and rejects loopback, private, link-local, multicast, reserved, unspecified and cloud-metadata destinations for every IPv4/IPv6 answer. Tests control both DNS resolution and transport, including rebinding and redirect targets.
- Website discovery supports one URL, explicit URL lists, bounded same-origin crawl and sitemap modes. Allowed origins and include/exclude paths cannot widen scope; robots is honored by default; redirects, pages, depth, bytes, timeout/deadline, concurrency and request rate remain within the immutable source-node configuration.
- HTML parsing is deterministic, non-executing and bounded. Only supported HTML responses enter link discovery; malformed pages, duplicate/canonical URLs, excluded paths, blocked targets, unsupported media types, response overflow and timeouts produce safe inspectable outcomes without response bodies or secrets in logs/errors.
- Alembic adds project-scoped asynchronous preview jobs and paginated preview items with constrained status/counts, immutable draft snapshot, cancellation token, dispatch/stale recovery fields and bounded retention behavior. Duplicate delivery, cancellation and exhausted recovery cannot resume network work or perform embedding/publication.
- Preview submission persists the validated draft before returning 202. The dispatcher and fenced preview worker execute bounded discovery checkpoints; project-scoped reads expose loading/queued/running/succeeded/failed/cancelled plus included/excluded/duplicate/failed items and reasons. Preview never creates processing runs, source revisions, embeddings or indexes.
- The ingestion editor adds Website source settings and a paginated preview inspector using real APIs. It preserves the Existing Files flow, authoritative validation, immutable-save/dirty boundaries, sequential polling, cancellation, responsive canvas/settings and clear URL-level reasons without rendering fetched HTML.
- Controlled resolver/transport security tests, clean/populated migration checks, backend regressions, frontend checks and an isolated controlled-site Chromium preview journey pass before Phase 4 is marked complete.

Status: complete for ingestion-pipeline Phase 4. Verified on 2026-09-12.

Implemented:

- A pinned-address standard-library HTTP boundary canonicalizes credential-free HTTP(S), validates every DNS answer before every request and redirect, preserves TLS SNI/Host while connecting to the approved address, rejects non-public and multicast destinations, refuses compressed bodies, and enforces response/aggregate byte, timeout, deadline and redirect budgets.
- The Website adapter supports single URL, URL list, same-origin crawl and bounded sitemap discovery. It applies origin/path scope, robots.txt by default, canonical duplicate handling, rate limits, HTML-only non-executing link parsing and explicit included/excluded/duplicate/failed reasons.
- Alembic `0011` adds project-scoped durable preview jobs and paginated items, one active preview per project, constrained counters/status, execution fencing, cancellation, stale recovery and bounded terminal retention. Preview snapshots the validated draft and cannot create processing, revision, embedding or index records.
- The ingestion editor exposes all Website discovery modes and budgets, polls and cancels real preview jobs sequentially, pages URL outcomes and clearly keeps Website execution disabled until Phase 5. Existing Files preview now uses the same asynchronous job path.

Verification:

- Backend isolated PostgreSQL suite: 203 passed, 1 skipped. Focused controlled resolver/transport suite: 18 passed, including DNS rebinding, cross-origin redirects, private/multicast IPv4/IPv6, timeouts, robots, duplicates, malformed/unsafe sitemaps, cancellation and project isolation.
- Backend Ruff format and lint passed. Frontend structure/lint, strict TypeScript, 72 Vitest tests and production build passed; Vite retains the known non-blocking ~608 kB chunk advisory.
- Isolated Chromium journeys passed for controlled Website preview and the Existing Files → ready index → grounded answer regression. Desktop 1440×1000 and mobile 390×844 states were inspected; the mobile horizontal-overflow assertion passed.

Remaining limits: Website is preview-only until Phase 5; JavaScript rendering and linked PDFs are unsupported; robots failures are fail-closed; preview discovery is deliberately sequential even though configuration snapshots a bounded future concurrency value. Live public-site traffic was not needed or performed because deterministic resolver/transport coverage exercises the security boundary without reaching external hosts.

Next actionable step: implement Phase 5 immutable Website identities/revisions, deterministic content extraction, incremental refresh and atomic index publication while preserving the previous ready index.

## Ingestion pipelines — Phase 3 acceptance criteria

Recorded before implementation on 2026-09-12:

- Existing Files source nodes persist explicit unique project document IDs. Preview and run submission reject missing, cross-project, unprocessed, failed or active documents and verify the saved parser/chunk/embedding configuration before queueing paid work.
- Alembic adds project-scoped ingestion runs and per-item records with constrained status/stage/counters, immutable pipeline-version and knowledge-set ownership, active-destination exclusion, bounded attempts and dispatcher/stale-recovery indexes. No credentials or source content are stored in pipeline configuration or errors.
- Run creation snapshots the exact immutable ingestion-pipeline version, explicit documents, selected successful processing runs, knowledge set and processing/embedding configuration. Every later stage consumes those IDs; it never discovers all project documents implicitly.
- PostgreSQL-backed dispatch and fenced workers execute bounded validation/membership/embed/publication units, tolerate duplicate delivery, persist progress, recover safe stale work and prevent failed, stale or cancelled attempts from publishing. Successful publication creates a new immutable ready index and updates only that knowledge set's current-ready pointer.
- Cancellation invalidates the run token, stops further scheduling and prevents partial publication. Per-item and run reads expose explicit queued/running/succeeded/failed/cancelled state, safe errors, stage and inspectable source/run/chunk provenance through bounded project-scoped APIs.
- The ingestion editor is feature-owned, accessible without dragging and preserves the current workspace design. Users can create/save/reopen an Existing Files graph, select explicit processed documents and a stable knowledge set, see authoritative validation, run the exact saved version, poll sequentially, cancel while actionable, inspect item provenance and open the published index.
- A completed browser journey uploads and processes two documents, saves an ingestion pipeline, runs it, inspects both items and the exact published index, selects that index from an answer pipeline and receives a grounded answer with citations. Existing answer, Knowledge Base, Playground and experiment behavior remains compatible.
- Clean/populated migrations, database constraints, project isolation, duplicate delivery, cancellation, stale recovery, atomic publication, frontend unit/build checks and isolated browser journeys pass before Phase 3 is marked complete.

Status: complete for ingestion-pipeline Phase 3. Verified on 2026-09-12.

Implemented:

- Alembic `0010` adds project-constrained ingestion runs/items, a single active run per knowledge set, bounded counters/attempts and a one-to-one published-index link. Run snapshots retain the immutable pipeline version, destination, exact document/content hashes, processing versions and complete embedding configuration.
- The Existing Files adapter discovers explicit project document IDs in stable paginated order. Preview explains reuse or required reprocessing without embedding; submission rejects missing, cross-project, unprocessed, active and failed latest document state before accepting work.
- The ingestion coordinator reuses matching successful character-window processing or creates a new processing version, then persists exact index membership and waits for the existing fenced processing/index workers. Duplicate delivery is inert after terminal state; cancellation and exhausted stale recovery fence coordinator, created processing, and unpublished index work.
- Project-scoped preview/run/detail/item/cancel APIs expose safe stage, progress, counts and per-file provenance. A ready `index_versions.ingestion_run_id` proves the publishing run, while atomic index publication keeps earlier ready knowledge-set versions usable.
- A feature-owned React Flow editor now creates, saves and reopens Existing Files pipelines, edits accessible document/chunk/destination settings outside drag interactions, previews real server decisions, runs only an unchanged saved version, polls sequentially, cancels active work and links to the exact published Knowledge Base version. Answer and ingestion routes remain explicitly separated by pipeline kind.
- Canvas execution feedback now projects the polled run's durable status, stage and embedding checkpoint onto the saved linear graph. Every node carries a visible icon-and-label state for queued, running, complete, failed or cancelled work; the active checkpoint uses restrained reduced-motion-safe emphasis, and a compact reserved run strip owns progress and cancellation without obscuring the graph or duplicating status below it. Reopening or refreshing a saved version restores its latest persisted run and terminal item details, while active restored runs resume polling. React Flow attribution is disabled through `proOptions.hideAttribution`.

Verification:

- Clean isolated PostgreSQL/pgvector suite: **185 passed, 1 skipped** (the existing opt-in live embedding check). This includes clean/model migrations, exact two-file membership/publication, answer-index selection, pagination/order, project isolation, cancellation, duplicate delivery and exhausted stale recovery. Backend Ruff lint and format checks passed.
- Frontend format, structure/ESLint, strict typecheck, **72 tests across 20 files**, and production build passed. The known approximately 601 kB Vite chunk advisory remains.
- The 2026-09-23 execution-visualization update passed frontend structure/ESLint, strict typecheck, **89 tests across 27 files**, the production build and a focused mocked Chromium journey covering checkpoint movement, selection, attribution removal and desktop/mobile layout. The existing Vite chunk-size advisory remains (approximately 667 kB for the main minified JavaScript chunk).
- The full isolated deterministic-provider Chromium run completed with **10 passed, 1 intentional missing-credentials skip and 2 failures**; the ingestion failure was a test navigation issue after switching to mobile and the answer-editor failure was non-reproducing. After correcting navigation and rebuilding, the complete ingestion journey plus both pipeline regressions passed together: **3 passed**.
- The browser journey uploaded and processed two files, previewed both, saved and executed the immutable ingestion version, inspected per-file provenance and the published index link, selected that exact two-passage index in an answer pipeline and received a cited grounded answer. Desktop 1440×1000 and mobile 390×844 captures had no page overflow; the confirmation pass verified canvas refitting and corrected return-link placement.
- The Impeccable detector reported only the repository's established Inter font warning and no new Phase 3 pattern. Its referenced degraded reviewer file was absent and workspace instructions prohibited spawning the optional finish-review sub-agent, so the bounded review was completed in-thread. No live provider, paid call, external source, developer data reset or persistent-volume deletion was used.

Remaining limitations: Phase 3 supports only already uploaded PDF/TXT files. Preview is synchronous because discovery is bounded to explicit project IDs. Website fetch/revision storage, async preview, credentialed connections, scheduling and shared-access authorization remain later phases. A processing or embedding request already in flight may finish and incur cost after cancellation, but its fenced result cannot publish through the cancelled run.

Next phase: Phase 4 may add bounded public Website discovery and async preview with the SSRF controls in the ingestion plan. It must not fetch content for indexing or embed during preview.

## Ingestion pipelines — Phase 2 acceptance criteria

Recorded before implementation on 2026-09-12:

- Alembic adds project-scoped knowledge sets, creates a stable default knowledge set for every existing project, associates every existing index version with its project's default set without changing index IDs, and preserves historical query, pipeline and experiment references through clean and populated upgrade checks.
- Index-version numbering and active-job exclusion are scoped to a knowledge set. Composite database constraints reject cross-project knowledge-set/index associations, and a knowledge set's current-ready pointer can reference only an index from the same project.
- New index construction accepts an explicit, bounded list of successful processing-run IDs and persists every selected run/chunk as immutable membership. Cross-project, missing, duplicate, incomplete and empty selections are rejected before an index is queued.
- The existing Knowledge Base action remains compatible by resolving its selected/default documents to an explicit latest-successful processing-run snapshot before calling the explicit construction path; later processing or uploads cannot alter that index's membership.
- Project-scoped knowledge-set and per-set index listings use bounded pagination. Existing index routes remain compatible while index reads identify their knowledge set, exact version and source-run count.
- Knowledge Base index rows are grouped and labeled by knowledge set. Answer-pipeline and Playground Retriever choices show the knowledge-set name plus exact ready index version and do not silently advance saved selections.
- Backend migration, project-isolation, explicit-membership and historical-reference regressions pass, together with backend lint/format, frontend format/lint/typecheck/unit/build and affected browser journeys.

Status: complete for ingestion-pipeline Phase 2. Verified on 2026-09-12.

Implemented:

- Alembic `0009` creates a stable **Uploaded documents** knowledge set for every existing project, assigns historical indexes without changing their IDs, scopes version/active-build constraints per knowledge set and enforces project-consistent index/current-ready references. New projects create their default set transactionally.
- Index construction now has an explicit processing-run service boundary. It rejects missing, duplicate, cross-project, incomplete, empty and over-limit membership, then persists every exact run/chunk before queueing. The compatible `POST /indexes` action resolves current or submitted document IDs to concrete latest-successful run IDs first.
- Successful fenced worker publication updates the destination's current-ready pointer atomically. Older ready indexes, saved pipeline index IDs, historical queries and experiments remain unchanged and searchable.
- Bounded project-scoped knowledge-set and per-set index APIs were added. Existing index reads now include knowledge-set identity/name, distinct processing-run count and current-ready state without exposing execution tokens or credentials.
- Knowledge Base groups immutable versions beneath the knowledge-set name and shows source-run/current-ready state. Answer editor and both Playground selectors show the knowledge-set name plus exact version and passage count; selection remains by immutable index UUID.
- Architecture, development and README guidance now describe the explicit/default snapshot boundary and current-ready semantics. No ingestion run, source revision, Website transport or credentialed connection was introduced.

Verification:

- Clean isolated PostgreSQL/pgvector suite: **182 passed, 1 skipped** (the existing opt-in live embedding check), including Alembic model drift/clean round-trip, populated `0008 → 0009` index-ID preservation, project constraints, explicit membership immutability and all query/pipeline/experiment regressions. The final focused composite-boundary check also passed after making its fixture unambiguous.
- Backend Ruff lint and format checks passed.
- Frontend format, structure/ESLint, strict typecheck, **71 tests across 20 files**, and production build passed. The known approximately 588 kB Vite chunk advisory remains.
- Isolated deterministic-provider Chromium checks passed for Knowledge Base indexing/retrieval, answer pipeline create/save/reopen/run and Playground retrieval/answer flows: **4 passed, 1 intentional missing-credentials skip**. The final index-label/current-ready confirmation passed separately: **1 passed, 1 intentional skip**.
- The existing-files index screen was inspected at 1440×1000 and 390×844; the mobile page had no horizontal overflow. Knowledge-set grouping, exact version, Ready/Current text, source-run count and controls remained readable. The Impeccable mechanical detector returned no findings.
- No live provider, paid model call, external source, developer database reset or persistent-volume deletion was used. Verification used `rag-phase2-test` and `rag-phase2-e2e` isolation.

Remaining limitations: the compatibility Knowledge Base action still targets the generated **Uploaded documents** set; named ingestion destinations become user-configurable with the Phase 3 editor. The frontend does not yet expose arbitrary document subsets because the Existing Files source node owns that selection in Phase 3. Ingestion workers, previews and cancellation do not exist yet. Existing local unauthenticated access, the upstream Starlette/AnyIO warning and Vite bundle advisory are unchanged.

Next phase: Phase 3 may implement Existing Files ingestion end to end against the explicit membership and knowledge-set foundation. Website and credentialed connectors remain out of scope until their later phases.

## Ingestion pipelines — Phase 1 acceptance criteria

Recorded before implementation on 2026-09-12:

- Alembic adds a non-null `pipelines.kind` constrained to `answer` or `ingestion`, backfills every existing pipeline as `answer`, and preserves existing pipeline/version/query identifiers and behavior through upgrade and downgrade checks.
- Pipeline create/list/version APIs remain project-scoped, accept an explicit kind, support server-side `kind=answer|ingestion` filtering, and preserve the legacy answer request shape as an `answer` pipeline.
- Answer versions continue to use the existing strict execution schema. Ingestion versions use a separate strict, versioned schema that permits one to ten recognized source nodes followed by exactly Extract → Clean → Chunk → Embed → Publish, rejects extra fields, mismatched layout, duplicate IDs, cycles and unsupported graph shapes, and never treats display/layout data as execution parameters.
- Connector-neutral contracts define deterministic discovery, fetch, unchanged and sanitized retry-classified error results, with deterministic fixtures/tests and no provider SDK dependency.
- Existing answer pipeline, version, query-run and project-wide document-indexing regressions remain behaviorally compatible; cross-project pipeline access remains rejected.
- The Pipelines page exposes refreshable/history-safe, project-scoped Answer pipelines and Ingestion pipelines tabs backed by the real kind filter. Answer creation/opening continues to work; ingestion creation is clearly unavailable and no preview, run, connector or other fake executable control is introduced.
- Backend schema/API/service tests, clean and populated upgrade migration checks, backend lint/format, frontend format/lint/typecheck/unit/build, affected browser regressions and one bounded desktop/mobile inspection pass satisfy the Phase 1 exit gate.

Status: complete for ingestion-pipeline Phase 1. Verified on 2026-09-12.

Implemented:

- Alembic `0008` adds and constrains `pipelines.kind`, backfills populated pre-Phase-1 rows as `answer`, and indexes project/kind/creation listings. Pipeline/version IDs and JSON survive the populated `0007 → 0008 → 0007 → 0008` path.
- Existing answer create/version requests remain valid without a `kind` field and are stored as `answer`. The project collection accepts `kind=answer|ingestion`; create and append dispatch strict validation from the requested/parent kind. Kind changes on append are rejected, ingestion versions cannot enter answer-run/preview/experiment paths, and existing answer validation remains the stable query/experiment contract.
- `app.schemas.ingestion` owns the separate schema-v1 execution union: one to ten Existing Files or Website source configurations, exactly one Extract/Clean/character Chunk/Embed/Publish index node, the exact supported fan-in plus linear processing chain, exact layout IDs, bounded numeric/URL/path settings and forbidden unknown fields. Existing-file IDs and embedding configuration are checked against the project/server before persistence.
- `app.connectors.base` defines immutable connector-neutral connection checks, stable discovered items, paginated discovery successes/failures, changed/unchanged/failed fetch results, content/provenance metadata and sanitized retry classification. Deterministic test doubles prove stable ordering and result behavior without provider SDKs or network traffic.
- The Pipelines page has URL-addressable Answer pipelines/Ingestion pipelines tabs backed by the server kind filter. The selected list URL is remembered per project only. Answer creation/opening remains operational; ingestion creation is disabled with explicit availability copy, ingestion rows have no editor/run action, and no connector/preview/worker behavior is exposed.
- Feature-owned frontend ingestion request/model contracts are present for later editor work. No knowledge set, ingestion run, worker, website fetch or connection record was introduced.

Verification:

- Isolated PostgreSQL/pgvector backend suite: **179 passed, 1 skipped** (the existing opt-in live embedding check), including clean/model migration checks, populated pipeline-kind upgrade/downgrade/re-upgrade, strict ingestion validation, project isolation and all answer/index/query/experiment regressions. Backend Ruff lint and format checks passed.
- Frontend format, structure/ESLint, strict typecheck and production build passed; **71 tests passed** across 20 files. The known Vite advisory remains for the approximately 587 kB main JavaScript chunk.
- Isolated Chromium stack: the initial complete run passed 9 journeys with 1 intentional missing-credentials skip; two answer/workspace journeys found only the deliberately renamed **New answer pipeline** locator. After updating those regressions, all three affected journeys passed together, including the new refresh/history/project-isolation tab flow and the full answer create/save/reopen/run/evidence path.
- Desktop 1440×1000 and mobile 390×844 ingestion-tab captures were inspected once; mobile had no horizontal page overflow. Agent-browser accessibility output exposed the tabs, disabled creation control and empty state. The Impeccable mechanical detector returned no findings.
- No provider SDK, external connector traffic, model call, developer-volume reset or ingestion execution was used. Browser verification ran in the separate `rag-phase1-e2e` stack.

Remaining limitations: this phase persists contracts/configuration only. Knowledge sets and explicit index membership begin in Phase 2; ingestion creation/editing, workers, preview and execution remain unavailable. Website schemas do not fetch URLs and therefore do not yet implement the Phase 4 SSRF transport boundary. Existing local unauthenticated access, upstream test warning and frontend bundle advisory remain unchanged.

Next phase: Phase 2 may add knowledge sets and explicit immutable index membership. It must not begin as part of this Phase 1 task.

## Retrieval node settings — completed 2026-09-12

Implemented the six agreed controls: search method, Top k, optional maximum vector distance, vector/keyword candidate counts and hybrid weighting. Shared validation and effective settings flow through canvas save/run, previews, direct retrieval, deferred queries and experiments. PostgreSQL keyword search and weighted RRF execute against scoped immutable index membership. No filters or reranking were implemented.

Added migration 0007 for lexical indexing without re-embedding, v1/v2 graph compatibility, mode-specific evidence scores, recorded retrieval outputs/diagnostics, shared visual forms and experiment export fields. Existing saved versions and source data are preserved. See the [original acceptance plan](retrieval-settings-plan.md) and [operating/API documentation](development.md#retrieval-search-settings).

Verification:

- Isolated PostgreSQL/pgvector backend: **164 passed, 1 skipped** (opt-in live embedding check). Includes configuration bounds, cosine cutoff, lexical and weighted RRF ordering, same-project index membership and cross-project isolation, zero-weight branches, provider failure, keyword without credentials, saved/preview/experiment snapshots, clean migrations and populated lexical downgrade/upgrade with preserved evidence.
- Frontend: **38 tests passed**, lint/typecheck and production builds passed. Backend Ruff lint/format passed.
- Browser regressions: **9 existing journeys passed**, with **1 missing-credentials case intentionally skipped** in the provider-fixture stack. New legacy-to-hybrid save/reload, all six controls, keyword preview and retrieval-only journey passed separately after fixing navigation/label test locators. It verifies original saved JSON remains unchanged and preview evidence has keyword scores without fabricated distances.
- Desktop/mobile screenshots reviewed; spacing refined and confirmed, no horizontal page overflow. Mechanical UI detector reported no findings. Direct agent-browser selection and keyword-search behavior were also inspected against isolated data.
- Local Compose images rebuilt; application containers explicitly recreated after detecting stale running images. `alembic current` confirmed 0007, `/api/ready` returned ready, and the running OpenAPI schema exposed HybridSearch. Developer volumes were preserved. No paid model calls were made for this task.

Limitations: simple lexical analysis has no language-specific stemming or exact substring guarantees; vector retrieval remains exact and source snapshots remain bounded to 50,000 chunks. No live-model quality comparison or large-corpus performance benchmark was run. Production build emits a bundle-size advisory (main bundle just over 500 kB); existing upstream test deprecation/color warnings remain. Schema-v2 pipelines require the updated backend; rollback must account for newly saved versions. Local unauthenticated deployment boundary is unchanged.

Next action: open a project → Pipelines → select Retriever; choose Search method and Top k, then expand Advanced search settings for mode-specific controls. Save a new version or test the draft in Playground.

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

## Milestone 5 — Datasets and experiments

Acceptance criteria (recorded before implementation): project-scoped immutable CSV dataset versions, bounded preview with row errors and example download; selection of one/two saved pipeline versions with visible configuration; application-owned RAGAS evaluator using separately configured OpenRouter model and existing embeddings; exact generation evidence and immutable evaluator/pipeline/dataset snapshots; durable Celery experiment progress, cancellation, duplicate protection and partial results; metric-specific unavailable/failure states and correct paired denominators; question/evidence comparison and safe CSV export; deterministic PostgreSQL/API/UI tests, browser journey, regressions and bounded live verification when configured.

Plan: (1) add dataset/experiment persistence and APIs; (2) pin and inspect RAGAS and implement evaluator adapters; (3) extend durable dispatcher with checkpointed question/candidate work; (4) add workspace import/setup/history/comparison UI; (5) verify migrations, failures/isolation/aggregation, browser flow and 3–5 live questions, then document results. User selected evaluator `openai/gpt-5.6-luna`, independently configured from CHAT_MODEL.

Status: implemented and verified; final visual confirmation below.

Milestone 5 implementation delivered:

- Added `models/experiment.py`, migration `0006_experiments.py`, typed request/read schemas, dataset/experiment service and API modules, evaluator interface/RAGAS adapter and staged Celery worker. Extended query execution only for atomic checkpoint linkage and cancellation checks; retrieval/generation engine is reused.
- Added Experiments sidebar/routes, API adapter, CSV preview/import and version inspection, setup, history/polling/cancellation, candidate summaries, paired/per-question comparison, evidence/judge inspector and formula-safe CSV export.
- Added isolated database/worker tests, real RAGAS adapter tests using deterministic structured responses, React import/validation tests, full browser experiment journey and opt-in bounded live script. Updated server settings, Compose configuration and locked compatible dependencies.

Verification (2026-09-11):

- Isolated PostgreSQL/pgvector suite: **145 passed, 1 skipped** (opt-in standalone embedding live test). Includes clean migrations, schema drift check, downgrade/upgrade paths, project isolation, immutable snapshots, CSV validation, metric requirements, true paired denominators, partial failures, duplicate delivery, stale recovery and cancellation before/during provider work.
- Frontend: **27 tests passed**; lint, strict typecheck and production build passed.
- Browser regressions: **8 passed, 1 intentionally skipped** in the configured fixture stack. New full experiment journey separately **1 passed** (2.2 minutes), including real import/version selection/Celery jobs/comparison/evidence/reload; no paid calls in these browser tests.
- Live verification: experiment `7e96a4c6-3ce6-4fb1-9413-7ba17fcde131` in the existing sample orchard project. Three reviewed questions × two existing saved versions (v3/v2), all six completed. Four answerable outputs scored successfully on all metrics. Both founder-question answers abstained; faithfulness/relevancy were unavailable and context recall reported missing reference. Paired sample count was 2 for each metric; faithfulness and context recall means were 1.0; relevancy approximately 0.954. These tiny-sample results verify integration and do not establish a superior pipeline.
- OpenRouter-reported generation cost: **$0.0003636**; evaluator LLM calls: **$0.00411326**. Embedding charges are unknown, so these are not total experiment costs. Live dataset, query and experiment records remain inspectable in the local app.
- Mechanical UI detector: no findings. Desktop/mobile comparison and evidence captures inspected, no horizontal page overflow. Visual review corrected undefined theme-token references and inherited checkbox sizing in setup. Final visual verdict recorded below.

Resolved verification failures: RAGAS 0.4.3 imports a module removed in langchain-community 0.4.2; pinned compatible 0.4.1. Browser test assertions were corrected to distinguish import/refresh statuses and target candidate comboboxes by accessible role.

Remaining limitations: local unauthenticated access only; CSV dataset replacement creates a new version, with no inline question editing/deletion or automatic generation. Paid stages have zero automatic retries to avoid duplicate charges after ambiguous failures; durable queue delivery retries and stale recovery remain enabled. Full evidence/judge snapshots can make large experiment detail responses expensive; configurable dataset limits bound the initial scope. Embedding token/cost accounting remains unavailable. One existing Starlette/AnyIO deprecation warning and Playwright terminal-color warnings remain. No live credential/model blocker.

Next action: open the local project → Experiments, inspect the retained live comparison, or preview/import reviewed questions for another project's saved pipelines.

Final visual verdict: **ship**. Theme integration and setup metric-control findings are resolved in desktop/mobile recaptures; no remaining material findings. Existing Impeccable design-sidecar drift was left outside this milestone. Normal local Compose services are running with the new migration and frontend; the separate browser-test stack was stopped without removing volumes.

Changed application entry points: `backend/app/api/experiments.py`, `api/routes.py`, `main.py`; `core/config.py`, `core/upload_limit.py`; `models/experiment.py`, `models/query.py`; `schemas/experiment.py`; `services/datasets.py`, `services/experiments.py`, `services/queries.py`; `evaluation/evaluator.py`; `workers/experiments.py`, `workers/celery_app.py`, `workers/dispatcher.py`; `backend/migrations/env.py`, `versions/0006_experiments.py`; `frontend/src/features/experiments/{api.ts,ExperimentsPage.tsx,experiments.css}`; `frontend/src/app/{App.tsx,navigation.ts}` and `frontend/src/lib/api.ts`. Supporting changes include tests, the live-check script, dependency locks, Compose/environment configuration and documentation.

## Live browser usability verification — 2026-09-12

Acceptance: execute all eight requested workflows through the real UI using isolated projects and bounded live provider calls; preserve existing data; capture desktop/mobile evidence, fix observed issues, repeat affected journeys and document unperformed checks.

Completed with installed agent-browser against the local Compose application (port 5173): project creation/switching; TXT/PDF upload, processing and chunks; live index/retrieval; two saved pipeline versions; Playground generation/citations; reviewed two-question CSV import; two-version RAGAS faithfulness experiment; per-question answers/evidence and CSV export. Both candidates answered the return-policy question and abstained on the unsupported founding year. Faithfulness was 1.0 on one scored question per candidate; abstentions were unavailable, not invented scores. This sample does not establish general quality or a winning configuration.

Fixed stale project switcher options, stale queued notices for processing/indexing, inconsistent chunk numbering, mobile navigation Escape handling, index selection loss after refresh/navigation, selected Playground version loss after project switching, and comparison-table keyboard/discoverability issues. Evaluation cost copy now mentions relevancy embedding costs only when that metric was selected. No schema/provider/execution changes.

Additional browser checks: empty project, missing-file validation, malformed PDF errors and retry, processing/index/experiment cancellation, previous successful chunk preservation, browser back/forward, direct links, mobile 390px layout, keyboard navigation and offline/retry recovery. No JavaScript runtime errors observed. Existing database records were preserved; QA records remain for inspection.

Validation: frontend 28 tests passed, lint/typecheck/build passed; backend 73 tests passed and 73 explicitly skipped (database/live test configuration not enabled). Mechanical design detector reported no findings. Playwright suite, full database integration/migration suite, screen-reader audit, all-device testing, provider outage/retry/worker-crash tests and the two other live evaluation metrics were not performed in this task.

Artifacts: `scrrenshot/qa-report.xlsx`, `scrrenshot/README.md`, screenshots, isolated sample inputs and actual exported experiment CSV. Workbook tabs distinguish tests, fixed/open UI issues, RAG/evaluation pointers with actionable prompts and retest criteria, exported results and screenshot links. Remaining improvements include safe answer formatting, preserving experiment form drafts and linking empty Playground states directly to ingestion. No claim of production readiness.

### Interactive Playground expansion — acceptance criteria

User requested separate retrieval and pipeline test modes with editable parameters in the sidebar. Retrieval must use real project-scoped search with selectable document set and Top k, without a generation call. Pipeline testing must expose document set, Top k, prompt, allowed model, temperature and output budget; drafts must execute through the existing validated engine, retain exact persisted snapshots, and never mutate saved versions. Saving a draft must explicitly create an immutable version. Preserve draft/navigation safeguards, provide progress/errors, retain source inspection, and verify both modes through the browser plus isolated regressions. Generation-only testing is not part of this scope.


### Follow-up completion and desktop sidebar verification

Completed the four initially open UI items: safe answer formatting, experiment draft continuity/reset, empty-Playground ingestion link, and readable metadata/controls. Playground now offers separate Retrieval test and Pipeline test modes, editable retrieval/generation parameters, exact preview snapshots, explicit immutable saving and reset. Direct/editor entry retains the selected saved version. The right sidebar spans the desktop workspace with consistent spacing, fixed header/save area and an independently scrolling form; feature CSS replaces accumulated Playground overrides in the app stylesheet.

Live agent-browser verification used only isolated QA data: retrieval returned actual policy text without generation; a draft with Top k 2, a one-sentence prompt and 128-token budget generated the correct warranty answer with S1. It took 2.63s and 455 tokens; provider-reported answer cost was $0.000116 excluding retrieval embeddings. Existing saved versions were preserved. Before/after screenshots were inspected at 1440x1000 and 1280x800, including scrolled settings, citations and details.

Frontend lint/typecheck/build and 36 unit tests passed. Backend PostgreSQL/pgvector suite passed 146 tests with one opt-in live embedding test skipped; changed Python files passed Ruff. Final browser regression: 9 passed, one missing-credential scenario skipped in the configured-provider fixture stack; results are recorded in scrrenshot/playwright-delivery-final.log. These isolated deterministic provider tests are distinct from the live checks above. Additional live relevancy and context-recall evaluation and export were completed earlier in this follow-up. Screen-reader/hardware-device testing, exhaustive upload limits and actual provider outage simulation remain unperformed. Generation-only testing is outside the requested two-mode Playground scope.

### Frontend maintainability refactor — acceptance criteria

Separate app navigation, route rendering and project data loading; extract the canvas node renderer; keep test code in separate test files; provide repeatable formatting and document CSS ownership. Preserve current routes, markup, styles, API behavior and saved-state boundaries. Verify frontend formatting, lint, type checking, unit tests and build; validate CSS rule order after extraction.

Completed: extracted workspace sidebar/router/project-loading hook, workflow node, document/chunk inspectors, and experiment comparison/configuration/question components. Added pinned Prettier and formatting scripts. Extracted ordered feature base CSS and theme tokens; preserved the existing dark override cascade. Following the user's clarified preference, moved all 11 unit/component test files and shared setup out of `src/` into `frontend/tests/`, updated imports/mocks and discovery, and enforced application/test import boundaries with ESLint. Existing feature tests retain their assertions; two new sidebar regressions cover remembered versions and Escape/focus behavior.

Verification: 40 tests passed across 11 files; lint, typecheck, production build, format check, and git whitespace check passed. Compared parsed CSS before and after expanding imports: selectors, declarations, nesting, and source order are identical. Browser journeys and visual screenshots were not rerun in this structural task. Build reports a 513 kB JavaScript chunk warning. Some page controllers and the cross-feature dark stylesheet still warrant incremental consolidation; conventions and source guidance are in `docs/frontend-standards.md`.

### Shadcn theme and frontend restructuring

The user requested a complete plan before implementation, with centralized CSS. See [frontend restructuring plan](frontend-restructure-plan.md) for the one-stylesheet target, shared component/domain boundaries, migration batches, CSS deletion evidence, and acceptance checks. This supersedes the earlier CSS Modules suggestion. Status: implemented; final verification is in progress.

Additional acceptance requirement: simplify the implementation itself, including duplicated domain logic, dead conditions, unclear naming, nested conditionals, large async JSX handlers and unnecessary file fragmentation. Each extraction must have a clear responsibility and consumer; formatting or moving code alone does not satisfy this requirement. Detailed examples and review gates are in section 5A of the plan.


Frontend restructuring implementation (2026-09-12): official shadcn CLI installation replaces custom primitive approximations; Tailwind/Vite plugin upgraded to 4.3.3. One authored stylesheet and root semantic tokens replace distributed CSS. Empty styles directory, unused wrappers, dead editor branches and obsolete selectors removed. All API modules now use descriptive operations with shared transport/pagination and separate domain contracts. Pipeline defaults and retrieval mode transitions are shared. Editable execution clones preserve saved snapshots; query polling is sequential and ignores stale responses. Tests remain outside source, and lint enforces stylesheet/test/shared-module boundaries. Standards and architecture describe the implemented ownership rather than the superseded feature-CSS proposal.

The component pass now uses shadcn Table, Badge, Tabs, Separator, Alert, Skeleton, Accordion and Progress in addition to the form primitives. Raw feature tables and progress elements were removed. Large route components were split into feature-owned sections; reusable Pagination, RetrievalSettingsForm, AnswerText and StatusBadge remain shared. Every non-generated TSX component is below 300 lines, while the longer Pipeline and Playground controller hooks retain cohesive state/request lifecycles.

## Reusable Website snapshots — Slice 3 verified (2026-09-22)

Knowledge Base now names the second top-level view **Indexes** and separates it into URL-addressable **Source snapshots** and **Indexes** catalogs. Snapshot detail reads project-scoped, paginated server resources and shows collection state, counts, captured page metadata, downstream indexes, legacy/unavailable lineage, safe errors, loading/empty states, and compact mobile master/detail navigation. Ready Website snapshots can start a real ingestion run with a selected saved Website pipeline version and either a new or existing index destination; progress is polled without another Website request. Refresh source uses the recorded immutable ingestion version. Index detail shows the exact snapshot, collection time, ingestion pipeline/version, chunk settings, embedding configuration, and provides functional links to build another variant or create an answer pipeline preselected to that exact ready index.

Verified checks: backend Ruff lint/format and 44 relevant contract/Website/index tests passed (26 integration tests skipped without the PostgreSQL test service); frontend Prettier, structure/ESLint, strict TypeScript, all 78 Vitest tests, and production build passed. The build retains the existing main-bundle size advisory. The interface detector reported only the pre-existing Inter font choice required by the established design system; no newly introduced UI anti-pattern was reported.

## Reusable Website snapshots — Slice 4 verified (2026-09-22)

The Website ingestion editor now offers two explicit execution paths: collect the latest source and build, or build from an exact ready snapshot selected by number and origin. Snapshot compatibility remains authoritative on the server and safe validation errors flow back into the editor. Answer-pipeline Retriever settings show the selected index's snapshot number and collection date, while the Knowledge Base handoff initializes an unsaved draft with that exact index. Experiment submission now snapshots the knowledge-set and source-snapshot lineage of every exact saved candidate. Setup and results distinguish **Same source snapshot** from a non-blocking content-comparison caveat, and CSV export retains snapshot IDs, numbers, and the comparison classification.

Verified checks: backend Ruff lint/format and 26 relevant experiment/pipeline/Website tests passed (30 PostgreSQL-dependent tests skipped without the integration service); frontend format, structure/ESLint, strict TypeScript, all 78 Vitest tests, and production build passed. No live Website, embedding, generation, or evaluator calls were made. The existing Vite bundle-size advisory and upstream Starlette/AnyIO deprecation warning remain.

## Reusable Website snapshots — Slice 5 complete (2026-09-22)

Final verification passed on a fresh isolated stack: backend Ruff format/lint and the complete PostgreSQL/pgvector suite (**253 passed, 4 skipped opt-in live-provider tests**), including clean migration, schema drift, populated downgrade/upgrade preservation, isolation, duplicate delivery, cancellation, snapshot reuse, and historical evidence. Frontend formatting, structure/ESLint, strict TypeScript, **78 Vitest tests**, and production build passed. Three affected deterministic Chromium regressions passed: one controlled Website snapshot produced two independently named indexes with different chunk settings and no second fetch, two exact answer-pipeline candidates, and a paired same-snapshot experiment; the existing-file answer workflow and the six-item experiment/evidence workflow also passed. Interactive desktop (1440px), 200%-equivalent (720px), mobile (390px), overflow, and keyboard checks passed. Documentation now covers the boundary, API/workflow, migration, backup, cost, legacy-lineage, and rollback behavior. No live provider or paid-model call was made.

Remaining known limits: Website JavaScript rendering and linked-PDF crawling remain unsupported; snapshot deletion/retention is intentionally absent; legacy lineage stays unavailable unless equivalence is provable; the local deployment remains unauthenticated and loopback-only. The existing Vite main-bundle advisory, upstream Starlette/AnyIO warning, and Celery root-container warning remain unchanged.

Final verification: Prettier check, structure/ESLint, strict TypeScript, all 66 Vitest tests across 18 files and the production build passed. A fresh isolated Compose stack passed 10 applicable Chromium journeys in 2.2 minutes; the credential-free scenario was skipped because this run intentionally enabled the local embedding-provider fixture. Visual confirmation covered Projects, Overview, Knowledge Base, Playground, Pipelines and Experiments at desktop size plus responsive project and experiment layouts. No live provider execution was used. The build reports a 586 kB minified JavaScript chunk warning; route-level code splitting remains a separate performance change. See [frontend restructuring plan](frontend-restructure-plan.md#implementation-result-2026-09-12) for concrete before/after examples and boundary decisions.

## Ingestion pipeline expansion — complete

Phases 1–9 delivered separate versioned ingestion graphs, stable knowledge sets, explicit immutable index membership, complete Existing Files and bounded Website ingestion, the AES-256-GCM connection vault, S3/Notion/Confluence adapters, durable schedules and final cross-feature hardening while preserving answer-pipeline behavior. Verification and remaining deployment limits are recorded in the Phase 9 result above; the complete phase table and exit gates remain in [ingestion-pipeline-plan.md](ingestion-pipeline-plan.md).
## Ingestion canvas node execution checkpoints — 2026-09-23

Status: implemented and verified.

- Migration `0019` adds ordered, project-scoped execution state for every node in
  an ingestion run. Connector and worker boundaries now persist Source, Extract,
  Clean, Chunk, Embed and Publish transitions rather than asking the browser to
  infer them from a percentage or broad run stage.
- The canvas reads those immutable node IDs directly. Exactly active work receives
  the restrained running treatment; earlier nodes retain a Complete check, future
  nodes remain Queued, and failure/cancellation resolves to labeled terminal
  states. Selection outlines remain independent of execution styling, reduced
  motion disables the pulse/spinner. This delivery initially hid React Flow attribution;
  the later production-quality hardening phase restored it because no Pro entitlement
  is recorded.
- Reloading a saved version restores its latest run and node checkpoints. The
  compact run strip remains above the graph; the redundant bottom execution
  status is not used.
- Verification: backend Ruff lint/format and compile checks passed. The complete
  isolated PostgreSQL suite passed with 254 tests and 4 opt-in live checks skipped,
  including Existing Files, Website, S3, Notion and Confluence. Frontend lint,
  strict TypeScript, all 90 Vitest tests and
  the production build passed; the existing approximately 668 kB Vite chunk
  advisory remains.

## Knowledge Base comprehension redesign — 2026-09-23

Acceptance criteria: explain the document → preparation → searchable collection →
retrieval model in the first viewport; consolidate exact-content duplicate uploads in
the document list; expose preparation readiness and next actions without opening the
inspector; make collection and immutable version context persistent; split overview,
provenance, version history, stored passages and retrieval testing; preserve real API
workflows, URL-addressable state, pagination, retries and project isolation; provide
purposeful mobile drill-down without page overflow.

Status: implemented and verified. Documents consolidate identical content while
retaining processing, retry, history and chunk inspection. Collections are grouped
across all index-version API pages and use an explicit catalog → immutable-version
drill-down; overview, provenance, versions, passages and retrieval testing remain
separate, URL-addressable sections. Source-snapshot selection now also preserves
canonical hash URLs and browser Back/Forward behavior.

Frontend Prettier, structure/ESLint, strict TypeScript, all 95 Vitest tests across 26
files and the production build passed. Agent Browser verified Documents, the collection
catalog, selected-version overview, retrieval testing and source-history empty state at
1440×1000 and 390×844 against the canonical `http://127.0.0.1:5273` frontend. Both
mobile views measured 390 px document width with no horizontal overflow. The
route-split production build completed without the earlier chunk-size advisory. The
design detector reported only the two established Inter-font warnings required by
`DESIGN.md`; no new warning class was introduced.

## LangChain answer-runtime migration — 2026-09-24

Acceptance criteria: compile the supported frontend-authored Question → Retriever →
Prompt → LLM → Answer graph with current LangChain runnable composition; retain strict
server graph validation, project/index isolation and immutable versions; bridge the
existing bounded OpenRouter embedding and generation providers into LangChain's native
interfaces; keep pgvector, hybrid/keyword retrieval, evidence provenance, citations,
insufficient-evidence handling, checkpointing, latency, usage and cost behavior; persist
runtime versions/node order; leave ingestion and RAGAS evaluation boundaries intact;
and verify direct queries, saved versions, previews, retrieval modes and failures with
real PostgreSQL/pgvector tests and deterministic provider doubles.

Implementation: `pipelines/langchain_rag.py` now compiles an LCEL
`RunnableSequence`. Application bridges implement `Embeddings`, `BaseRetriever` and
`BaseChatModel`, while `ChatPromptTemplate` renders the existing fixed system policy and
JSON evidence payload. The pgvector retriever continues through the project-scoped
`indexes.retrieve` service, with LangChain query embeddings injected only for vector
branches. Query execution reparses persisted pipeline execution as the authoritative
source for retrieval, prompt and node identity. Evidence is still committed before a
potentially billable generation request, provider retries remain disabled, and every
accepted run records pinned LangChain/runtime identity. Standalone Playground queries
use the same compiled default sequence. Ingestion execution and RAGAS evaluator
adapters are unchanged.

Verification: the complete isolated PostgreSQL/pgvector backend suite passed with
**260 tests passed and 4 opt-in live-provider tests skipped**. This includes query,
pipeline preview/versioning, vector/keyword/hybrid retrieval, experiment cancellation,
ingestion and evaluator regressions. Focused local checks passed with 36 tests and 35
expected database skips. Backend Ruff lint and format checks, lock consistency,
`git diff --check`, and a clean Docker backend image build from the exported lock all
passed. The existing Starlette/AnyIO deprecation warning remains.

The persistent backend, worker and dispatcher were rebuilt on that image. One bounded
live run then executed the existing saved schema-v2 frontend graph against its ready
61-chunk index through LangChain 1.4.0/core 1.6.2. It succeeded with five pgvector
results, three evidence items retained by the context budget, one valid citation and no
invalid citations. The saved snapshot included retrieval/generation/total latency,
1,214 reported tokens and the provider-reported generation cost; no evaluation request
was made.
