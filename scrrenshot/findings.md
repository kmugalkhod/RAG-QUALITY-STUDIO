# Live usability findings — 2026-09-12

Isolated project: `12809bf1-825c-4e0d-997d-91a656b48e6e` (QA usability 2026-09-12). Existing projects untouched. Live OpenRouter models; no mocked browser responses.

- P2: New project missing from switcher until navigating. Repro: create project, inspect switcher. Evidence: 01.
- P2: Index success retains stale queued notice. Repro: build index and wait for ready. Evidence: 04.
- P2: Playground calls first chunk 0, retrieval calls it 1. Evidence: 07 vs 04.
- P2: Mobile navigation Escape fails while focus remains on toggle. Repro: open navigation, press Escape; label remains Close navigation.
- P2: Mobile comparison hides candidate B horizontally without a scrolling hint; paired table lacks an explicit keyboard focus target. Evidence: 10.
- P2: Model Markdown emphasis appears as literal asterisks in answers. Evidence: 06/07. Keep source text untouched; follow-up rendering improvement needed.

## Final disposition

Fixed and browser-retested: stale switcher; queued notices (including parser failure); one-based chunk label; Escape from navigation toggle; keyboard-focusable comparison/history tables and horizontal-scroll hint; explicit selected-index link restoration; per-project Knowledge Base/Playground destination continuity; conditional relevancy cost caveat.

Follow-up: Markdown formatting, experiment draft persistence, direct empty-Playground action and scoped readability fixes are completed. Interactive retrieval/pipeline testing and a full-height desktop sidebar were added and verified. See README.md and qa-report.xlsx for current results and unperformed checks.
