# Spec 0003: Studio shell and guided pipeline setup

Status: mockup approved by the owner on 2026-10-06; built on 2026-10-06 (see the implementation plan for verification and the owner's build decisions).
Mockup: https://claude.ai/artifact/Y3xLjDf1eLAaDaeMAo2TaF (clickable; press Play on a frame). Its source is saved in `mockup/`:

- `Main.dc.html` is the dark desktop screen with all five steps.
- `Light.dc.html` is the light theme, opened on the Processing step.
- `Phone.dc.html` is 390px wide.

These are Design-canvas component files. Read them for structure, sizes and copy. They are not production code.

## Intent

Give the Studio a calmer, more focused shell and add a guided way to create an ingestion pipeline. The layout is inspired by a public study-planner setup page (takeUforward "Planly"). We borrow its structure and feel, never its brand, logo, name or exact visuals. Everything uses RAG Quality Studio's own content, logo mark and colors.

**Current behavior must not change.** Every page, route and feature keeps working as it does today. The guided setup is an additional way to create a pipeline. The canvas editor (sources panel, compact canvas, **Applies to** overrides from commit `0e91b51`) stays as the place to edit a pipeline afterwards. The guided setup saves the same ingestion pipeline versions through the same API.

## Shell

- Three separate rounded cards (radius about 10px, 1px hairline border) on a near-black app background with 8px gaps: the sidebar, a slim top bar of about 48px, and the main content panel.
- **Sidebar** (about 240px; collapses to 64px icons):
  - Our logo mark, then "RAG Quality Studio" with "Quality" in the accent color, and a collapse button on the right.
  - The project switcher.
  - Sections divided by hairlines, each with a small collapsible header: **Build** (Overview, Knowledge Base, Pipelines), **Run** (Playground, Deployments), **Measure** (Experiments, Settings, Help & docs).
  - Pipelines opens a sub-menu (Answer pipelines, Ingestion pipelines) with a left guide line.
  - The active item has a tinted background, an accent icon and a 2px accent marker on the sidebar's left edge.
  - Profile footer: initials avatar, name, and the role in small capitals (for example "OWNER · LOCAL").
- **Top bar:**
  - Breadcrumb on the left.
  - On the right, separated by thin vertical lines: search, the API status (green dot and "API ready"), the count of active runs, and the theme toggle.
- **Phone:** no sidebar. The existing bottom tab bar (Overview, Knowledge, Pipelines, Playground, More) stays.

## Guided setup page

Steps: **Sources → Output → Processing → Review → Run**.

- **Header row:** "Guided setup by RAG Quality Studio" on the left; **Discard draft** (outlined) and **Close** (text) on the right.
- **Heading:** one large plain sentence (24px, weight 500, soft bluish-white in dark), for example "Which websites should this pipeline read?".
- **Tip banner:** dark navy with an amber lightning icon and a one-line tip. On the right, an icon, a label and a large accent number that updates live (Pages per run, Indexes, Est. chunks, Progress).
- **Rows:** full width, about 46px, 6px radius, hairline border. Accent icon, bold name and a short hint on the left. On the right, a control (a thin slider with tick dots, a select, or a status chip) and the value in small muted text. A one-line summary under the list.
- **Step content:**
  1. **Sources:** one row per website with a page-limit slider, preview status and remove; an "Add a website" row; at most 5 sites; limit 2,500 pages per run.
  2. **Output:** **One combined index** or **One index per source**; per source shows each site's index name.
  3. **Processing:** Extract and Clean selects, Chunk size and Overlap sliders, the Embed model. In per-source mode, override rows ("Custom", Edit override, Use shared settings).
  4. **Review:** key/value rows, each with an Edit button that returns to that step.
  5. **Run:** one row per site with a progress bar and a status chip.
- **Sticky footer:** a short progress line, **Step N of 5**, the step name, "Draft saved"; **‹ Previous** (outlined) and one primary button (**Next: …**, **Save and publish**, **Open in editor**).
- **Estimates** are labelled as estimates and state their basis. The Est. chunks figure assumes about 2,400 tokens per page.

## Visual tokens

These come from the mockup. Map them onto `frontend/src/app/styles.css` tokens and update DESIGN.md, which currently specifies Inter.

- **Font:** Geist (body 13/18, hints 11/15, row titles 14 semibold, heading 24/30 weight 500); Geist Mono for counts and IDs.
- **Dark:**
  - bg `#09090b`, panel `#111113`, row `#141518`, hover `#1b1c20`, active `#18202d`
  - border `#212328`, strong border `#34373e`
  - text `#e8e9ec`, heading `#d3dbe8`, muted `#9a9ea7`, subtle `#6c7079`
  - accent `#4c8fe0`, primary fill `#2f6fd6`
  - banner `#0e1726` with border `#1b2940`, slider track `#2a2d33`, amber `#e0a63c`
- **Light:**
  - bg `#e8eaed`, panel `#ffffff`, row `#fafbfc`, active `#e9f1fc`
  - border `#e2e4e8`, text `#16181b`, heading `#1b2a40`
  - accent and fill `#2a63b5`, banner `#eef4fc`
- **Shape:** buttons 34px high (28px small), 6px radius. Touch targets still grow to 44px on touch screens, per DESIGN.md.

## Acceptance criteria for the build

- Every existing route works in the new shell, in both themes and at desktop, tablet and 390px, with no horizontal scroll.
- The sidebar groups, collapse state and active marker work with the keyboard, with accessible names.
- A user can create a Website ingestion pipeline (1–5 sites, merged or per source, shared processing with optional per-source overrides) through the five steps. The saved version opens unchanged in the canvas editor, and runs, refresh and run groups behave as today.
- The draft survives a reload ("Draft saved"); Discard and Close behave as labelled.
- Vitest, typecheck, ESLint with the token guard, the build and the existing Playwright journeys pass, plus new journeys for the shell and the guided setup.
