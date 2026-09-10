---
name: RAG Quality Studio
description: Existing visual system for configuring RAG work and inspecting evidence.
colors:
  primary: "#285d48"
  primary-foreground: "#ffffff"
  background: "#fcfcf9"
  canvas: "#f6f7f2"
  sidebar: "#eff1e9"
  muted: "#eeefe9"
  text: "#273c32"
  secondary-text: "#657065"
  input: "#c8cdc5"
  divider: "#dce0d6"
  error: "#8c3027"
typography:
  display:
    fontFamily: 'Georgia, "Times New Roman", serif'
    fontSize: "clamp(36px, 4vw, 48px)"
    fontWeight: 400
    lineHeight: 1.1
    letterSpacing: "-0.025em"
  body:
    fontFamily: '"Avenir Next", Avenir, "Segoe UI", sans-serif'
  title:
    fontSize: "16px"
    fontWeight: 600
  label:
    fontSize: "13px"
    fontWeight: 600
rounded:
  field: "5px"
  control: "6px"
  panel: "12px"
spacing:
  compact: "8px"
  control: "12px"
  section: "20px"
  panel: "24px"
  columns: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.control}"
    height: "40px"
    padding: "8px 16px"
  button-outline:
    backgroundColor: "{colors.background}"
    rounded: "{rounded.control}"
    height: "40px"
    padding: "8px 16px"
  panel:
    backgroundColor: "{colors.background}"
    rounded: "{rounded.panel}"
    padding: "24px"
---

## Overview

The incumbent interface uses green actions, warm neutral surfaces, serif page headings and sans-serif controls. It supports document and query work through readable forms, saved-run lists and evidence inspection. This records observed code rather than establishing a new visual identity.

Source: `frontend/src/app/styles.css`, `frontend/src/components/ui/button.tsx`, `frontend/src/features/playground/Playground.tsx`, and `frontend/src/features/pipelines/PipelineEditor.tsx`. Product context comes from `AGENTS.md`.

## Colors

Primary green identifies actions, links and focus. Warm neutral backgrounds separate the sidebar, canvas and forms; dark green text carries content and muted text carries metadata. Errors use the error color with visible text. Job status badges have separate green, red and amber treatments in the stylesheet.

## Typography

Serif display type distinguishes page titles and empty-state headings. Sans-serif type carries forms, navigation, evidence and metadata. Section titles use the title role; field labels use the label role. Answer text is slightly larger (17px), while answer and evidence text use generous line height (1.7) and preserve source line breaks.

## Layout

The desktop shell has a sidebar (242px), a flexible workspace and centered content capped at (1240px). Main horizontal padding is (48px), reducing to (28px) at (900px) and (20px) at (640px). The mobile shell moves navigation above content.

Query results place answer and evidence in equal columns with the columns spacing token; they stack at (850px). Document lists and upload forms stack at (700px). Preserve readable wrapping for long document names, questions, evidence and metadata.

The pipeline editor keeps its wrapping node palette above the canvas and settings beside it. Settings move below the canvas at (1150px). The canvas supports panning and explicit fit-view controls; selecting a node from the settings field brings it into view at a readable working scale. Graph overview and node editing are distinct viewing tasks, not a reason to reduce the interface type scale.

## Elevation & Depth

The observed system uses flat tonal surfaces and thin dividers. Panels are distinguished by a border and background; there is no shadow vocabulary in the source stylesheet.

## Shapes

Inputs have gently rounded corners, controls slightly rounder corners and form panels larger corners. Lists and evidence articles use horizontal separators instead of individual raised cards.

## Components

Primary buttons have solid green fills and white text; outline buttons use a neutral surface and input-colored border. Both have medium-weight small text, a compact size option (36px high), color transitions and half-opacity disabled states. Primary hover reduces fill opacity to 90%; outline hover uses the muted surface.

Inputs and textareas use white backgrounds, a thin muted green border and visible labels. Global keyboard focus uses a green outline (2px) offset (4px). Reduced-motion preference disables transitions. Busy forms announce progress; validation and request errors have alert semantics.

Active navigation has a soft green fill and a modest radius. Form panels use the panel tokens and reduce padding to (18px) on mobile. Status badges combine a readable status label with color.

Citation controls are underlined green references that move focus to the matching evidence article. Evidence shows provenance and retrieved text; metrics remain labeled, and unavailable values are explicitly represented.

### Workflow nodes

Nodes share a restrained bordered surface with three parts: a header naming the operation and its role, content summarizing current configuration, and a divided footer for configuration guidance or generation limits. Type is sans-serif throughout, using a strong title, readable configuration text and quieter metadata. Connections use muted strokes and green handles to show the executable graph.

**The Visible Selection Rule.** The canvas outline and the labeled selected-node field identify the same node. Editing takes place in visible settings fields; palette buttons provide a click alternative to dragging. Keep selected state distinct from keyboard focus.

Saved-version status and unsaved changes appear beside save controls. Graph validation precedes the saved-version run form, and results reuse the answer and evidence inspector. Node summaries describe configuration, not execution success or invented quality scores.

## Do's and Don'ts

- Do preserve visible keyboard focus, labeled fields and announced loading/error states.
- Do keep answer and evidence readable when columns stack.
- Do show text labels alongside status colors.
- Do preserve readable node content and synchronize canvas selection with labeled settings.
- Do distinguish draft changes, saved execution versions and returned results.
- Don't present retrieval distance as confidence or unavailable cost as zero.

## Linear-inspired Knowledge Base pilot — supersedes this page's incumbent styling

User direction on 2026-09-10: “use the liner type of design.” The earlier green/serif direction was rejected. The first-screen pilot is now extended through `.linear-workspace` across every route.

Reference: Linear's [2024 interface redesign](https://linear.app/now/how-we-redesigned-the-linear-ui) and [2026 refresh](https://linear.app/now/behind-the-latest-design-refresh). Apply the hierarchy and compact navigation rather than copying Linear branding or implying its features exist here.

The pilot uses white content, #f7f7f8 navigation, #27272b text, muted gray metadata, a #5e61c7 action/focus accent, self-hosted Inter typography (Linear’s documented UI face), page titles (22px) and compact rows (54px). Status green is reserved for processed/succeeded work. A 216px sidebar and 48px location bar form the outer frame. Documents and Indexes have separate views; an adjacent 350px document inspector keeps processing, provenance and chunks close to the selected source. The inspector becomes the main content view on mobile and closes back to the table. Upload opens from Add document. No invented content is used to fill empty space.

Implementation source: `frontend/src/app/linear-workspace.css`, the shared shell class in `App.tsx`, and `features/documents/KnowledgeBase.tsx`.

## Full workspace extension

Overview uses real source/pipeline rows and a small project-properties column. Settings uses read-only grouped definition lists. Playground gives the question, answer and evidence separate areas, with history collapsed. Projects and pipelines share compact list treatment. The editor takes all remaining viewport height instead of a fixed 470px box; its palette floats on the left and its 300px inspector can close. Mobile keeps a pannable canvas above editable node forms. Reference: [Dify Workflow Studio](https://dify.ai/workflows). Desktop/mobile captures are in `.lavish/linear-workspace/`.
