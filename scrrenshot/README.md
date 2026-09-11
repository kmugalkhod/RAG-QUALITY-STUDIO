# RAG Quality Studio — QA and desktop follow-up

Open [qa-report.xlsx](qa-report.xlsx). Seven tabs contain tests, UI findings/fixes, RAG/evaluation pointers with retest prompts, both live CSV exports, and screenshot links. Keep the workbook in this folder. Intermediate and before screenshots are retained.

All eight requested core journeys were verified earlier with the real local backend, worker, PostgreSQL and configured providers using two isolated QA projects. Existing user projects were preserved. The follow-up repeated affected navigation, editor, experiment-draft and Playground journeys; it did not rerun every paid experiment after each CSS change.

## Latest desktop screenshots

- Sidebar [before](80-sidebar-before.png), [after at 1440×1000](87-sidebar-final-desktop.png), [after at 1280×800](88-sidebar-final-1280.png).
- [Scrolled settings and keyboard focus](89-sidebar-final-scrolled.png).
- [Live draft answer and citation](84-live-draft-citation.png), [exact run details](85-live-draft-details.png), [retrieval-only results](86-live-retrieval-sidebar.png).
- [Experiment draft restored](51-draft-two-candidates-restored.png), [additional live metrics](50-live-other-metrics.png).

## Changes

Fixed project-switcher refresh, stale job notices, source numbering, project-scoped selection continuity, navigation Escape and experiment table access. The initially open formatting, experiment-draft persistence, empty-Playground action and scoped readability issues are now fixed.

Playground has Retrieval test and Pipeline test modes. The sidebar exposes actual pipeline/version names, documents, Top k, prompt, model, temperature and output budget. Draft tests preserve exact execution snapshots without changing saved versions; saving explicitly creates an immutable version. Sources, details and history stay in the sidebar. The right panel now fills the desktop workspace; its heading/save area stay fixed while settings scroll. The composer remains at the bottom. Styles are scoped to the Playground feature.

## Verification

Frontend: 36 unit tests, lint, typecheck and build passed. Backend: 146 tests passed, one opt-in standalone live embedding test skipped; PostgreSQL/pgvector integration and migrations included. Changed Python files passed Ruff. Final browser regression: 9 passed, one missing-credential scenario skipped because this stack has configured fixture providers. The final browser log is [playwright-delivery-final.log](playwright-delivery-final.log). Automated regression uses isolated deterministic providers; these are not represented as live verification.

Live follow-up: retrieval returned actual policy text without answer generation. A draft with Top k 2, a one-sentence prompt and 128-token output budget answered the warranty question correctly with S1. It took 2.63s and 455 tokens; reported generation cost $0.000116 excludes embeddings. Saved versions were unchanged. Earlier live experiments compared two versions for faithfulness and separately checked relevancy/context recall; both actual [initial](experiment-results.csv) and [additional-metrics](other-metrics-results.csv) exports are retained.

## Limits

No claim that every possible issue is fixed. Screen-reader/hardware-device testing, exhaustive size/pagination stress and actual provider-outage simulation remain unperformed. Native refresh-warning appearance was not manually validated because agent-browser accepts beforeunload automatically; in-app unsaved-change handling was tested. Generation-only testing and evidence-inclusive JSON export are not implemented. The two-question evaluation sample does not establish general quality or a winning pipeline.

The workbook is ZIP/XML validated, not visually opened in Excel. Regenerate with `python3 scrrenshot/build_report.py`.
