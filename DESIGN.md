# Workspace design

The visual authority is [spec 0002](docs/specs/0002-workspace-ui-redesign/index.md), built and closed out on 2026-10-01, as updated by [spec 0003](docs/specs/0003-studio-shell-guided-setup/index.md) (approved 2026-10-06): the Geist font, a deeper near black palette, 34px controls, the card shell and the guided pipeline setup. Spec 0002 replaced the charcoal and periwinkle direction from 2026-09-10. RAG Quality Studio is an operating interface: clear project context, readable configuration and evidence, persistent navigation, and one primary action for the current state. The main flow is open a project, prepare knowledge, ask a question, compare.

## References

Mobbin could not be used (paid plan and a sign in the automated browser could not complete). The system instead takes patterns from seven public references, recorded in the spec's [rationale](docs/specs/0002-workspace-ui-redesign/rationale.md#reference-research-2026-09-30-public-pages-verified-by-a-read-only-agent):

- **Vercel Geist**: spacing on multiples of 4 and 8, weights 400 to read, 500 to interact, 600 to announce, neutral surfaces with one accent.
- **Linear**: dense 4 to 8px gaps without shrinking targets, hairline borders at 8 percent.
- **Supabase**: 44px data rows, 36px header rows, borders instead of shadows in dark mode.
- **Material Design 3 and Apple HIG**: 48px touch controls, a 44px minimum for every target.
- **Home Assistant tiles**: mirrored control clusters and an explicit unavailable state.
- **Dify workflow studio**: a right side settings panel, a dotted canvas and compact node cards with one summary line.

## Tokens

Every value lives in the token block of `frontend/src/app/styles.css`, between `/* @tokens:start */` and `/* @tokens:end */`. The spec's Feature design section holds the full color table with each contrast ratio.

- **Spacing**: an 8pt grid with a 4px half step. Only the keys 1, 2, 3, 4, 6, 8, 12 and 16 exist (4 to 64px). Padding and margins use multiples of 8; 4 and 12px are for icon gaps and badges.
- **Named sizes**: `control-sm` 28px, `control-md` 34px, `control-lg` 48px, `row-header` 36px, `row` 44px, `tabbar` 56px, `node-h` 80px, `node-legacy` 220px, `sidebar` 240px, `node` 288px, `panel` 320px.
- **Type**: Geist at six sizes, each with its own line height: `xs` 11/15 for hints, meta and badges, `sm` 13/18 for body and controls, `md` 14/20 for row titles, `base` 16/24 for section titles (and phone form fields, so iOS never zooms), `lg` 20/28 for page titles and live figures, `xl` 24/30 for a page heading. Geist Mono (`font-mono`) sets counts and IDs. Weights are 400 for reading (body, counts and field values, even inside a medium label), 500 for interaction (buttons, labels, nav) and for the plain sentence headings of the guided setup, and 600 for page, section, card and row titles. Metrics use tabular numerals.
- **Color**: near monochrome surfaces (`background`, `surface` for cards and panels, `surface-raised` for rows, `surface-hover`, `surface-active` for the selected nav item or choice), two borders (`border` for hairlines, `border-strong` for control boundaries at 3:1), text levels (`foreground`, `heading` for the guided setup's large sentence, `foreground-muted`, `foreground-subtle` for decorative icons only), one blue accent (`accent` for links, selection and focus, `accent-fill` for the primary button), the tip banner (`banner`, `banner-border`, with `highlight`, an amber used only for its icon), `track` for slider and progress tracks, and status colors (`success`, `warning`, `danger`, `danger-fill`). The mockup's dark `#34373e` strong border is not used, because it reaches only about 1.6:1 against a panel.
- **Scrollbars**: thin, with a `scrollbar` thumb at 3:1 on the background and surface and a transparent track, in both themes.
- **Other**: `rounded-control` 6px, `rounded-card` 8px, `rounded-shell` 10px for the shell cards, `rounded-full`; one shadow, `shadow-popover`; `--disabled-opacity` 0.5; 150ms for hover and 100ms for press.

Tailwind's default spacing, type, color, radius, shadow and blur scales are reset, so any other key generates no CSS.

## Themes

Light and dark are complete palettes. `:root` holds dark and `:root[data-theme="light"]` overrides it. `frontend/public/theme-init.js` runs before the stylesheet and sets `data-theme` from the stored choice (`rqs.theme`), or from the OS setting when nothing is stored, so the page never flashes the wrong theme. The header toggle switches without a reload, stores only `light` or `dark`, and syncs other tabs. Clerk receives the same colors through its appearance variables. Both themes pass the axe contrast rule on every route, and a unit test checks that control boundaries and the focus ring reach 3:1.

## Layout

- **Breakpoints**: below 768px is mobile, 768 to 1151px is tablet (panels stack below their content), 1152px and above is desktop.
- **Shell** (spec 0003): three `rounded-shell` cards with a hairline border on the `background`, 8px apart: the sidebar, a 48px top bar and the content card (`surface`). The page still scrolls as a whole; the sidebar and top bar stay in place. Page gutters inside the content card are 24px on desktop and 16px on mobile.
  - **Sidebar**: 240px, or 64px of named icon links when collapsed (remembered per browser in `rqs.sidebar`, layout only). Pipeline editors open with it collapsed so the canvas gets the width; expanding it there lasts until the editor is left and does not change the remembered choice. The logo mark with "RAG Quality Studio" and Quality in the accent, the collapse button, the project switcher, then groups with collapsible headers: Build (Overview, Knowledge Base, Pipelines with an Answer and Ingestion sub-menu on a left guide line), Run (Playground, Deployments), Measure (Experiments, Settings, Help & docs) and Workspace (Manage projects, Organization settings). The active item has the `surface-active` fill, an accent icon and a 2px accent marker on the card's left edge. The footer shows initials, the name and the role in small capitals (Owner · local without Clerk).
  - **Top bar**: the breadcrumb (project, page, detail) on the left; on the right, separated by hairlines, the quick jump (Ctrl K: a filter over pages, projects and this project's pipelines; it only navigates), the API status from the readiness store, the count of queued and running ingestion runs among the project's 20 most recent, and the theme toggle.
  - **Phones**: no sidebar. The 56px bottom tab bar (Overview, Knowledge, Pipelines, Playground, More) respects the safe area; More opens a sheet with the remaining routes. There is no hamburger menu. The tab bar hides while the Playground composer has focus.
- **Connection**: when the server cannot be reached, a banner under the header says so, shows the last successful contact and offers Retry while the shell polls readiness.
- **Overview**: a three stage strip (Prepare knowledge, Ask a question, Compare results) above the project summary. Only the first stage that is not ready carries a primary button.
- **Tables**: 44px rows, 36px header rows, 16px cell padding. Tables scroll inside a labeled region, never the page.
- **Panels**: node settings and evidence inspectors are 320px on desktop and full width below.
- **Control clusters**: the editor toolbar, Playground composer and retrieval settings are centered with mirrored groups. The primary action sits at the right end on desktop and full width at the bottom on mobile.

## Controls and states

- **Buttons**: three sizes (28, 34 and 48px) and six variants (primary, secondary, outline, ghost, destructive, link). On touch screens small and medium controls grow to 48px. Focus is a 2px accent ring with a 2px offset. Pressed is CSS `:active` with a 1px shift. Disabled uses `aria-disabled` so the button stays focusable. Loading keeps the width and shows a spinner. Primary and destructive presses give a short vibration on Android.
- **Fields**: 34px, 48px on touch.
- **Targets**: every interactive element is at least 44 by 44px on touch. Inline prose links and React Flow handles are exempt, because node settings forms are the accessible path.
- **Page states**: list and detail routes render the shared LoadingState, EmptyState (one action) and ErrorState (Retry). Settings renders loading and error. Editors show ErrorState for a missing pipeline.

## Pipeline editors

Node cards are 288 by 80px with a 20px icon, a 16px title and one 12px summary line from `summarizeNodeConfig`, shown in full in a tooltip. Saved horizontal layouts keep their 220px width. The selected node shows a 2px inset accent outline, so nothing shifts. Saved coordinates are never rewritten. The React Flow canvas, edges, handles and controls take their colors from the tokens in both themes. The answer editor keeps a 320px settings panel beside a canvas sized by `--editor-canvas`. The ingestion editor fills the viewport below the headers (`--ingestion-workspace`), its canvas never resizes when you change stage or source, and its settings panel scrolls on its own.

The Website sources panel keeps the list short: the Output choice (Combined or Per source) sits under the Sources header with one hint line, each source is a three line card (name and status, host and outcome, shared or custom settings) and its run and remove actions open inside the card from its "⋯" button; Remove asks for confirmation. The last run of a one-index-per-source pipeline is one summary line with Details for the per-index rows, which open on their own when an index failed. Source settings show their fields first; the website explanation is under "How website ingestion works", and the connection vault notice appears only while the source type can change or for a credentialed source. Below desktop, preview and run results scroll inside 70 percent of the screen height.

## Guided setup

`#/projects/:id/pipelines/setup?kind=ingestion`, opened from **Guided setup** beside New ingestion pipeline, creates a Website ingestion pipeline in five steps: Sources, Output, Processing, Review and Run. A header row (Discard draft, Close), a 24/30 weight 500 `heading` sentence, the `banner` tip with an amber `highlight` icon and a live accent figure, full width `surface-raised` rows (name and hint on the left, a control and a mono value on the right) and a sticky footer (progress, Step N of 5, Draft saved, Previous and one primary button). Estimates are labelled as estimates and give their basis. The canvas editor remains the place to edit the pipeline afterwards.

## Anti slop rules

No gradients, no glow or blur shadows, no glass or backdrop blur, no sparkle or magic icons, no purple or violet hue, and no colored card backgrounds. The accent covers under 5 percent of any screen. Status colors always appear with a text label. Status badges use colored text and a 1px colored border on the surface, never white text on a status fill.

## Website widget

The widget in `widget/` shares no code with Studio. Its stylesheet copies the spec 0002 spacing, type, radius and both palettes as its own variables (spec 0003 did not change the widget) and follows the visitor's OS theme, not the host page. Each appearance option (blue, slate, green) has a fill and a text accent for each theme, all at 4.5:1 or better. The launcher is 56px and every target is 44px.

## Enforcement and verification

`npm run lint` runs the token guard in `frontend/scripts/check-structure.mjs`. It rejects color literals, off scale font sizes, style props, pixel bracket values, spacing or size keys outside the approved set, banned utilities, raw form elements in features, and any stylesheet rule outside the token block, `@layer base`, `@layer components` and the React Flow vendor block. The visual journey (`frontend/e2e/visual.spec.ts`) captures every route in desktop and phone contexts and both themes, forces the empty, error and loading states, and fails on contrast violations or horizontal overflow. Screenshots go to the ignored `frontend/test-results/visual/`. The `.lavish/` screenshots record superseded directions.

Use real API data. Keep processing distinct from indexing, and saved configurations distinct from execution results.
