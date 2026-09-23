# Workspace design

The current visual authority is the user's supplied dark pipeline-editor reference (2026-09-10). It supersedes the earlier green/serif implementation and the light Linear pilot. This is an operating interface: clear project context, readable configuration and evidence, persistent navigation and one primary action for the current state.

## Visual system

Use low-chroma charcoal content (#17191f), a slightly lighter raised surface (#20242b), subtle borders (#343b45), readable foreground (#eceef3), secondary text (#adb6c4), and a desaturated periwinkle accent (#a49bd8). Accent marks primary actions, focus, selection and meaningful active state; it is not a general decoration color. Success, warning and failure use muted sage, ochre and brick treatments with explicit labels. Native inputs use a dark color scheme. Self-hosted Inter remains the UI font; its OFL license is included. Technical values and metrics use tabular numerals where comparison benefits.

The shared theme lives in `frontend/src/app/styles.css`, the only application-owned stylesheet. Semantic tokens define surfaces, text, borders, focus, statuses and the 150ms interaction transition; Tailwind utilities handle ordinary component layout. The compact 216px sidebar holds the project switcher and implemented sections. Its active route uses a quiet tonal surface plus a one-pixel accent marker, not a filled accent block. The project/page header is 48px high. On mobile the navigation expands inline with 44px targets, visible focus and Escape support.

## Pipeline editor

The editor fills the space below the project header. A prominent editable pipeline name, version selector and Save/Test controls stay above the canvas. Save is primary for a changed draft; Test is primary for an unchanged saved version. Validation and unsaved changes are explicit. Palette and node settings can collapse.

New templates flow vertically through Question, Retriever, Prompt, LLM and Answer. Answer nodes are a compact 296×78px, with a 16px title, one concise configuration line and an icon. Vertical spacing leaves room for connectors. The selected node has a periwinkle border and persistent settings context. Its editable configuration appears in a 320px panel; the retriever also explains its supported search method as read-only information. Active ingestion nodes rely on explicit status labels and restrained depth rather than glow.

Existing graph coordinates are preserved. Horizontal layouts retain their original 220px node width. Arrange vertically is an explicit draft edit: it changes positions, refits the canvas and activates the unsaved guard. Discard restores the saved layout. Orientation is inferred from saved positions, keeping the current backend schema. Handle geometry is refreshed when orientation changes. Canvas fitting responds to viewport/panel size changes; mobile shows settings below the canvas.

## Other pages

Overview shows actual document/index/pipeline state, a compact source-to-configuration lifecycle and one contextual next action. Historical ready collections count as source/preparation history even if their original uploads were later removed. Knowledge Base makes the retrieval lifecycle explicit: Documents become prepared content, prepared content is published into Collections, and retrieval uses a specific immutable collection version. The Documents view represents each real document once and pairs its current readiness with the next available action rather than exposing duplicate upload or processing records as separate sources. Empty document state is a compact onboarding row that opens the real upload flow.

Collections use a master/detail workspace. The master list summarizes each collection and its current ready version; the detail keeps the selected collection name, immutable version and retrieval readiness visible while the user moves through progressively disclosed Overview, Sources, Versions, Passages and Test retrieval tabs. On mobile, opening a document or collection drills into its detail in place of the list and provides an explicit route back, instead of compressing the desktop split view.

Pipeline lists expose the latest immutable version, update date and validated readiness when those details are available. Playground keeps questions, answers and evidence primary, with metadata/history collapsed and evidence-oriented iconography rather than generic AI sparkle cues. Settings shows supported configuration without secrets or nonfunctional edit controls. Experiments is organized as three progressive stages—dataset, candidates, and metrics/execution—with a concise sticky run summary on desktop and collapsible stages on narrow screens. Projects and other saved objects use compact lists.

Use real API data. Never copy the reference's illustrative project names, version numbers, preview badges or unsupported controls into the live application. Keep processing distinct from indexing and saved configurations distinct from execution results.

## Verification artifacts

Actual desktop/mobile screenshots for the current direction are in `.lavish/dark-workspace/`. Earlier `.lavish/linear-*` artifacts record superseded visual reviews. No screenshot data is used as runtime content.
