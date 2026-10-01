# 0002. Verify steps

Run these after each build step on the routes migrated so far, and in full at close out. They back AC-2 and AC-12 in [index.md](index.md).

## Visual journey

1. Stop the Vite dev server if it is running. The isolated stack's frontend serves on the same port (`E2E_UI_PORT`, default 5273), and two frontends on one port make it unclear which build is under test.
2. From the repository root, start the isolated browser stack with `compose.e2e.yaml` in its own Compose project, such as `rag-studio-e2e`. Never use the development project.
3. From `frontend/`, run the visual journey with `E2E_BASE_URL=http://127.0.0.1:5273 npx playwright test e2e/visual.spec.ts`.
4. The journey does the following:
   - Creates one project in `beforeAll` and reads its id from the hash.
   - Visits each route in the `MIGRATED_ROUTES` table twice: in a 1280px desktop context and in a `devices['iPhone 13']` context (touch, coarse pointer).
   - Runs dark only in steps 1 and 2, and both themes from step 3 onward. The theme is set by `addInitScript` writing `rqs.theme`.
   - Forces states on each route's primary list request with `page.route()`, using fixtures typed from the OpenAPI types. Empty is an empty page with a total of 0. Error is a 500. Loading holds the response until the LoadingState test id is visible and the screenshot is taken, then releases it.
   - Stubs `navigator.vibrate` to record calls.
   - Writes `<route>-<context>-<theme>[-<state>].png` into the ignored `frontend/test-results/visual/` folder.
5. The journey fails on any axe `color-contrast` violation, or when `scrollWidth > innerWidth` in the phone context.

## Legacy parity (step 1)

_Retired at close out (2026-10-01): the `legacy` layer and `e2e/legacy-parity.spec.ts` are gone. Kept as a record of how step 1 was proven._

This proves the old CSS split changed nothing. It backs AC-1.

1. Start the isolated stack from the tree before the split, with `compose.e2e.yaml` plus `compose.index-e2e.yaml` (deterministic providers) in the `rag-studio-e2e` project. Seed the parity project once (one TXT document indexed, one pipeline of each kind, one dataset) and note its id as `PARITY_PROJECT_ID`.
2. From `frontend/`, run `PARITY_MODE=record PARITY_PROJECT_ID=<id> E2E_BASE_URL=http://127.0.0.1:5273 npx playwright test e2e/legacy-parity.spec.ts`.
3. Apply the split. Rebuild only the frontend container in the same Compose project (`up --build -d frontend`), keeping the database as it is, and run the same command with `PARITY_MODE=compare`.
4. The run fails on any changed element (including an element present in only one run) and lists the route, context, DOM path, property, old value and new value. Fix each by the dead utility rule in AC-1, or by moving a rule that now loses to React Flow into the vendor block, then compare again. Never put an old element rule back above utilities to make the diff pass.
5. Step 1 is done only at zero changed elements. In later steps you may run it again for unmigrated routes (record before the change, compare after); step 2 changes primitives on purpose, so review its diff rather than expecting zero.

## Checklist per screenshot (visual review)

These items are not automated:

- Page gutters are 24px on desktop and 16px on the phone.
- Every visible spacing step is 4, 8, 12, 16, 24, 32, 48 or 64px. The 4px and 12px steps appear only inside badges or between an icon and its label.
- Only the five type sizes appear: page hero 24px, page title 20px, section title 16px, body 14px, meta 12px.
- Controls are 40px on desktop and 48px on the phone, for both sm and md. Icon buttons have a 44px hit area.
- Status badges use colored text and a border on the surface, never white text on a status fill.
- The accent covers under 5 percent of the screen and appears only on the primary action, focus, selection and links.
- There is no purple, gradient, glow, blur or glass anywhere.
- Status colors always carry a text label.
- Left and right control groups mirror each other. The primary action is at the right end on desktop and full width at the bottom on the phone.
- On the phone, the bottom tab bar has five tabs and is 56px tall. The active tab is marked (Pipelines on the editors, More for its items). The bar hides while the Playground composer has focus.
- Every main route is reachable in at most two taps from Overview.
- Before close out, only migrated routes are expected to look right in the light theme, and the default theme is dark.
- In step 1, check every route once in dark after the old CSS split, looking at dialogs, populated lists and error states that the parity run does not render.

## Automated checks

From `frontend/`, run `npm run format:check`, `npm run lint` (includes the token guard and the legacy allowance check), `npm run typecheck`, `npm run test -- --run` (includes the token contrast test) and `npm run build`. Then run the existing browser journeys against the isolated stack.

After step 7, run `npm run typecheck`, `npm run test` and `npm run build` from `widget/`.

When you are done, stop the isolated stack with `down` on the same project. Do not delete volumes.

## Record

Record the dated result and any off grid finding in `docs/reviews/`, through `/check verify workspace UI redesign`.

## Step 2 · primitives · updated 2026-09-30

_Steps derived from AC-3, AC-4 and AC-10. `/check verify` runs these; `/test` locks the durable ones._

### UI / manual

- [ ] In a 1280px context, render a Button outside `.app-shell` (or on a migrated route): sm, md and lg measure 32, 40 and 48px high; with `icon` each is square at its height → AC-3
- [ ] In the `devices['iPhone 13']` Chromium context, sm and md measure 48px and their icons stay 16px. On unmigrated routes a legacy `.app-shell` mobile rule still holds them at 44px until step 3 → AC-3
- [ ] Tab to any Button: a 2px accent outline with a 2px gap appears → AC-3
- [ ] Hold the pointer down on a primary Button: the fill darkens and it drops 1px. With reduced motion emulated, the fill still changes but it does not move → AC-3, AC-4
- [ ] Open Experiments with no dataset: "Run experiment" has `aria-disabled="true"`, can take focus, sits at the disabled opacity, and clicking it or pressing Enter does nothing → AC-3
- [ ] A Button with `loading` shows a centered spinner at the same width, has `aria-busy="true"`, keeps its accessible name, and ignores clicks. Under reduced motion the spinner is still → AC-3
- [ ] Stub `navigator.vibrate` in the phone context: pressing a primary or destructive Button calls it once with 10, while outline, ghost and disabled Buttons do not → AC-4
- [ ] Input, Textarea and NativeSelect measure 40px (48px on touch), use 16px text on phones and 14px from 768px up; a Checkbox has a 40px hit area (48px on touch) → AC-3
- [ ] Open a Sheet: the backdrop uses `--overlay`, the panel is 320px wide on the right (full width on phones), and the close button is at least 44px → AC-3
- [ ] Playground at 1280px with the settings panel open: the toolbar wraps without overlapping text → no regression

### Commands

- [ ] `npm run test -- --run tests/components` → Button, states and PageHeader tests pass → AC-3, AC-4, AC-10
- [ ] `npm run lint` → the token guard reports 420 against an allowance of 420 → AC-1

### Acceptance-criteria coverage

- AC-3: sizes, touch, focus, pressed, disabled, loading and field steps
- AC-4: the vibration and reduced motion steps
- AC-10: the component tests (LoadingState, EmptyState with one action, ErrorState with Retry); route level use starts with step 3

## Step 3: shell and Overview · updated 2026-09-30

_Steps derived from AC-5, AC-6, AC-7, AC-8 and AC-12 plus the Value sourcing rows for this step. `/check verify` runs these; `/test` locks the durable ones._

### UI / manual

- [ ] At 1280px on a project route, the sidebar measures 224px and the header 48px; the project switcher keeps the current page when you switch → AC-5
- [ ] In the iPhone context on a project route, no hamburger shows; the header holds the project name linking to `#/`; a 56px tab bar shows Overview, Knowledge, Pipelines, Playground and More → AC-5
- [ ] Open a pipeline editor on the phone: Pipelines has `aria-current="page"`; open Experiments, Deployments and Settings: More has it → AC-5, Value sourcing "Bottom tabs"
- [ ] Tap More: a bottom sheet lists Experiments, Deployments, Connections, Settings and All projects; Connections opens Settings scrolled to Source connections → AC-5
- [ ] Focus the Playground question field on the phone: the tab bar hides; blur it: the tab bar returns → AC-5
- [ ] On the Projects list, no tab bar renders at any width → AC-5
- [ ] A fresh project's Overview shows three stage cards; Prepare reads "0 documents · 0 ready indexes", "No documents", and carries the only primary button → AC-6, Value sourcing "Prepare card"
- [ ] Upload and index one TXT document: Prepare reads "1 document · 1 ready index", "Ready", and Ask now carries the primary button ("0 answer pipelines") → AC-6, Value sourcing "Prepare card", "Ask card", "Overview primary"
- [ ] Upload a document but do not index it: Prepare reads "Needs indexing" → Value sourcing "Prepare card" state
- [ ] Save an answer pipeline: Ask reads "1 answer pipeline", "Ready"; Compare now carries the primary; import a dataset: Compare reads "No completed runs"; finish an experiment: all three ready and the primary stays on Compare ("Run experiment") → AC-6, Value sourcing "Compare card"
- [ ] With `page.route` failing `/datasets?` with a 500: Compare shows an inline error with Retry, the other cards load, and no primary appears before all three settle → AC-6
- [ ] From Overview, reach every main route in at most two taps on the phone (tab or More then item) → AC-6
- [ ] Stop the backend (or route `/api/` to 502): a banner under the header reads "Cannot reach the server", the safe message and "No successful response yet"; it polls `/api/ready` 5 seconds after each response only while the tab is visible → AC-7
- [ ] Restore the backend and press Retry: "Checking…" and a spinning Retry, then the banner clears; a 404 or 422 elsewhere never shows the banner → AC-7
- [ ] In Clerk mode, toggle `data-theme` in devtools: the Clerk user button and sign in modal take `--accent-fill`, `--surface`, `--foreground` and `--border-strong` from the active theme → AC-8, Value sourcing "Clerk theme"
- [ ] Projects and Overview use 24px page padding on desktop and 16px on the phone, with no legacy class in their files → AC-8

### Commands

- [ ] `npm run lint` in `frontend/` → guard at 357, no legacy class in `MIGRATED_PATHS` → AC-1, AC-8
- [ ] `npm run typecheck`, `npm run test -- --run` and `npm run build` in `frontend/` → all pass (197 tests) → AC-12
- [ ] With Vite on 5273 in local auth mode (`VITE_CLERK_PUBLISHABLE_KEY=`) proxied to the isolated backend (`API_PROXY_TARGET=http://127.0.0.1:8001`), `E2E_BASE_URL=http://127.0.0.1:5273 npx playwright test e2e/visual.spec.ts` → 34 pass: Projects and Overview in both themes and four states, tab bar targets, disconnected banner → AC-5, AC-6, AC-7, AC-12
- [ ] Same setup, `npx playwright test e2e/workspace.spec.ts e2e/projects.spec.ts` → pass with the tab bar path → AC-5

### Acceptance criteria coverage

- AC-5: sidebar, header, tab bar, More sheet, composer hiding, no tab bar on Projects
- AC-6: stage copy and counts, states, single primary, per card Retry, two tap reach
- AC-7: banner, polling, Retry, Checking…, statuses that do and do not trip it
- AC-8: Projects and Overview migrated, Clerk appearance, padding
- AC-12: visual journey in both themes with forced states

## Step 5: Playground and Experiments · updated 2026-09-30

### UI / manual

- [ ] Open Playground at 1440 by 1000 with a published collection → the page does not scroll, messages scroll inside their region, and the composer bottom sits 24px above the viewport bottom → AC-8
- [ ] Toolbar → test mode on the left, the exact configuration under test centered (for example "Orchard answers · Version 1"), panel toggles on the right; below 768px they stack and the send action spans the width → AC-8
- [ ] Toggle Pipeline settings, Past questions and Sources & details → one 320px panel with its own title and Close; Escape closes it; the save and reset footer stays pinned while settings scroll → AC-8
- [ ] Resize to 1000px → the panel stacks under the conversation at full width → AC-8
- [ ] Project with no published collection → Playground shows "No prepared documents yet" with one primary "Upload and prepare documents" that opens the Knowledge Base upload → AC-10
- [ ] Block `/indexes` with a 500 → "We couldn’t load the Playground" with Retry; restore it and press Retry → the Playground loads without a page reload → AC-10
- [ ] Ask a question and press a citation → the matching source in the panel takes focus → AC-8
- [ ] Focus the composer on a phone → the tab bar hides, and the composer shows a 2px accent ring → AC-3, AC-5
- [ ] Experiments at 1280px → Dataset, Candidates and Metrics stage cards on the left, the 320px run summary sticky on the right; below 1152px the summary sits under the stages → AC-8
- [ ] Experiments with no experiments → "No experiments yet" empty state; block `/experiments` with a 500 → error with "Retry loading" → AC-10
- [ ] Open a completed comparison → Candidate summaries, Paired comparison and Per-question comparison are named regions with scrolling tables; select a question → the evidence panel takes focus and Close evidence returns → AC-8
- [ ] Both routes in light and dark → no gradients, no colored card backgrounds, status colors always beside text → AC-2, AC-8

### Commands

- [ ] `npm run lint` in `frontend/` → guard at 179, no legacy class in `MIGRATED_PATHS` → AC-1, AC-8
- [ ] `npm run typecheck`, `npm run test -- --run` and `npm run build` in `frontend/` → all pass (197 tests) → AC-12
- [ ] Same journey setup, `npx playwright test e2e/visual.spec.ts` → 82 pass, including Playground and Experiments in both themes and four states → AC-10, AC-12
- [ ] With `E2E_EMBEDDING_FIXTURE=1`, `npx playwright test e2e/playground.spec.ts e2e/experiments.spec.ts e2e/pipelines.spec.ts` → pass once the journeys wait for the index to be published (they currently move on while it is still publishing) → AC-12

### Acceptance criteria coverage

- AC-8: Playground and Experiments on shared primitives, layout rules and panels
- AC-10: loading, empty and error states with Retry on both routes and the comparison detail
- AC-12: visual journey extended to both routes

## Step 6: editors and remaining pages · updated 2026-10-01

_Steps derived from AC-1, AC-5, AC-8, AC-9, AC-10 and AC-12 plus the Value sourcing rows for this step. `/check verify` runs these; `/test` locks the durable ones._

### UI / manual

- [ ] Open a new answer pipeline at 1280px → a canvas sized by `--editor-canvas` with a 320px settings panel on the right; below 1152px the panel stacks under the canvas at full width → AC-8
- [ ] Editor toolbar → name, saved version and the draft badge on the left; Discard, Duplicate, Open Playground and Save on the right. Only one primary: Save while there are changes, Open Playground once a clean version is saved. On a phone the actions stack and the primary sits last at full width → AC-8
- [ ] At 390px the canvas tools (Nodes, Arrange vertically, Node settings) wrap onto their own rows and never overlap, and the canvas still pans between them → AC-8
- [ ] Default answer template → five node cards, each 288 by 80, 16px title, 20px icon, no overlap → AC-9
- [ ] Open a saved pipeline whose nodes are laid out horizontally → nodes stay 220px wide and keep their saved coordinates → AC-9
- [ ] Each node card shows one 12px muted summary line: Question "User input · single turn", Retriever "Vector · Top 5 · Choose documents" (then "Documents selected" once an index is picked), Prompt "Answer with evidence", LLM the model name or "Choose a model", Answer "Response + citations". Hover a truncated line → a Tooltip shows it in full → AC-9, Value sourcing "Node card"
- [ ] Select a node → a 2px accent outline inside the border and no layout shift; the icon turns accent → AC-9
- [ ] Toggle the theme → canvas background dots, edges, handles, controls and node cards follow both palettes → AC-9
- [ ] Open a missing pipeline id, or fail `/pipelines/options` with a 500 → the editor shows ErrorState with "Retry loading pipeline" → AC-10
- [ ] Ingestion editor at 1440 by 900 → the page does not scroll while the settings panel scrolls; stage buttons mark the active stage; the automatic sync panel spans canvas plus settings → AC-8
- [ ] Run an ingestion → node cards show Queued, Running now (spinning icon, still under reduced motion), Complete, Reused, Failed or Cancelled as a bordered status badge, never a colored card fill; the run bar shows a status badge, progress bar and Cancel run → AC-8, AC-2
- [ ] Stage settings → checkboxes are the Checkbox primitive with 44px or larger rows; notices use Callout; disclosure sections use the shared summary style → AC-3, AC-8
- [ ] On a phone or at 1024px, choose a stage → the settings panel scrolls into view (it stacks below 1152px) → AC-8
- [ ] Pipelines list → PageHeader with one primary "New answer pipeline" or "New ingestion pipeline"; rows show name, status badge and version line; forced empty, error (Retry) and loading states render → AC-8, AC-10
- [ ] Settings → Project, Documents and Models sections with intro on the left third on desktop; Source connections below; loading and error only (no empty state) → AC-8, AC-10
- [ ] Settings with no stored connections → only "No credentials are stored for this project." shows, no empty detail card; add one → the detail card appears with Test connection as the single primary → AC-8
- [ ] Deployments in local auth mode → ErrorState "We couldn’t load deployments" with Retry (the API serves organization projects only). In Clerk mode → list, create form, release history, keys and runs render, and status uses badges on the surface with no tinted backgrounds → AC-8, AC-10
- [ ] Signed out in Clerk mode → two pane landing on tokens with a 24px hero title; the Clerk modal follows the theme → AC-8
- [ ] Header → the theme toggle shows on every route at desktop and phone widths, switches without reload, and is labeled "Switch to light theme" or "Switch to dark theme" → AC-2, AC-5
- [ ] Close the Playground side panel → focus returns to the toolbar toggle that opened it → no regression

### Commands

- [ ] `npm run lint` in `frontend/` → "Token guard: 0 violations, allowance 0" and every source path in `MIGRATED_PATHS` → AC-1
- [ ] `npm run format:check`, `npm run typecheck`, `npm run test -- --run` (197 tests) and `npm run build` in `frontend/` → all pass → AC-12
- [ ] With Vite on 5273 in local auth mode proxied to the isolated backend, `npx playwright test e2e/visual.spec.ts` → all pass, including pipelines, both editors, deployments (error and loading) and settings in both themes → AC-10, AC-12
- [ ] Same setup with `E2E_EMBEDDING_FIXTURE=1`, `npx playwright test e2e/pipelines.spec.ts e2e/retrieval-settings.spec.ts e2e/ingestion-layout.spec.ts e2e/ingestion.spec.ts` → pass with the new test id selectors (the phone ingestion canvas is now 480px) → AC-12

### Acceptance criteria coverage

- AC-1: guard at 0, legacy rules deleted, all paths migrated
- AC-8: editors, Pipelines list, Deployments, Settings, Connections and the landing on shared primitives and layout rules
- AC-9: node card size, summary line, Tooltip, selection outline, token mapped React Flow variables
- AC-10: states on the Pipelines list, editors, Deployments and Settings
- AC-12: visual journey extended to the step 6 routes

## Steps 7 and 8: widget and close out · updated 2026-10-01

_Steps derived from AC-1, AC-2, AC-8, AC-11, AC-12 and AC-13. `/check verify` runs these; `/test` locks the durable ones._

### UI / manual

- [x] Clear `rqs.theme` from local storage, set the OS to light, load any route → the app renders light with no dark flash; switch the OS to dark → the app follows live without a reload → AC-2
- [x] Toggle the header theme, then change the OS theme → the stored choice wins and the OS change is ignored; a second open tab follows the toggle → AC-2
- [x] Block site storage and reload → the theme still follows the OS → AC-2
- [x] Signed out in Clerk mode, both themes → the landing and the Clerk sign in dialog use token colors (surface card, hairline border, popover shadow, accent primary, danger for errors); no contrast failures → AC-8, AC-2
- [x] Deployments, Website widget → the appearance preview iframe is 480px tall and at most 400px wide → AC-8
- [x] Knowledge Base alert and accordion chevrons → icons line up with the first text line, as before close out → AC-1
- [x] Widget frame with the OS in light, then dark, for blue, slate and green → panel, messages, composer and launcher follow the OS theme, not the host page; zero axe contrast violations → AC-11
- [x] Widget on touch → launcher 56px, close, send, Evidence, Check result again and Answer details are at least 44px; inline citation buttons are exempt (prose) → AC-11
- [x] Ingestion editor at 1440 by 900 and 1366 by 768 → the document never scrolls, the canvas keeps its size when you change stage, click a node or switch the source kind, and the settings panel scrolls on its own → AC-8

### Commands

- [x] From `frontend/`: `npm run lint` → "Token guard: 0 violations, allowance 0" and structure checks pass → AC-1
- [x] Add `.stray { color: inherit; }` or `@layer legacy { … }` to `styles.css`, run `npm run lint` → it fails naming the line; revert → AC-8
- [x] Use an unapproved key such as `p-5`, `text-2xl` or `bg-blue-500` in a component and build → no CSS is generated for it, and the guard reports it → AC-1
- [x] `npm run typecheck`, `npm run test -- --run`, `npm run format:check`, `npm run build` → all pass → AC-12
- [x] With the isolated stack and Vite on 5273 (see the project memory note), `E2E_BASE_URL=http://127.0.0.1:5273 npx playwright test` → all pass except the docs site journeys (need the docs server on 3000) and the credential free indexes case (needs a stack without embedding credentials) → AC-12
- [x] From `widget/`: `npm run typecheck && npm run test && npm run build` → pass, frame CSS under the 20 kB budget → AC-11
- [x] With the widget fixture running (`docs/development.md`, port 8000 free), `WIDGET_E2E=1 npm run test:e2e -- --grep widget` from `frontend/` → 18 pass → AC-11
- [x] `grep -rn "legacy\|SCOPE_CLASSES\|DeprecatedSize" frontend/src frontend/scripts` → only `--spacing-node-legacy` (the approved saved layout width) → AC-1

### Acceptance criteria coverage

- AC-1: guard, unapproved key, legacy grep and alert alignment steps
- AC-2: OS theme, toggle precedence, blocked storage and Clerk steps
- AC-8: layer guard, Clerk, widget preview size and ingestion layout steps
- AC-11: widget theme, targets, widget checks and widget journeys
- AC-12: static checks and the full browser suite
- AC-13: `DESIGN.md` and `docs/frontend-standards.md` describe the system (read them against this spec)
