# 0002. Workspace UI redesign on a token based design system

**Date**: 2026-09-30
**Status**: Accepted

## Summary

Every Studio screen and the website widget move onto one small design system. It has an 8pt spacing grid, five type sizes, a near monochrome palette with one restrained blue accent, complete light and dark themes, and three control sizes. Today's dark only look, with 26 font sizes and 35 spacing values, is replaced one screen at a time, starting with the shell and Overview. The old class styles move into their own named layer (a CSS cascade layer), still ranked above utilities so screens that have not moved look exactly as they do today, while the old global element rules drop below utilities and a guard keeps old classes out of migrated files. Behavior and the API do not change. Reasoning and options: see [rationale.md](rationale.md).

## Requirements

**User stories**:

- As a RAG engineer, I want every screen to share the same spacing, type and controls so that I can read state quickly and never relearn a layout.
- As an operator on a phone, I want the main routes within thumb reach and controls I can hit reliably so that I can check a job or ask a question away from my desk.
- As a reviewer, I want light and dark themes that both meet contrast rules so that the app is usable in any lighting and any OS setting.
- As a maintainer, I want a lint rule that rejects off grid values so that the system does not drift back into one off styles.

**Acceptance criteria** (the contract, each criterion is independently checkable):

- **AC-1**: Tokens and the lint guard.
  - `frontend/src/app/styles.css` defines every token in Feature design between `/* @tokens:start */` and `/* @tokens:end */`.
  - Tailwind's import already declares `theme, base, components, utilities`. Immediately after the imports, the order is declared again with `legacy` appended, as `@layer theme, base, components, utilities, legacy;`, so `legacy` is the last layer and outranks utilities (unmigrated screens keep today's look).
  - Every pre existing rule whose selectors all contain a class sits inside `@layer legacy`.
  - Old element rules (selectors with no class) are handled one of two ways:
    - Deleted where Tailwind's reset (preflight) already does the same: `* { box-sizing: border-box }`, `body { margin: 0 }` and `h2 { margin: 0 }`.
    - Moved into `@layer base`, after preflight and below utilities: `body { min-width }`, `button, a` tap highlight, `button` and `button:disabled` cursor, `a { text-decoration: none }` (preflight uses `inherit`, which differs), `a:not([data-slot='button'])`, `h3`, `progress`, `main:focus`, `summary`, the two `input[type='file']` rules and the reduced motion rule.
  - The `footer` rule folds into `.create-project-footer`, its only user.
  - The two `:root` blocks (the token block and the alias block) stay unlayered. They hold only custom properties.
  - The four `.app-shell .react-flow__*` overrides move into the unlayered React Flow vendor block, because React Flow's own stylesheet is unlayered and would otherwise outrank them. Any other rule the parity diff shows losing to React Flow's stylesheet (for example `a { color: inherit }` against the attribution link) moves there too.
  - Utilities that the old class rules override stay untouched in step 1, because `legacy` still outranks them. Only utilities that a moved element rule used to override are edited. Each is deleted, or, where it only partly lost (for example `text-sm` setting both size and line height when the old rule set only the size), replaced with a narrower utility or covered by adding the property to the element's existing legacy class rule. The parity diff decides.
  - The legacy parity check (a computed style diff, see [verify.md](verify.md)) reports zero changed elements on every route after step 1.
  - The guard parses `styles.css` with `postcss` (already installed, no new dependency), walks the rules inside `@layer legacy` including nested `@media`, and skips `@keyframes`. It fails when any top level comma separated selector of a legacy rule has no class.
  - Legacy class names are the base classes it collects, meaning the first class of each compound (`selected` in `.connection-choice.selected` is not one), ignoring classes inside `:not()`.
  - The guard fails when any string literal in a file under a `MIGRATED_PATHS` entry (a file or directory prefix) contains a legacy class name as a whole word, after stripping variant prefixes such as `md:`. Names in its `SCOPE_CLASSES` list are exempt: `app-shell`, `playground-page` and `pipeline-editor`, plus any ancestor class that an unmigrated descendant rule still needs. That list empties at close out.
  - A legacy class in a migrated file is a hard failure. It is not counted in `LEGACY_ALLOWANCE`. `MIGRATED_PATHS` starts empty and grows with each migrated screen.
  - The guard in `scripts/check-structure.mjs` scans `frontend/src/**/*.{css,ts,tsx}` outside the token block and the `/* @vendor:react-flow:start */` to `/* @vendor:react-flow:end */` block. It counts one violation for each regex match of:
    - a hex, rgb or hsl color literal
    - a CSS `font-size` that is not `var(--text-*)` or `inherit`
    - a `style={{` prop with any key that is not a CSS custom property
    - an arbitrary bracket value in pixels, rem or percent
    - a spacing, size or text utility key in a `className`, `cn()` or `cva` string that is not in the approved key set; padding, margin and gap utilities may use only the grid keys 1, 2, 3, 4, 6, 8, 12 and 16
    - any `font-bold`, `backdrop-*`, `bg-gradient-*` or `blur-*` utility, and any off scale `rounded-*` or `shadow-*` key
    - a raw `<button>`, `<input>`, `<select>` or `<textarea>` element in a file under `src/features/`
  - The shorthand `(--var)` for Radix variables is allowed. `z-*` utilities are not checked.
  - The guard prints counts per file. It fails when the total is not equal to the `LEGACY_ALLOWANCE` integer in the script. The allowance is zero at close out.
  - At close out, `@theme inline` resets `--spacing-*`, `--text-*`, `--color-*`, `--radius-*`, `--shadow-*` and `--blur-*` to `initial` and defines only the approved keys: `rounded-control`, `rounded-card`, `rounded-full` and `shadow-popover`.
- **AC-2**: Theme selection and contrast.
  - `:root` holds the dark tokens and `:root[data-theme="light"]` overrides them, so the app renders dark even if the script fails.
  - `frontend/public/theme-init.js` loads synchronously as the first script in the `<head>` of `frontend/index.html`, before the stylesheet. It always sets `data-theme` on the html element.
  - It reads `rqs.theme` from local storage inside a try block. If the value is not `light` or `dark`, it falls back to `dark` until close out, and to `prefers-color-scheme` from close out onward.
  - A `useTheme` module in `src/app/` owns the header toggle, the OS change listener (active only while nothing is stored) and a `storage` event listener that syncs other tabs. The toggle switches without reload and stores only `light` or `dark`.
  - There is no flash of the wrong theme on load.
  - Every migrated route passes the axe `color-contrast` rule in each theme it is verified in.
  - A Vitest reads the token block and asserts that in both themes, `--border-strong` and the focus ring reach 3:1 against `--surface` and `--background`, and every text token pair in the color table reaches its stated ratio.
- **AC-3**: The button primitive exposes three sizes (sm 32px, md 40px, lg 48px) and six variants (primary, secondary, outline, ghost, destructive, link). An `icon` prop makes it square at the size height, with a 16px icon at sm and md and a 20px icon at lg.
  - **Touch.** Under `@media (pointer: coarse)`, sm and md both render at 48px. Icons keep their size and only the box grows, with no JavaScript and no flicker.
  - **Hit area.** On touch, every interactive element's own `boundingBox()` is at least 44 by 44px. Checkboxes get a label hit area of at least 44px. Inline links in prose and React Flow handles and edges are exempt, because node settings forms are the accessible path (a WCAG 2.5.8 exception).
  - **Focus** shows a 2px accent ring with a 2px offset in `--background`.
  - **Hover** uses the variant's hover fill.
  - **Pressed** uses CSS `:active`: the variant's pressed fill plus `translateY(1px)`, with a 100ms transition held while pressed, so keyboard activation shows it too.
  - **Disabled.** The `disabled` prop maps to `aria-disabled="true"`, and native `disabled` is never set. The button stays focusable, click and Enter submit are prevented, and `--disabled-opacity` applies. With `asChild` anchors, navigation is prevented and `href` is removed.
  - **Loading** sets `aria-busy="true"`, blocks the click, hides the label with `visibility: hidden` to keep the width, and centers the lucide `Loader2` icon with `animate-spin`. Under reduced motion, the icon is static.
  - Disabled content uses `--disabled-opacity` only, never `--foreground-subtle`.
- **AC-4**: The primary and destructive variants call `navigator.vibrate(10)` on `pointerdown` when `navigator.vibrate` is a function and `matchMedia('(pointer: coarse)').matches` at that moment. The call sits in a try block. The first tap of a page may be silent, because browsers block vibration before the first user activation. With `prefers-reduced-motion`, the `translateY` is removed while the fill change and vibration remain.
- **AC-5**: Layout and mobile navigation.
  - At 768px and wider, the sidebar is 224px and the header is 48px.
  - Below 768px on project routes, the sidebar is hidden. The header is 48px with no hamburger menu. It holds the project name (linking to Projects), the ThemeToggle once shown (see Build plan step 6), and the user button.
  - A 56px bottom tab bar shows five tabs with lucide icons: Overview (`LayoutDashboard`), Knowledge (`BookOpen`), Pipelines (`Workflow`), Playground (`MessageSquare`) and More (`Ellipsis`).
  - Tabs are anchor links to their hash routes. More is a button with `aria-haspopup="dialog"` that opens a bottom Sheet listing Experiments (`FlaskConical`), Deployments, Connections, Settings and All projects.
  - The active tab has `aria-current="page"`. Pipelines is active on the list and both editor routes. More is active on Experiments, Deployments, Connections and Settings.
  - Tabs have 48px targets inside a `nav` landmark and respect `env(safe-area-inset-bottom)`, with `viewport-fit=cover` in the viewport meta.
  - The tab bar is hidden while a Playground composer field has focus, so the phone keyboard cannot cover the composer.
  - Routes without a project, such as the Projects list, render no tab bar.
- **AC-6**: Overview shows a three stage strip above the existing Overview content, which stays and is moved onto the grid. The strip has three equal StageCards with the copy, counts, states and destinations in Value sourcing.
  - No primary button shows until all three count requests have settled.
  - A card whose request failed shows an inline ErrorState with Retry.
  - Among the loaded cards, the first one not ready carries the only primary button. When all are ready, the primary goes to Compare. Other cards use secondary buttons.
  - Every main route is reachable in at most two taps from Overview (checklist item).
- **AC-7**: A connection store in `src/lib/connection.ts` is fed by `src/lib/api.ts`.
  - A fetch `TypeError`, the 12 second timeout abort, or a 502, 503 or 504 response marks it unreachable with the safe message.
  - Any 2xx response marks it ok and records the time. User cancels do not change it.
  - While unreachable and while `document.hidden` is false, the shell polls `GET /api/ready` through `api.ts`, 5 seconds after each response ends. A failed poll does not reset the last contact time.
  - A `role="status"` banner under the header pushes content down. It shows "Cannot reach the server" with the safe message, and the last successful response time or "No successful response yet".
  - Retry sends an immediate readiness request. While that request runs, the banner reads "Checking…" and Retry shows its loading state.
  - The banner clears on the first 200 response. Page level validation and not found errors are unchanged.
- **AC-8**: These routes use only the shared primitives and shared product components: Projects, Overview, Knowledge Base, Pipelines list, answer pipeline editor, ingestion pipeline editor, Playground, Experiments, Deployments, Connections and Settings.
  - The Clerk sign in, which exists only when Clerk mode is on, receives the theme through its `appearance.variables`. These are built at runtime from `getComputedStyle` for `--accent-fill`, `--surface`, `--foreground` and `--border-strong`, and rebuilt on theme change. No new package is added.
  - Page padding is 24px on desktop and 16px on mobile. Side panels are 320px.
  - Control clusters are centered with mirrored left and right groups (checklist item).
  - At close out, `styles.css` holds only the token block, the base layer, the React Flow vendor block and a `components` layer of shared selectors, with no `legacy` layer. The element rules moved into `base` in step 1 are kept only where a migrated screen still needs them. The guard fails on any selector outside those layers.
- **AC-9**: Canvas node cards.
  - Answer pipeline and vertical ingestion node cards are 288 by 80px. Nodes in a saved horizontal layout keep their 220px width, as `DESIGN.md` does today.
  - Each card has a 16px title, a 20px icon, 16px padding, 4px radius and a 1px border.
  - The card has one 12px muted summary line from `summarizeNodeConfig` in the canvas component folder, using one format per node kind (for example "top_k 5 · dense"). The line is truncated with an ellipsis and shown in full in a Tooltip.
  - The selected node shows `outline: 2px solid var(--accent)` with `outline-offset: -1px`, so the layout does not shift, and `--xy-node-boxshadow-selected: none`.
  - Saved coordinates are never rewritten, and `useUpdateNodeInternals` runs after the card mounts.
  - The React Flow node, edge, handle, controls, minimap and background pattern variables are mapped to tokens in both themes.
- **AC-10**: The shared LoadingState, EmptyState (one action) and ErrorState (Retry) components cover these cases:
  - List and detail routes render all three.
  - Settings renders loading and error only.
  - Editors render ErrorState for a missing pipeline.
- **AC-11**: The widget stylesheet carries the same spacing, type, radius and both palettes through its own CSS variables, with a comment citing this spec's token table.
  - The iframe follows the visitor's OS theme through `prefers-color-scheme`, not the host page's theme.
  - Each of the three appearance options defines a light and a dark accent pair. White text on each fill and the accent as text on the surface reach 4.5:1.
  - The launcher is 56px, targets are 44px, and the widget shares no code with Studio.
- **AC-12**: A Playwright visual journey (`frontend/e2e/visual.spec.ts`) runs against the isolated browser stack in local auth mode.
  - A `MIGRATED_ROUTES` table in the spec file lists each route, its hash path and its primary list request.
  - It captures each migrated route in a 1280px desktop context and a `{ ...devices['iPhone 13'], defaultBrowserType: 'chromium' }` context. Only Chromium is installed, and the preset defaults to WebKit. The theme is set by `addInitScript` writing `rqs.theme`. Steps 1 and 2 run dark only. Step 3 onward runs both themes on migrated routes.
  - It forces states with `page.route()` on each route's primary list request, using fixtures typed from the generated OpenAPI types:
    - empty is `{ items: [], total: 0 }` or the route's schema equivalent
    - error is a 500 response
    - loading holds the response until the LoadingState test id is visible and the screenshot is taken, then releases it
  - It asserts `scrollWidth <= innerWidth` in the phone context and zero axe `color-contrast` violations. It stubs `navigator.vibrate` to record calls.
  - It writes images to the ignored `frontend/test-results/visual/` folder.
  - Lint including the guard, type check, unit tests including the token contrast test, build and the existing browser journeys all pass. No feature `api.ts` module is edited.
- **AC-13**: Documentation.
  - In step 1, the "preserve DESIGN.md" and "one dark theme" lines in `frontend/AGENTS.md` and `docs/frontend-standards.md` are amended to point at this spec.
  - At close out, `DESIGN.md` and `docs/frontend-standards.md` describe the new system, the anti slop rules and both themes.

## Decision

**Chosen option**: Option 2, a new token layer with screens migrated one at a time (a strangler migration inside one stylesheet). The old CSS is split: class rules go into a `legacy` layer ranked above utilities, and element rules go into `base` below utilities.

**Revised 2026-09-30**: the first plan put the whole old stylesheet in a layer below utilities. That changed the layout of about 170 elements, because about 140 `className` sites mix old classes with Tailwind utilities, and the old unlayered rules had been silently beating those utilities. Ranking the class rules above utilities keeps unmigrated screens identical. Isolation of migrated screens now comes from the guard (migrated files carry no legacy class) instead of from layer order. Details: [rationale.md](rationale.md#old-css-layer-revision-2026-09-30).

The tokens, the guard, the `legacy` layer and the resized primitives land first. Tailwind's default scales and the old Button names stay available until close out. Each screen then moves onto the new system and deletes its legacy selectors in the same change, so the app keeps working at every step.

**Design source**: this spec plus the reference patterns in [rationale.md](rationale.md). Mobbin was requested but could not be used (the MCP needs a paid plan and the site needs a sign in the automated browser could not complete). `/develop` builds from the values here.

**Implementation skills**: none installed for this area. The user level `impeccable` skill is available for UI critique but is not a project skill.

## Feature design

**Data model sketch**: no database change. Client state only:
- `rqs.theme` in local storage, holding `light` or `dark`, or absent.
- The connection store, held in memory: `status` (`ok`, `checking` or `unreachable`), `lastOkAt` (a timestamp or null) and `message` (a safe string).

**State transitions**:

- Theme: absent (dark until close out, then follows the OS live) becomes `light` or `dark` on toggle. The toggle has two states, uses the lucide sun and moon icons, and labels itself "Switch to light theme" or "Switch to dark theme".
- Connection: `ok` becomes `unreachable` on a network error, timeout or 502 to 504. `unreachable` becomes `checking` on each poll or on Retry. `checking` becomes `ok` on a 200, and returns to `unreachable` otherwise.
- Press: CSS `:active` only. Vibration fires on `pointerdown`.

**Color tokens** (you approved these values; the rows marked with an asterisk were adjusted or added after the contrast checks):

| Token | Dark | Light | Use |
|---|---|---|---|
| `--background` | `#0b0c0e` | `#f7f7f8` | page |
| `--surface` | `#131518` | `#ffffff` | cards, sidebar, tab bar |
| `--surface-raised` | `#1a1d21` | `#ffffff` | popovers (light relies on the shadow) |
| `--surface-hover`* | `#1a1d21` | `#f1f2f3` | hover rows and hover ghost buttons |
| `--overlay`* | `rgb(0 0 0 / 60%)` | `rgb(0 0 0 / 40%)` | Sheet backdrop |
| `--border` | `rgb(255 255 255 / 8%)` | `rgb(0 0 0 / 8%)` | hairlines, table and divider lines only |
| `--border-strong`* | `rgb(255 255 255 / 40%)` | `rgb(0 0 0 / 45%)` | input and control boundaries, about 3.8:1 and 3.3:1 |
| `--foreground` | `#e6e7e9` | `#16181b` | body text |
| `--foreground-muted` | `#9a9ea6` | `#5d6269` | secondary text, all 12px meta text, placeholders |
| `--foreground-subtle` | `#6b7079` | `#8a8f97` | decorative icons only, never readable text or disabled content |
| `--accent` | `#4b8bd4` | `#2a63b5` | links, selection, focus ring |
| `--accent-fill` | `#2b62ad` | `#2a63b5` | primary button fill |
| `--accent-foreground` | `#ffffff` | `#ffffff` | text on accent and danger fills |
| `--accent-fill-hover` | `color-mix(in oklab, var(--accent-fill), black 6%)` | same formula | primary hover |
| `--accent-fill-pressed` | `color-mix(in oklab, var(--accent-fill), black 12%)` | same formula | primary pressed |
| `--success` | `#3f9a5e` | `#2e7d4a` | status text and icons on a surface, always with a label |
| `--warning`* | `#c48a2a` | `#8f6210` | status text and icons on a surface, always with a label |
| `--danger`* | `#d9625a` | `#b23c33` | status and error text on a surface, always with a label |
| `--danger-fill`* | `#b23c33` | `#b23c33` | destructive button fill, white text at about 5.9:1 |

Status badges use status colored text and a 1px status colored border on the surface. They never use white text on a status fill. Hover and pressed fills for secondary, outline, ghost and destructive use the same `color-mix` formula on their own base color (`--surface`, `--surface-hover` or `--danger-fill`).

**Other tokens**: `--shadow-popover` is `0 1px 2px rgb(0 0 0 / 40%)` in dark and `0 1px 2px rgb(0 0 0 / 6%)` in light. `--radius-control` is 4px and `--radius-card` is 8px. `--disabled-opacity` is 0.5. `--transition-fast` is 150ms and `--transition-press` is 100ms. Each theme selector also sets `color-scheme`.

**Approved Tailwind keys** (defined in step 1 alongside the defaults, and the only keys left after the close out reset):
- **Spacing.** `1`, `2`, `3`, `4`, `6`, `8`, `12` and `16` map to 4, 8, 12, 16, 24, 32, 48 and 64px. These named sizes are also in the spacing namespace, so `h-*`, `w-*`, `size-*` and `min-h-*` can use them:

  | Key | Size |
  |---|---|
  | `control-sm` | 32px |
  | `control-md` | 40px |
  | `control-lg` | 48px |
  | `row-header` | 36px |
  | `row` | 44px |
  | `tabbar` | 56px |
  | `node-h` | 80px |
  | `node-legacy` | 220px |
  | `sidebar` | 224px |
  | `node` | 288px |
  | `panel` | 320px |

  The fractions and `full`, `screen`, `dvh`, `auto`, `px` and `0` stay allowed.
- **Text.** Each key sets a size and line height:

  | Key | Size and line height | Use |
  |---|---|---|
  | `xs` | 12px / 16px | meta and badges |
  | `sm` | 14px / 20px | body and controls |
  | `base` | 16px / 24px | section titles |
  | `lg` | 20px / 28px | page titles |
  | `xl` | 24px / 32px | page hero |

- **Colors.** Only the token names in the color table.

Padding and margins use multiples of 8. The 4px and 12px steps are for gaps between an icon and its label and inside badges. The font stays Inter, with weights 400, 500 and 600 and tabular numerals for metrics. Icons are lucide at 16px or 20px.

**Anti slop rules** (enforced by review, the guard and the checklist): no gradients, no glow or blur shadows, no glass or backdrop blur, no sparkle or magic icons, no purple or violet hue, and no colored card backgrounds. The accent covers under 5 percent of any screen (checklist item). Status colors never appear without a text label.

**Layout rules**:

- **Breakpoints.** Below 768px is mobile. 768 to 1151px is tablet, where inspectors and settings panels stack below their content. 1152px and above is desktop.
- **Shell.** The sidebar is 224px, the header 48px, and page gutters 24px on desktop and 16px on mobile. The mobile tab bar is 56px plus the safe area, and main content gets matching bottom padding.
- **Tables.** Data rows are 44px, header rows 36px and cell padding 16px. Tables scroll inside a labeled region, never the page.
- **Panels.** Node settings and evidence inspectors are 320px on desktop and full width below tablet.
- **Control clusters.** The editor toolbar, Playground composer and retrieval settings are centered, with mirrored left and right groups. The primary action is at the right end on desktop and full width at the bottom on mobile.
- **Mobile primary actions.** These live in the bottom two thirds of the viewport. Sticky bottom action bars sit above the tab bar.

**Component inventory**:

| Component | Location | Status |
|---|---|---|
| Button (3 sizes, 6 variants, icon prop, loading, `aria-disabled`, CSS pressed and touch sizing, vibration, deprecated aliases for `default`, `xs`, `icon`, `icon-xs`, `icon-sm`, `icon-lg` until close out) | `src/components/ui/button.tsx` | resize and extend |
| Input, Textarea, Native Select, Checkbox (40px, 48px on touch) | `src/components/ui/` | resize |
| Table, Badge, Tabs, Alert, Skeleton, Progress, Accordion, Separator | `src/components/ui/` | restyle to tokens |
| Sheet and Tooltip | `src/components/ui/` | add with `npx --yes shadcn@4.21.0 add sheet tooltip`, then normalize to approved keys in the same step |
| PageHeader (title, meta, one primary action) | `src/components/PageHeader.tsx` | new |
| EmptyState, ErrorState, LoadingState (each with a test id) | `src/components/states/` | new |
| StageCard | `src/features/workspace/components/` | new |
| `summarizeNodeConfig` | the pipeline canvas component folder | new |
| BottomTabBar, ThemeToggle, `useTheme`, DisconnectedBanner, Clerk appearance builder | `src/app/` | new |
| Connection store | `src/lib/connection.ts` | new |
| Theme init script | `frontend/public/theme-init.js` | new |
| StatusBadge, Pagination, AnswerText, RetrievalSettingsForm | `src/components/` | restyle |

**API surface**: no new endpoints. The shell polls the existing `GET /api/ready`. Overview calls the existing exported list functions in the feature `api.ts` modules and reads the `total` field of each page (calling them is allowed; editing them is not).

**Value sourcing**:

| Action | Value produced or displayed | Source |
|---|---|---|
| Pre paint | active theme | `rqs.theme` if it is `light` or `dark`; else `dark` until close out, then `matchMedia('(prefers-color-scheme: light)')` |
| Toggle | new theme | the opposite of the current `data-theme`, written to `rqs.theme` |
| Other tabs | active theme | the `storage` event on `rqs.theme` |
| Touch sizing | control height | CSS `@media (pointer: coarse)` |
| Vibration | allowed | `typeof navigator.vibrate === 'function'` and `matchMedia('(pointer: coarse)')` at `pointerdown` |
| Clerk theme | appearance variables | `getComputedStyle(document.documentElement)` for four tokens, rebuilt on theme change |
| Banner | status, message, last contact | the connection store, fed by `api.ts` as in AC-7 |
| Prepare card | count text | "N documents · M ready indexes": the documents list `total`, and the index list `total` filtered to status `ready` |
| Prepare card | state | 0 documents is empty ("No documents"); documents with no `ready` index is in progress ("Needs indexing"); a `ready` index is ready |
| Prepare card | button | "Upload documents", which goes to the Knowledge route |
| Ask card | count and state | "N answer pipelines": the pipelines list `total` for the answer kind; 0 is empty and 1 or more is ready |
| Ask card | button | "Ask a question", which goes to the Playground route |
| Compare card | count text | "N datasets · M completed runs": the datasets list `total`, and experiments with status `succeeded` |
| Compare card | state | no dataset is empty; a dataset but no `succeeded` experiment is in progress; a `succeeded` experiment is ready |
| Compare card | button | "Run experiment", which goes to the Experiments route |
| Overview primary | which card | the first loaded card that is not ready, else Compare; none until all requests settle |
| Node card | summary line | `summarizeNodeConfig(kind, config)`, one format per node kind |
| Bottom tabs | active tab | the parsed hash route from `src/app/navigation.ts` and the AC-5 rules |
| Visual journey | project id | in `beforeAll`, a context from `browser` creates one project through the UI and reads the id from the hash, then shares it through a module variable |
| Visual journey | routes and requests | the `MIGRATED_ROUTES` table in `visual.spec.ts` |
| Visual journey | editors | opened through "New pipeline" for each kind |
| Legacy parity | routes | every Studio route (the full list in AC-8), including both pipeline editors, dark only |
| Legacy parity | widths | 1280px desktop, 820px tablet and the `devices['iPhone 13']` phone context |
| Legacy parity | data | the project named by `PARITY_PROJECT_ID`, seeded once with one TXT document indexed through the deterministic providers (`compose.index-e2e.yaml`), one pipeline of each kind and one dataset; record and compare reuse it and never recreate it |
| Legacy parity | stable render | awaits `document.fonts.ready` and fixes time with `page.clock.setFixedTime` before reading styles |
| Legacy parity | element identity | the DOM path from `body`: tag name plus `nth-child` index at each level. A path present in only one run counts as a change |
| Legacy parity | compared values | every longhand property from `getComputedStyle`, except `transition*` and `animation*`, plus `getBoundingClientRect()` compared with a 0.5px tolerance; for `::before`, `::after` and `::file-selector-button`, the properties `content`, `display`, `color`, `background-color`, `width`, `height`, `margin` and `padding` |
| Legacy parity | baseline | `PARITY_MODE=record` writes one JSON file per route and context to the ignored `frontend/test-results/parity/baseline/`; `PARITY_MODE=compare` reads it |
| Guard | legacy class names | base classes parsed with `postcss` from `@layer legacy` in `styles.css` at lint time |
| Guard | migrated files | the `MIGRATED_PATHS` array (files or directory prefixes) in `scripts/check-structure.mjs` |
| Guard | exempt wrapper classes | the `SCOPE_CLASSES` array in `scripts/check-structure.mjs` |

**Key invariants**:

- No feature `api.ts`, `model.ts`, controller hook or backend file is edited in this feature.
- Saved pipeline graphs and node coordinates are never rewritten.
- `LEGACY_ALLOWANCE` equals the real violation total and only goes down.
- A screen's legacy selectors are deleted in the same change that migrates it.
- A migrated file names no class defined in `@layer legacy` other than the `SCOPE_CLASSES` wrappers, so the above utilities rank of `legacy` can never reach a migrated element. Every legacy rule needs a non wrapper class to match, because descendant selectors are all scoped under a feature class.
- `@layer legacy` holds only rules whose selectors all contain a class. Element rules live in `base`.
- Step 1 changes no computed style on any route (legacy parity check at zero).
- Browser storage holds only the theme word.

**Security model**: unchanged. Authorization and project scoping stay server side. The widget keeps its trust boundary and shares no code with Studio.

**Configuration required**: none. The only dependency added is `@axe-core/playwright`, as a dev dependency pinned to an exact version.

**Critical test scenarios**:

- **Theme.** No stored value loads dark. Toggle to light, reload and stay light. A second tab follows through the storage event. After close out, no stored value follows an emulated OS change. Verifies **AC-2**.
- **Contrast tokens.** The Vitest fails if any color table pair drops below its ratio. Verifies **AC-2**.
- **Vibration.** A Vitest with a stubbed `navigator.vibrate` and a coarse `matchMedia` sees one call per primary or destructive `pointerdown` and none for other variants. Verifies **AC-4**.
- **Overview.** The strip never holds more than one primary button. A fresh project shows Prepare empty with the only primary button. After a `ready` index, Ask carries it. A failed datasets request shows Retry on Compare only, and no primary button appears before all requests settle. Verifies **AC-6**.
- **Disconnected.** Intercept requests with a 502 and see the banner with "No successful response yet". Restore them, press Retry, see "Checking…", then the banner clears. Verifies **AC-7**.
- **Touch.** In the iPhone context, sm and md buttons measure 48px and every tab `boundingBox()` is at least 44px. Verifies **AC-3** and **AC-5**.
- **Disabled.** A disabled Button has `aria-disabled="true"`, stays focusable and ignores click and Enter. The 8 existing `toBeDisabled()` assertions become attribute checks. Verifies **AC-3**.
- **Legacy parity.** After the step 1 split, `PARITY_MODE=compare` reports zero changed elements on every route in both contexts. A deliberate test edit (moving one class rule into `base`) makes it fail and name the route, DOM path, property, old value and new value. Verifies **AC-1**.
- **Legacy isolation.** Adding a legacy class name to any string in a file in `MIGRATED_PATHS`, or an element only selector such as `h2 { … }` inside `@layer legacy`, each fail `npm run lint`. `app-shell` in a migrated shell file and `selected` in a React Flow node both pass. Verifies **AC-1**.
- **Guard.** A hex literal, a `text-[13px]`, a `p-5`, a `bg-purple-500` after close out, or a `style={{ color: 'red' }}` each fail `npm run lint`. A `style={{ '--progress': x }}` passes. Verifies **AC-1**.
- **Canvas.** The default answer template opens with no node overlap at 288 by 80. A saved horizontal graph keeps 220px nodes and its coordinates. Verifies **AC-9**.
- **Visual.** Every migrated route produces its images with no overflow and no contrast violations. Verifies **AC-12**.
- **Auth and permission.** Unchanged, covered by existing tests.

## Build plan

This follows Tracer Bullet: steps 1 to 3 push one verified thread from tokens through the shell and Overview. Steps 4 to 6 widen it, and every step runs the visual journey on the routes migrated so far.

1. Foundation.
   - Add the token block with markers and add the approved keys next to the Tailwind defaults, and add `theme-init.js` (dark fallback), `useTheme`, the ThemeToggle component (built but not rendered) and `viewport-fit=cover`.
   - Split the old CSS (tracer order, so each move is proven before the next):
     1. Build `e2e/legacy-parity.spec.ts` and record the baseline on the unchanged tree.
     2. Add the layer order statement and move the class rules into `@layer legacy`, the element rules into `@layer base`, the `footer` rule into `.create-project-footer` and the four React Flow overrides into the vendor block.
     3. Run the parity compare. For each changed element, apply the AC-1 dead utility rule, or move a rule that now loses to React Flow into the vendor block. Never put an old element rule back above utilities. Repeat until the diff is zero.
   - Build the guard with `LEGACY_ALLOWANCE` seeded from the real total, the legacy selector, `MIGRATED_PATHS` and `SCOPE_CLASSES` checks, and the token contrast Vitest.
   - Scaffold `visual.spec.ts` with axe for Projects, dark only.
   - Amend the "preserve DESIGN.md" and "one dark theme" lines to point at this spec.
   - Keep the manual dark pass over every route as a backstop for states the parity run does not render.

   Satisfies **AC-1**, **AC-2**, **AC-12**, **AC-13**.
2. Primitives.
   - Resize and extend them with deprecated aliases, CSS touch sizing, `:active`, `aria-disabled` and vibration.
   - Add Sheet and Tooltip and normalize them. Add PageHeader and the three state components.
   - Convert the 8 `toBeDisabled()` assertions.

   Satisfies **AC-3**, **AC-4**, **AC-10**.
3. Shell and Overview.
   - Build the sidebar, header, BottomTabBar with the More sheet and composer focus hiding, the connection store wired from `api.ts`, and DisconnectedBanner.
   - Build the Overview StageCards and the Clerk appearance builder.
   - Migrate Projects and Overview, add their files and the shell files to `MIGRATED_PATHS` (the shell keeps `app-shell` through `SCOPE_CLASSES`), extend the journey to both themes with state interception, and lower the allowance.

   Satisfies **AC-5**, **AC-6**, **AC-7**, **AC-8**, **AC-12**.
4. Migrate Knowledge Base, add its files to `MIGRATED_PATHS`, then extend the journey and lower the allowance. Satisfies **AC-8**, **AC-10**.
5. Migrate Playground and Experiments, add their files to `MIGRATED_PATHS`, then extend the journey and lower the allowance. Satisfies **AC-8**, **AC-10**.
6. Migrate the rest.
   - Migrate both pipeline editors, the React Flow vendor block, the node cards and `summarizeNodeConfig`.
   - Then migrate the Pipelines list, Deployments, Connections and Settings.
   - Render the ThemeToggle in the header now that every route is migrated, so you cannot reach a half styled light theme earlier.
   - Add their files to `MIGRATED_PATHS`, extend the journey and lower the allowance.

   Satisfies **AC-8**, **AC-9**, **AC-10**.
7. Widget. Add the token variables, the light palette, a light and dark accent pair for each appearance option, the launcher and the targets. Run the widget tests and the size check. Satisfies **AC-11**.
8. Close out.
   - Remove the `legacy` layer (and `legacy` from the layer order statement), `SCOPE_CLASSES`, the parity spec, the Button aliases and the theme aliases. Prune the moved element rules in `base` to those still needed.
   - Reset the Tailwind spacing, text and color scales to the approved keys, and set the allowance to zero.
   - Switch the theme fallback to `prefers-color-scheme`.
   - Rewrite `DESIGN.md` and `docs/frontend-standards.md`, and run every check.

   Satisfies **AC-1**, **AC-2**, **AC-12**, **AC-13**.

## Consequences

**Positive**:

- Unmigrated screens keep their exact look through step 1, proven by a zero diff rather than by eye.
- The old global element rules can no longer override utilities on migrated screens.
- One token block, the approved keys and one guard keep the system from drifting.
- Contrast is checked automatically for text (axe) and for boundaries (the token Vitest).
- Mobile gets thumb reachable navigation and 48px controls without any workflow change.
- The stylesheet shrinks with every migrated screen.

**Negative / tradeoffs**:

- Light mode is not the fallback until close out, and only migrated routes are verified in light before then.
- Two visual languages coexist during the migration.
- The guard parses class strings with regexes, so it can miss dynamic class names built at runtime. Review covers those.
- Vibration works only on Android Chrome, and not on the first tap.
- About a dozen routes times two contexts times two themes, plus states, is a large manual checklist review. No pixel baselines catch regressions automatically.
- Adds one dev dependency (`@axe-core/playwright`).
- Because `legacy` outranks utilities, isolation of migrated screens rests on the guard, not on the cascade. A legacy class added through a dynamic class name slips past the regex guard, and review has to catch it.
- About 140 utilities stay dead (overridden by legacy class rules) until their screen migrates. They look like working styles but are not, which can mislead anyone editing an unmigrated screen.
- Wrapper classes such as `app-shell` stay exempt from the guard until close out, so a legacy rule scoped only to a wrapper (with no feature class) could still reach a migrated element. Review covers those.
- The parity check covers only what renders on each route with the seeded project. Dialogs, error states and the Clerk account widgets (never rendered, because the test stack runs local auth) are covered by the manual dark pass.

**Neutral**:

- The `DESIGN.md` authority changes, and the `.lavish/` artifacts become history.
- The widget gains a light palette that follows the visitor's OS, not the host page.
- Existing e2e journeys that assert on class names or exact layout may need selector updates.

## Migration plan

**Strategy**: a strangler migration within the single stylesheet, one screen per change, with no feature flag.
**Phases**:
1. Tokens, the guard, the split of the old CSS (class rules in `legacy` above utilities, element rules in `base`) and primitives land. Tailwind defaults and old Button names stay available, and the fallback theme is dark.
2. Each screen migrates, deletes its legacy selectors and lowers the allowance to the new total.
3. At close out, the legacy layer, the aliases and the Tailwind defaults are removed, and the OS theme fallback turns on.

**Rollback**: revert the screen's change, and the `legacy` layer and aliases keep other screens intact. Reverting step 1 restores the dark only app.
**Risks**:
- Moving rules between layers can change which rule wins. The first attempt (legacy below utilities) moved about 170 elements. The control is the legacy parity check at zero changed elements, plus the manual dark pass for unrendered states.
- `!important` flips across layers (an earlier layer's important declaration wins). The reduced motion `transition: none !important` rule in `base` therefore outranks any important utility, which matches its intent. The three other important declarations stay in `legacy`.
- React Flow variables must be remapped in both themes.
- User built graphs with nodes closer than 288px apart in a vertical layout may overlap and need a manual re-layout. Coordinates are never rewritten automatically.

## Follow-up

- [ ] Consider committing a `toHaveScreenshot` baseline for desktop dark after close out, so regressions are caught without manual review.
- [ ] If Mobbin becomes available, add its references to `rationale.md` and reconcile any differing pattern.
- [ ] After close out, `/sync` should record the token guard rule in `frontend/AGENTS.md`.

## Rationale

Reasoning, options, the UI audit, the reference evidence and both cross check records: see [rationale.md](rationale.md).
