# Scope: RAG Quality Studio

RAG Quality Studio helps RAG engineers and operators build versioned knowledge, inspect cited answers, and compare measured quality. The next work improves the quality decision in the private local workspace. A workspace UI redesign, which you authorized on 2026-09-30, comes first so later screens use the new design system. It uses a small English question set, bounded live calls, and no billing or third party tracking.

**Build approach:** Tracer Bullet (complete one real path through the interface, API, persistence, and verification before widening it).
**Workflow:** Beta (verify each new feature in the real app, then add focused tests). A feature with an unmade decision starts with `/architect`.

These are recommendations. You can change the order or skip a step that no longer fits.

## At a glance

| # | Feature | Phase | Status |
|---|---|---|---|
| 1 | Projects and access | Existing foundation | existing |
| 2 | Sources and ingestion | Existing workflow | existing |
| 3 | Knowledge versions and retrieval | Existing workflow | existing |
| 4 | Answer pipelines and evidence | Existing workflow | existing |
| 5 | Datasets and experiments | Existing workflow | existing |
| 6 | Deployed answer API | Existing local delivery | existing |
| 7 | Documentation and operations | Existing local delivery | existing |
| 8 | Private website widget | Existing local delivery | existing |
| 9 | Reviewed quality dataset | Cancelled | dropped |
| 10 | Human answer and evidence review | Quality slice 2 | planned |
| 11 | Quality comparison decision | Quality slice 3 | planned |
| 12 | Held out confirmation | Quality slice 4 | planned |
| 13 | Public visitor website widget | Existing local delivery | existing |
| 14 | Workspace UI redesign | Redesign slice | done |
| 15 | Multi-source ingestion pipelines | Ingestion slice | done |

## Existing foundation

### 1. Projects and access · existing

Project creation, organization membership, and project roles give each workspace a durable ownership boundary. The current Clerk mode is for local development.

**Done when:** a permitted member can work in the right project and another project or organization cannot expose its data. Code in `backend/app/core/auth.py`, `backend/app/services/projects.py`, and `frontend/src/features/projects/`.

## Existing workflow

### 2. Sources and ingestion · existing

Documents and configured sources flow through preview, processing, provenance, and durable ingestion jobs.

**Done when:** a selected source can publish a complete new index without exposing a partial index or erasing the previous ready version. Code in `backend/app/connectors/`, `backend/app/ingestion_content/`, `backend/app/workers/ingestion.py`, and `frontend/src/features/ingestion-pipelines/`.

### 3. Knowledge versions and retrieval · existing

Immutable index versions support dense, keyword, and hybrid retrieval with inspectable evidence and source lineage.

**Done when:** a project can inspect a ready index and retrieve only its own indexed passages using saved settings. Code in `backend/app/services/indexes.py`, `backend/app/pipelines/retrieval.py`, and `frontend/src/features/documents/`.

### 4. Answer pipelines and evidence · existing

Saved answer graphs and the Playground run grounded questions against selected ready indexes.

**Done when:** a question returns a cited answer or an explicit insufficient evidence result, with the supplied passages available to inspect. Code in `backend/app/services/pipelines.py`, `backend/app/services/queries.py`, `frontend/src/features/pipelines/`, and `frontend/src/features/playground/`.

### 5. Datasets and experiments · existing

Immutable CSV question sets, durable evaluation jobs, and paired reports already compare saved answer versions.

**Done when:** a member can inspect each question, answer, evidence, metric state, failure, latency, and known cost behind a comparison. Code in `backend/app/services/datasets.py`, `backend/app/services/experiments.py`, `backend/app/evaluation/`, and `frontend/src/features/experiments/`.

## Existing local delivery

### 6. Deployed answer API · existing

The local server API pins an answer release and index, applies admission limits, and saves durable customer question runs.

**Done when:** an authorized server key can submit and inspect a bounded run, while browser traffic cannot use that key route. Code in `backend/app/api/deployed_answers.py`, `backend/app/services/deployed_runs.py`, and `backend/app/workers/deployed_answers.py`.

### 7. Documentation and operations · existing

The local guide site and operator notes cover current workflows, recovery, and the boundary for shared release.

**Done when:** a local user can follow the guide and an operator can find the backup, restore, and job procedures. Code and content in `docs/site/`, `docs/development.md`, and `docs/operations.md`.

### 8. Private website widget · existing

The separate loader and iframe let an authenticated visitor ask one deployed answer pipeline through a customer backend. This is complete for local private checks in the current working tree; public hosting remains deferred.

**Done when:** a local customer fixture can obtain a visitor token, submit a question, and inspect a cited result, while a copied embed alone cannot ask. Code in `widget/`, `backend/app/api/widget.py`, and `frontend/src/features/deployments/WidgetSettings.tsx`.

### 13. Public visitor website widget · existing local delivery

An owner can opt in to public questions for an active deployment and exact site origin. A static site needs one script; Studio issues short-lived visitor tokens and applies the saved admission and spend limits. The local static page submitted a real question and displayed cited evidence. Internet hosting remains deferred.

## Cancelled work

### 9. Reviewed quality dataset · dropped

Cancelled at your request on 2026-09-29. The added review and approval workflow, implementation and spec were removed. Existing CSV imports and RAGAS experiments remain the product workflow.

## Redesign slice

### 14. Workspace UI redesign · done

Bring every Studio screen and the widget to a polished, professional standard, guided by Mobbin references (dashboards, workflow builders, data tools and device control apps) and an audit of the current UI. Define tokens first (8pt spacing grid, a type scale of at most five sizes, light and dark palettes, reusable buttons, cards, inspectors and the nav bar), then apply them to every screen with no one off styles. Simplify the main flow to the fewest steps: open project, prepare knowledge, ask a question, compare. Existing behavior and the API stay unchanged; this changes UI and UX only. You authorized replacing the `DESIGN.md` visual authority on 2026-09-30, so `/architect` should revise it rather than preserve it.

**Done when:** `DESIGN.md` records the chosen references, tokens and layout rules; every screen uses shared components on the 8pt grid with 44px or larger targets and clear pressed, disabled, focus, loading, empty, error and disconnected states; the app runs and a screenshot of each screen matches the recorded rules on desktop and mobile; existing tests still pass and no feature behavior changed.

- [x] Design it (spec): `/architect workspace UI redesign`
- [x] Build it: `/develop workspace UI redesign`
   - [x] Foundation: tokens, old CSS split with zero change parity check, theme init, lint guard, contrast test, journey scaffold (AC-1, AC-2, AC-12, AC-13)
      - Step 1 done 2026-09-30: parity compare at zero changed elements on 11 routes x 3 widths; guard at 518 (`LEGACY_ALLOWANCE`); lint, typecheck, 173 unit tests, build and the Projects visual journey pass. 15 existing journeys (experiments, pipelines, playground, ingestion, ingestion-layout) fail identically on the last commit, so they predate this feature (likely a stale `rag-studio-e2e` backend image). Next: build plan step 2, primitives.
   - [x] Primitives and shared states: buttons, inputs, Sheet, Tooltip, empty, error, loading (AC-3, AC-4, AC-10)
      - Step 2 done 2026-09-30: Button (3 sizes, 6 variants, `icon`, `loading`, `aria-disabled`, CSS pressed and touch sizing, vibration, deprecated aliases), 40px fields (48px on touch), Sheet and Tooltip, PageHeader and the three state components in `frontend/src/components/`; 8 `toBeDisabled()` checks converted; guard at 420. On unmigrated routes a legacy `.app-shell` mobile rule still holds controls at 44px until the shell migrates in step 3. indexes and ingestion-layout journeys fail on environment and fixture drift, not this change. Next: build plan step 3, shell and Overview.
   - [x] Shell and Overview: tab bar, disconnected banner, stage strip, Projects (AC-5, AC-6, AC-7, AC-8)
      - Step 3 done 2026-09-30: 224px sidebar and 48px header, phone tab bar with the More sheet (no hamburger), connection store fed by `api.ts` with the disconnected banner and readiness polling, Overview stage strip, Clerk appearance builder, Projects and Overview migrated; the `app-shell` legacy scope now wraps only unmigrated page content; guard at 357. Lint, typecheck, 197 unit tests, build, the visual journey (34 tests, both themes, forced states) and the workspace, projects, pipelines, documents, playground, experiments and retrieval settings journeys pass. Next: build plan step 4, Knowledge Base.
   - [x] Remaining screens: Knowledge, Playground, Experiments, editors, settings pages, theme toggle (AC-8, AC-9, AC-10)
      - Step 4 done 2026-09-30: Knowledge Base migrated (documents, upload, inspector, chunks, collections, stored passages, retrieval test, source history) onto PageHeader, the shared states and primitives, with 320px panels at desktop and list or detail swapping on phones; the shared RetrievalSettingsForm migrated with it, a RadioGroup primitive added and EmptyState given an optional heading level; 311 legacy selectors deleted; guard at 269. Lint, typecheck, 197 unit tests, build, the visual journey (now with Knowledge, both themes, forced states) and the documents, indexes, workspace, projects, retrieval settings, playground and pipelines journeys pass. The indexes fixture journey passed on rerun after one timeout while the worker was still publishing; its credential free case needs a stack without embedding credentials. Next: build plan step 5, Playground and Experiments.
      - Step 5 done 2026-09-30: Playground and Experiments migrated onto PageHeader, the shared states and primitives. The Playground has a centered toolbar (test mode, the exact configuration under test, panel toggles), a 320px side panel that owns its title and close button, fills the viewport on desktop and stacks the panel under the composer below 1152px; a failed catalog load shows ErrorState whose Retry remounts the screen, and no prepared documents shows EmptyState. Experiments has stage cards beside a 320px run summary, labeled table regions and page level loading, error and empty states, and the comparison detail uses named regions. The Knowledge `parts.tsx` moved to `src/components/` with `PRE` and `Callout` added, AnswerText was restyled, 193 legacy rules were deleted, `playground-page` and `playground-main` left `SCOPE_CLASSES`, and journeys moved off class selectors; guard at 179. Lint, typecheck, 197 unit tests, build and the visual journey (now with Playground and Experiments, both themes, forced states) pass, plus the workspace, documents, projects and pipeline kind journeys. The provider backed playground, experiments and pipeline editor journeys fail at the same step as before this change: they move on while the index is still publishing. Next: build plan step 6, the editors and remaining pages.
      - Step 6 done 2026-10-01: both pipeline editors, the Pipelines list, Deployments, Settings with Connections and project access, and the signed out Clerk landing migrated onto PageHeader, the shared states and primitives. Node cards are 288 by 80 (220px wide in saved horizontal layouts) with a `summarizeNodeConfig` summary line and Tooltip, an inset accent outline when selected, and ingestion run status as a StatusBadge; the React Flow vendor block maps canvas, node, edge, handle and controls variables to tokens in both themes. The answer editor has mirrored toolbar groups with one primary action and a 320px settings panel beside a canvas sized by `--editor-canvas`; the ingestion editor keeps its viewport sized workspace (`--ingestion-workspace`), and every raw checkbox, select and textarea became a primitive. Every legacy rule is deleted (the `legacy` layer is empty for close out), the `app-shell` wrapper is gone, every source path is in `MIGRATED_PATHS`, and the guard is at 0. The ThemeToggle now renders in the header. Journeys moved to test ids (`node-card`, `ingestion-node`, `ingestion-run-state`, `pipeline-canvas`, `published-index`), the phone ingestion canvas is 480px, and the visual journey covers the new routes (Deployments reaches only error and loading in local auth mode, because its API serves organization projects only). Fixed along the way: the ingestion stage scroll lookup and its 1152px breakpoint, and the Playground panel close focus return lost in step 5. Lint, typecheck, 197 unit tests and the build pass; the visual journey passed 134 of 142 before the deployments states were narrowed. Not yet run: the visual journey after the last two fixes, and the pipelines, retrieval settings, ingestion layout and ingestion journeys with their new selectors. Next: rerun those journeys, then build plan step 7, the widget.
   - [x] Widget and close out: widget tokens, scale reset, docs (AC-1, AC-11, AC-12, AC-13)
      - Step 6 follow up done 2026-10-01: the pending journeys were rerun. The ingestion layout journey had been crashing in its fixture since an older capabilities change; with a recorded capabilities fixture it exposed four real regressions, now fixed: the ingestion canvas grew with the settings panel (a fieldset gives flex children no definite height, so a wrapper div now owns the viewport sized column), the document overflowed by 5px (the title row passed 48px), the canvas resized when the source kind changed (the actions row is pinned at 64px on desktop again), and the failure alert lost focus. Stale steps in that journey (the section token chunk default, newer preview fields, copy) were updated. The visual journey got unique project names per worker and now waits for finite transitions before sampling contrast.
      - Step 7 done 2026-10-01: the widget stylesheet carries the spec token values as its own variables, follows the visitor's OS theme, and gives blue, slate and green a fill and text accent per theme (lowest ratio 5.18:1); 56px launcher, 44px targets. Widget typecheck, tests and build (CSS 9.3 of 20 kB) pass; the real frame in preview mode shows zero contrast violations and no small targets in all 12 theme and appearance combinations. With your approval the disposable `rag_widget_browser_test` database was recreated (its key file was gone), and all 18 widget browser journeys pass; their region lookup now matches any assistant title, because the fixture seeds "Fixture assistant" while the journey expected "Help assistant" since it was added.
      - Step 8 done 2026-10-01: the legacy layer, layer order line, Button aliases, theme aliases, `SCOPE_CLASSES`, `MIGRATED_PATHS` and the parity spec are gone; the guard now fails on any stylesheet rule outside the token block, base, components and the React Flow vendor block. Tailwind's spacing, text, color, radius, shadow and blur scales are reset to the approved keys (a selector and declaration diff of the build confirmed only the intended changes; the alert, accordion and answer text utilities moved onto approved keys, and the undefined widget preview size variables from step 6 are now defined). An unset theme follows the OS. Clerk gets every color it reads from the tokens. `DESIGN.md` and `docs/frontend-standards.md` describe the new system. Lint, typecheck, 196 unit tests, format check, build, the visual journey (134 of 134) and the full browser suite pass, except the docs site journeys (docs server not running) and the credential free indexes case (needs a stack without embedding credentials). Code in `frontend/src/`, `widget/src/styles.css`.
- [x] Verify it: `/check verify workspace UI redesign`
- [x] Test it: `/test workspace UI redesign`

Spec [0002](../specs/0002-workspace-ui-redesign/index.md)

## Ingestion slice

### 15. Multi-source ingestion pipelines · done

Let one ingestion pipeline read up to five Website sources and either merge them into one index or build one index per source, with per-source failure reasons, carry-forward of a failed source's last good content, and refresh of one source. Other connector kinds join later.

**Done when:** a merged pipeline with two sites publishes one index even when one site fails (with the reason shown), and a per-source pipeline publishes one index per site. Plan in [`docs/multi-source-ingestion-plan.md`](../multi-source-ingestion-plan.md).

## Quality slice 2

### 10. Human answer and evidence review · planned · needs a decision

Let a reviewer judge a bounded sample of actual answers, retrieved passages, and abstentions. Record the judgment beside the exact run so model scores can be checked against human evidence.

**Done when:** a reviewer can mark answer support, evidence usefulness, and abstention fit, with the reviewer and run identity retained and disagreements visible.

- [ ] Design it (spec): `/architect human answer and evidence review`

## Quality slice 3

### 11. Quality comparison decision · planned · needs a decision

Help an operator compare a baseline and one changed configuration on the same reviewed questions and compatible source versions. Put quality first within stated latency and cost limits, and show failures and unknown cost alongside successful scores.

**Done when:** the report shows paired sample counts, human judgments, model metric limits, latency, cost basis, and a measured reason to keep or reject the candidate. It does not claim proof of a root cause.

- [ ] Design it (spec): `/architect quality comparison decision`

## Quality slice 4

### 12. Held out confirmation · planned · needs a decision

Reserve questions that were not used to tune the candidate, then confirm the chosen change against them with bounded live calls. Keep the comparison and the final decision inspectable.

**Done when:** one real source flows through a cited answer and a measured baseline comparison, a separate held out set checks the chosen candidate, and the saved result states sample size, failures, latency, known and unknown cost, and limits. Changed flows meet WCAG 2.2 AA checks.

- [ ] Design it (spec): `/architect held out confirmation`

## Deferred

Public internet widget and API rollout, billing, product usage tracking, and UI translation are deferred. New retrieval methods or automatic configuration recommendations should follow measured evidence from the reviewed comparisons.

## Legend

`existing` means the local capability predates this scope. `planned` means its first unchecked command is the next design step. `/develop` builds a designed feature through its real layers. With the Beta workflow, `/check verify` and `/test` follow development. A later pass of `/scope` can reconcile shipped work and reorder the remaining slices.
