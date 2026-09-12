# Current implementation phase

Feature: Ingestion pipelines

```text
PHASE_NUMBER=2
STATUS=ready
```

## Current phase

Phase 2 — Knowledge sets and explicit index membership.

Implement the complete Phase 2 scope and stop at its exit gate. The authoritative requirements and copy-paste prompt are in [`docs/ingestion-pipeline-plan.md`](../docs/ingestion-pipeline-plan.md#phase-2-prompt).

## Required references

- [`AGENTS.md`](../AGENTS.md)
- [`DESIGN.md`](../DESIGN.md)
- [`docs/frontend-standards.md`](../docs/frontend-standards.md)
- [`docs/ingestion-pipeline-plan.md`](../docs/ingestion-pipeline-plan.md)
- [`docs/implementation-plan.md`](../docs/implementation-plan.md)
- [`docs/architecture.md`](../docs/architecture.md)
- [`docs/development.md`](../docs/development.md)

## Completion handoff

When the phase exit gate passes:

1. Change `STATUS` to `complete`.
2. Record the completion date, checks actually run, remaining limitations and important changed files below.
3. Update the matching phase status in `docs/ingestion-pipeline-plan.md`.
4. Update `docs/implementation-plan.md` with verified implementation results.
5. Change `PHASE_NUMBER` and **Current phase** to the next dependency-unblocked phase and set `STATUS=ready`.
6. Do not begin the next phase in the same implementation task.

## Completion record

### Phase 1 — complete 2026-09-12

Implemented migration `0008`, explicit answer/ingestion pipeline kinds, strict separate ingestion graph/config/layout validation, kind-dispatched persistence and server-side listing filters, connector-neutral contracts with deterministic fixtures, and URL-addressable project-scoped pipeline tabs. Existing answer behavior remains available; ingestion creation/execution is explicitly unavailable.

Checks run:

- Isolated PostgreSQL/pgvector backend: 179 passed, 1 opt-in live embedding check skipped.
- Backend Ruff lint and formatting: passed.
- Frontend Prettier, structure/ESLint, strict typecheck, 71 tests and production build: passed.
- Isolated Chromium: 9 unaffected journeys passed with 1 intentional missing-credentials skip in the complete run; after updating the deliberate answer-create label, the two affected regressions plus the new kind-tab journey passed together.
- Desktop/mobile agent-browser inspection: passed; no mobile horizontal overflow. Impeccable detector: no findings.

Remaining limitations: only contracts and graph persistence exist. Knowledge sets, explicit index membership, ingestion editor/create flow, preview, workers, website fetching, source connections and ingestion execution are not implemented. Local authentication and known upstream warning/bundle advisory are unchanged.

Important changed files: `backend/migrations/versions/0008_pipeline_kinds.py`, `backend/app/schemas/ingestion.py`, `backend/app/connectors/base.py`, `backend/app/services/pipelines.py`, `backend/app/api/pipelines.py`, `frontend/src/features/pipelines/PipelinesPage.tsx`, `frontend/src/features/ingestion-pipelines/`, and their backend/frontend/browser tests.

Phase 2 is dependency-unblocked and ready. It was not started in this task.
