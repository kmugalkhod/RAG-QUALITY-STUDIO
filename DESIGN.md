# Workspace design

The visual authority is [spec 0002](docs/specs/0002-workspace-ui-redesign/index.md), built and closed out on 2026-10-01. It replaced the charcoal and periwinkle direction from 2026-09-10. RAG Quality Studio is an operating interface: clear project context, readable configuration and evidence, persistent navigation, and one primary action for the current state. The main flow is open a project, prepare knowledge, ask a question, compare.

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
- **Named sizes**: `control-sm` 32px, `control-md` 40px, `control-lg` 48px, `row-header` 36px, `row` 44px, `tabbar` 56px, `node-h` 80px, `node-legacy` 220px, `sidebar` 224px, `node` 288px, `panel` 320px.
- **Type**: Inter at five sizes, each with its own line height: `xs` 12/16 for meta and badges, `sm` 14/20 for body and controls, `base` 16/24 for section titles, `lg` 20/28 for page titles, `xl` 24/32 for a page hero. Weights are 400, 500 and 600. Metrics use tabular numerals.
- **Color**: near monochrome surfaces (`background`, `surface`, `surface-raised`, `surface-hover`), two borders (`border` for hairlines, `border-strong` for control boundaries), three text levels (`foreground`, `foreground-muted`, `foreground-subtle` for decorative icons only), one blue accent (`accent` for links, selection and focus, `accent-fill` for the primary button), and status colors (`success`, `warning`, `danger`, `danger-fill`).
- **Other**: `rounded-control` 4px, `rounded-card` 8px, `rounded-full`; one shadow, `shadow-popover`; `--disabled-opacity` 0.5; 150ms for hover and 100ms for press.

Tailwind's default spacing, type, color, radius, shadow and blur scales are reset, so any other key generates no CSS.

## Themes

Light and dark are complete palettes. `:root` holds dark and `:root[data-theme="light"]` overrides it. `frontend/public/theme-init.js` runs before the stylesheet and sets `data-theme` from the stored choice (`rqs.theme`), or from the OS setting when nothing is stored, so the page never flashes the wrong theme. The header toggle switches without a reload, stores only `light` or `dark`, and syncs other tabs. Clerk receives the same colors through its appearance variables. Both themes pass the axe contrast rule on every route, and a unit test checks that control boundaries and the focus ring reach 3:1.

## Layout

- **Breakpoints**: below 768px is mobile, 768 to 1151px is tablet (panels stack below their content), 1152px and above is desktop.
- **Shell**: a 224px sidebar and a 48px header. Page gutters are 24px on desktop and 16px on mobile. On phones the sidebar gives way to a 56px bottom tab bar (Overview, Knowledge, Pipelines, Playground, More) that respects the safe area; More opens a sheet with the remaining routes. There is no hamburger menu. The tab bar hides while the Playground composer has focus.
- **Connection**: when the server cannot be reached, a banner under the header says so, shows the last successful contact and offers Retry while the shell polls readiness.
- **Overview**: a three stage strip (Prepare knowledge, Ask a question, Compare results) above the project summary. Only the first stage that is not ready carries a primary button.
- **Tables**: 44px rows, 36px header rows, 16px cell padding. Tables scroll inside a labeled region, never the page.
- **Panels**: node settings and evidence inspectors are 320px on desktop and full width below.
- **Control clusters**: the editor toolbar, Playground composer and retrieval settings are centered with mirrored groups. The primary action sits at the right end on desktop and full width at the bottom on mobile.

## Controls and states

- **Buttons**: three sizes (32, 40 and 48px) and six variants (primary, secondary, outline, ghost, destructive, link). On touch screens small and medium controls grow to 48px. Focus is a 2px accent ring with a 2px offset. Pressed is CSS `:active` with a 1px shift. Disabled uses `aria-disabled` so the button stays focusable. Loading keeps the width and shows a spinner. Primary and destructive presses give a short vibration on Android.
- **Fields**: 40px, 48px on touch.
- **Targets**: every interactive element is at least 44 by 44px on touch. Inline prose links and React Flow handles are exempt, because node settings forms are the accessible path.
- **Page states**: list and detail routes render the shared LoadingState, EmptyState (one action) and ErrorState (Retry). Settings renders loading and error. Editors show ErrorState for a missing pipeline.

## Pipeline editors

Node cards are 288 by 80px with a 20px icon, a 16px title and one 12px summary line from `summarizeNodeConfig`, shown in full in a tooltip. Saved horizontal layouts keep their 220px width. The selected node shows a 2px inset accent outline, so nothing shifts. Saved coordinates are never rewritten. The React Flow canvas, edges, handles and controls take their colors from the tokens in both themes. The answer editor keeps a 320px settings panel beside a canvas sized by `--editor-canvas`. The ingestion editor fills the viewport below the headers (`--ingestion-workspace`), its canvas never resizes when you change stage or source, and its settings panel scrolls on its own.

## Anti slop rules

No gradients, no glow or blur shadows, no glass or backdrop blur, no sparkle or magic icons, no purple or violet hue, and no colored card backgrounds. The accent covers under 5 percent of any screen. Status colors always appear with a text label. Status badges use colored text and a 1px colored border on the surface, never white text on a status fill.

## Website widget

The widget in `widget/` shares no code with Studio. Its stylesheet copies the same spacing, type, radius and both palettes as its own variables and follows the visitor's OS theme, not the host page. Each appearance option (blue, slate, green) has a fill and a text accent for each theme, all at 4.5:1 or better. The launcher is 56px and every target is 44px.

## Enforcement and verification

`npm run lint` runs the token guard in `frontend/scripts/check-structure.mjs`. It rejects color literals, off scale font sizes, style props, pixel bracket values, spacing or size keys outside the approved set, banned utilities, raw form elements in features, and any stylesheet rule outside the token block, `@layer base`, `@layer components` and the React Flow vendor block. The visual journey (`frontend/e2e/visual.spec.ts`) captures every route in desktop and phone contexts and both themes, forces the empty, error and loading states, and fails on contrast violations or horizontal overflow. Screenshots go to the ignored `frontend/test-results/visual/`. The `.lavish/` screenshots record superseded directions.

Use real API data. Keep processing distinct from indexing, and saved configurations distinct from execution results.
