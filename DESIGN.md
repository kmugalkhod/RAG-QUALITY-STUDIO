# Workspace design

The current visual authority is the user's supplied dark pipeline-editor reference (2026-09-10). It supersedes the earlier green/serif implementation and the light Linear pilot. This is an operating interface: clear project context, readable configuration and evidence, persistent navigation and one primary action for the current state.

## Visual system

Use charcoal content (#181b21), a slightly lighter canvas/sidebar (#20242b), subtle borders (#343b46), readable foreground (#e8eaf0), secondary text (#a5afbf), and lavender accents (#afa1ff). Accent marks active navigation, selection, focus and the primary action. Success, failure and in-progress states have separate colors and explicit labels. Native inputs use a dark color scheme. Self-hosted Inter remains the UI font; its OFL license is included.

The shared theme lives in `frontend/src/app/styles.css`, the only application-owned stylesheet. Semantic shadcn tokens define common surface, text, border and accent colors; Tailwind utilities handle ordinary component layout. The 232px sidebar holds the project switcher and five implemented sections. The project/page header is 48px high. On mobile the navigation expands inline with visible focus and Escape support.

## Pipeline editor

The editor fills the space below the project header. A prominent editable pipeline name, version selector and Save/Test controls stay above the canvas. Save is primary for a changed draft; Test is primary for an unchanged saved version. Validation and unsaved changes are explicit. Palette and node settings can collapse.

New templates flow vertically through Question, Retriever, Prompt, LLM and Answer. Nodes are 320×84px, with a 16px title, one concise configuration line and an icon. Vertical spacing leaves room for connectors. The selected node has a lavender border. Its editable configuration appears in a 320px panel; the retriever also explains its supported search method as read-only information.

Existing graph coordinates are preserved. Horizontal layouts retain their original 220px node width. Arrange vertically is an explicit draft edit: it changes positions, refits the canvas and activates the unsaved guard. Discard restores the saved layout. Orientation is inferred from saved positions, keeping the current backend schema. Handle geometry is refreshed when orientation changes. Canvas fitting responds to viewport/panel size changes; mobile shows settings below the canvas.

## Other pages

Overview shows actual document/index/pipeline state and a contextual action. Knowledge Base uses source rows, separate Documents/Indexes views and an adjacent detail inspector; mobile detail replaces the table. Playground keeps questions, answers and evidence primary, with metadata/history collapsed. Settings shows supported configuration without secrets or nonfunctional edit controls. Projects and saved pipelines use compact lists.

Use real API data. Never copy the reference's illustrative project names, version numbers, preview badges or unsupported controls into the live application. Keep processing distinct from indexing and saved configurations distinct from execution results.

## Verification artifacts

Actual desktop/mobile screenshots for the current direction are in `.lavish/dark-workspace/`. Earlier `.lavish/linear-*` artifacts record superseded visual reviews. No screenshot data is used as runtime content.
