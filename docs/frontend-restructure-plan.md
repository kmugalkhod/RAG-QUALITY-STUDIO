# Frontend restructuring plan: shadcn theming and centralized CSS

Status: implemented; final verification results are recorded below. This document supersedes the earlier suggestion to introduce CSS Modules or retain permanent feature stylesheets. The user wants centralized CSS, readable components, and actual reuse.

## 1. Outcome and scope

Use one application-owned stylesheet, `frontend/src/app/styles.css`, with shadcn-compatible semantic theme variables. Shared UI primitives own their Tailwind/CVA variants. Pages compose components and use token-based layout utilities. Necessary custom selectors have named sections in the central stylesheet. No component CSS files, feature CSS files, CSS Modules, or CSS-in-JS are part of the target.

Preserve the current charcoal/lavender design, Inter font, supported features, routes, saved versions, project isolation, evidence semantics, and separate `frontend/tests/` directory. This is a frontend restructuring task, not a redesign or backend/API migration. Keep the dark appearance as the initial theme; do not introduce a theme switch or promise an unverified light theme.

Third-party distributed CSS is an explicit exception to the one-file rule: React Flow's required package stylesheet is retained and imported once through the central CSS entry where supported by the installed build. Application overrides remain in the central stylesheet.

“One stylesheet” must not become “paste all 3,709 lines into a new file.” Success requires removing obsolete rules, fixing token wiring, replacing repeated control styling with shared components, and removing cross-feature overrides.

## 2. Evidence and verification limits

The pre-implementation tree contained 13 authored CSS files, approximately 3,709 lines. `linear-workspace.css` alone has 1,471 lines. Pipeline styles span that file, `app/styles/workspace.css`, and `features/pipelines/pipelines.css`.

Confirmed from source and the existing production CSS:

- `components.json` already enables CSS variables and points at `src/app/styles.css`; preserve that path and the existing new-york/Radix component convention.
- `@theme inline` currently defines literal green/light values. Generated `.bg-primary` uses `#285d48`; a later selector patches primary buttons to lavender. The final theme must remove this conflict.
- Broad `label`, `select`, and `nav` rules affect unrelated controls.
- `PipelineEditor` has a constant `running = false` with unreachable conditional branches.
- `playground/api.ts` exports an `ask` wrapper with no callers found in frontend source, unit tests, or browser tests. Remove that wrapper only; retain backend routes and historical data behavior.
- Workflow-node header/footer styling targets elements the current node renderer does not produce.
- Pipeline node defaults and template construction are repeated in the editor and Playground.
- `allPages` is a general pagination helper housed in the pipeline API but used across features.
- Playground run polling uses an interval that can start another request before the preceding request completes.
- The file named `Playground.test.tsx` currently exercises answer-result components rather than the full Playground controller.

Baseline review checks: lint, typecheck, and 40 tests across 11 files passed. Prior build passed with a roughly 513 kB JavaScript chunk warning. No complete browser-state audit or exhaustive CSS reachability analysis has been performed. These observations justify the plan; they do not establish that all candidate CSS is safe to delete.

## 3. Target organization and dependency boundaries

Keep the existing feature layout. The following was the proposed boundary map; the implementation retains page-local orchestration instead of creating forwarding-only toolbar/canvas/version hooks. Pipeline contracts and validation share `model.ts`, and no placeholder files or empty directories are created.

```text
frontend/
  src/
    app/
      App.tsx
      WorkspacePage.tsx
      WorkspaceSidebar.tsx
      navigation.ts
      useWorkspaceProjects.ts
      styles.css                 # only application-owned stylesheet
    components/
      ui/                        # shared styled primitives, Tailwind/CVA
        button.tsx
        input.tsx
        textarea.tsx
        label.tsx
        native-select.tsx
      Pagination.tsx             # shared only after callers migrate
      AnswerText.tsx
    features/
      pipelines/
        PipelineEditor.tsx       # composes editor responsibilities
        PipelineToolbar.tsx
        PipelineCanvas.tsx
        NodeSettings.tsx
        WorkflowNode.tsx
        usePipelineVersions.ts
        pipelineTemplate.ts
        validation.ts
        types.ts
        api.ts
      playground/
        Playground.tsx           # composes modes, input and results
        PipelineTestSettings.tsx
        RunHistory.tsx
        AnswerResult.tsx
        RetrievalTest.tsx
        usePipelineDraft.ts
        useQueryRun.ts
        api.ts
      documents/                 # keep existing inspectors
      experiments/               # keep comparison and dataset boundaries
      projects/
      retrieval/                 # reusable RetrievalSettingsForm + logic
    lib/
      api.ts                     # transport; separate project calls as needed
      pagination.ts
      utils.ts
  tests/                         # mirrors src responsibilities
  e2e/                           # isolated browser journeys
```

Rules:

- `app` composes features; shared `components/ui` and `lib` must not import feature implementation.
- Feature `api.ts` files handle transport and endpoint payloads. Pure validation, template creation, and editable-version conversion do not live in HTTP wrappers.
- Explicit reuse between related features is allowed: Playground can use pipeline domain functions and retrieval controls. Avoid introducing barrels or a generic framework just to hide these dependencies.
- Use descriptive parameter names such as `projectId`, `version`, and `node` when touching code. Do not rename unrelated files merely for uniformity.
- A component may own local interaction state. Hooks own cohesive request/state lifecycles; a huge hook returning every page setter is not an improvement.
- There is no arbitrary line-count limit. Extract where behavior, ownership, reuse, or testing becomes clearer.

## 4. Central shadcn theme

### Token model

Use semantic variables consumed by utilities through `@theme inline`, rather than literals in the mapping:

```css
@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
}
```

This is a wiring example, not the complete theme. Define all tokens used by adopted components, including muted/foreground, secondary/foreground, accent/foreground, card/foreground, popover/foreground, sidebar tokens and radii. Add success/warning/destructive state tokens where the existing product uses those states. Do not add chart or animation tokens without a consumer.

Apply theme scope at the document root so portaled overlays inherit it. Preserve the initial dark palette; avoid parallel definitions in `:root`, `.dark`, and `.linear-workspace` that disagree. Root defaults can represent the sole supported dark theme. Add a separate light palette only in a future explicitly scoped task.

Initial semantic mapping, subject to contrast and computed-style verification:

| Current meaning | Target token | Preserve initially |
| --- | --- | --- |
| Main surface | background | #181b21 |
| Main text | foreground | #e8eaf0 |
| Sidebar / secondary surface | sidebar, card where appropriate | #20242b |
| Quiet text | muted-foreground | #a5afbf |
| High-emphasis action | primary | #afa1ff |
| Text on primary | primary-foreground | #181b21 |
| Borders | border, input | #343b46 |
| Hover surface | accent / secondary according to use | #282d36 |
| Selected navigation | sidebar-accent / sidebar-accent-foreground | #302c49 / #afa1ff |
| Focus indicator | ring | verify current lavender contrast |

The old `--accent` means brand lavender; shadcn's `accent` commonly means an interaction surface. Map by meaning, not by matching variable names. Preserve the existing primary hover behavior through one shared button variant/token decision.

### Contents of styles.css

Keep this order explicit:

1. Tailwind and required vendor imports; deliberate cascade-layer ordering.
2. Font registration and semantic variables.
3. Tailwind token mapping and any necessary dark variant.
4. Small base layer: body defaults, box sizing, default borders/focus behavior, reduced motion, and shared document typography where truly global.
5. Named component sections for custom cases: safe answer markup, pipeline canvas/vendor overrides, and complex workspace/scroll geometry that utilities do not express clearly.
6. Responsive and accessibility rules beside their owning component section.

Use normal component rules in `@layer components` so utility precedence is deliberate. React Flow may require an explicitly ordered vendor layer or more specific scoped rules. Verify its required geometry/interaction styles before changing import layering. Normal unlayered declarations outrank normal layered ones; moving a rule into a layer is a behavior change and must be tested.

No permanent “overrides” section at the bottom. No `.linear-workspace .some-page .some-control` patches to fix a shared component. No selectors that identify a Button variant by matching generated Tailwind classes. No raw palette colors in feature components; use semantic utilities. Dynamic node coordinates and library-generated inline styles remain valid runtime data.

## 5. Shared components and readability

Start from the installed Button/CVA/Radix convention. Do not run a blanket latest-version shadcn reinitialization or overwrite existing components. Official examples may now target a different preset or dependency family; inspect compatibility first.

Introduce Input, Textarea, Label and native-select wrappers only as their real callers migrate. Preserve native select, file input, checkbox and numeric input semantics where they already work. A custom Select, Dialog, Form library, state library, or new animation dependency is not required to centralize styling.

Shared primitives own focus, disabled, invalid, sizing, and typography rules. Pages own layout. Repeated layout with the same behavior may become a small shared component; do not build a configurable universal page/form abstraction.

Reuse targets:

- One pipeline-template builder with explicit options for name, initial index and retrieval settings. Retain immutable saved inputs and v1 compatibility conversion.
- One pagination utility and a component with explicit `offset`, `total`, `pageSize`, disabled state, label and change callback. Preserve page-specific focus handling.
- Existing RetrievalSettingsForm stays shared between editor, indexing inspection and Playground.
- Run polling becomes sequential and tied to project/run identity, with cleanup, terminal-state handling and explicit retry/error behavior. This correctness fix is a separate change from moving JSX.
- Replace behavior tied to styling selectors with refs or stable functional attributes before deleting those selectors (mobile toggle focus, Playground panel focus, editor document selection).

## 5A. Code simplification is a required deliverable

The user's additional requirement is readable, deliberate code, not merely moving generated-looking code into smaller files. The earlier extraction is not an approved template: review it critically and undo unnecessary fragmentation when it improves ownership. Preserve behavior and unrelated edits while making these changes deliberately.

### Concrete cleanup targets

| Current pattern | Planned simplification | Verification |
| --- | --- | --- |
| Editor defaults(), initial configs, Playground newDraft() construct similar graphs | One typed domain builder with explicit options; preserve intentional names and initial index differences | Equivalent nodes/edges/settings; fresh objects per call; saved snapshots unchanged |
| Constant running=false and branches in PipelineEditor | Remove the constant and dead conditions/messages | Save/disable/interaction behavior unchanged |
| Deep ternaries in defaults, save guidance and node descriptions | Early returns, named derived values, or short exhaustive switches | Every supported node/status still handled |
| Large async save/duplicate actions embedded inside JSX | Named handleSaveVersion/handleDuplicatePipeline functions or cohesive version operations | Interrupted responses, errors and busy states remain visible |
| Short ambiguous API parameters and local variables (p, v, k, o, c) | Name projectId, version, kind, options and node at meaningful boundaries | Type checks; no broad mechanical renaming of harmless short map indices |
| api.ts mixes HTTP, types, pagination, validation and canonicalization | Keep transport focused; move actual domain logic to named modules and general pagination to lib | Callers and tests import the real owner; no re-export compatibility layer left behind |
| Three separate pagination UIs assume page size 20 | Shared Pagination with explicit pageSize; retain caller-owned focus/scroll handling | First/middle/last pages, empty results and changing totals |
| Playground lifecycle scattered across many effects/setters | Group draft/version ownership and run lifecycle; derive redundant values, keep independent processes separate | Route/version identity, draft guards, request cleanup and stale responses |
| Styling selectors also control focus behavior | Use refs or intentional functional attributes, not class-name lookup dependencies | Escape and citation/document focus work after CSS migration |
| New small files with vague names (Configuration.tsx, Questions.tsx, format.ts) | Use domain-specific names when independently useful; otherwise colocate simple helpers with the owner | Easier navigation; no new generic wrapper just to reduce line count |

### Rules for the resulting code

- One obvious place to change a behavior. Readers should not trace three implementations of the same default or follow an API helper into an unrelated feature.
- Use typed props that describe intent. Prefer callbacks such as onClose/onSelectVersion to exposing an entire state setter when callers need only a specific action.
- Keep ordinary JSX handlers short. Inline a simple field update; name an operation that validates, saves, navigates and reloads data.
- Use discriminated unions where they prevent invalid node or async states. Do not replace working types wholesale; preserve persisted v1 reading and incomplete draft editing. A saved configuration and an unfinished form may need different types.
- Derive values from existing state where possible. Introduce a reducer only when multiple transitions must update related state consistently; do not add one just because a component is long.
- Extract repeated meaning and behavior, not every repeated tag. Small one-use helpers can stay with their owner. A three-line formatter does not automatically need a new shared module.
- Avoid broad context providers, universal forms, generic request hooks with many switches, barrel exports, and speculative utilities. Add an abstraction only with named current consumers or a coherent lifecycle to isolate.
- Preserve useful comments explaining security, compatibility, units and immutable snapshots. Remove comments that simply narrate the next line or justify obsolete implementation choices.
- Use consistent semantic Tailwind variants in shared controls. Do not replace CSS sprawl with giant repeated class strings and arbitrary palette values in every page.
- Keep user-facing errors specific and recovery actionable. Simplification must not swallow failures, remove validation, or collapse distinct loading/error states into misleading success.

### Review gate for every batch

For each extracted component/hook/helper, record its responsibility and current consumer(s). Show which duplicated or obsolete implementation was removed. Check whether a reader can follow the main user action from the page to its operation without jumping through forwarding-only wrappers. If moving code leaves the original complexity intact, revise the design before proceeding.

The final handoff must include representative before/after examples of template creation, an async JSX handler, and a feature's styling ownership, plus the behavioral checks that protect each change. Formatting and file-count changes alone do not count as simplification.

## 6. Migration batches and exit gates

### Batch 0 — record the baseline

Inventory every stylesheet import and map each selector group to a component, responsive state, or vendor dependency. Trace dynamic class construction and DOM queries. Record source matches, current markup, cascade dependencies and deletion confidence. Browser coverage is evidence, not proof of global non-use.

Use isolated fixtures and existing documented test services. Capture projects, documents, index panel, editor, Playground, experiments and settings at 1440x1000 and 390x844; verify editor/Playground additionally at 1280x800. Include overlays/open panels, focus, errors, disabled controls and long content. Record the source snapshot used because earlier changes remain uncommitted.

Exit: import/ownership inventory, reproducible screenshots, current tests and behavior gaps documented. No destructive data cleanup or live paid execution is needed.

### Batch 1 — remove proven leftovers and protect behavior

Remove the unused `ask` wrapper, editor's always-false running branches, and unreachable node header/footer rules after checking all consumers. Rename the result-component test file accurately. Add focused regressions for behaviors about to move, particularly saved-version identity, dirty draft reset/guards and delayed polling.

Exit: each removal has evidence; no supported workflow or API compatibility behavior removed; affected tests pass.

### Batch 2 — theme and primitives

Wire semantic shadcn tokens correctly in styles.css. Update shared Button styling and migrate basic form primitives. If needed, use temporary aliases for old variables so untouched pages continue working. Document each alias and its consumers. Preserve dark root appearance and portaled inheritance.

Exit: generated primary utilities reference the intended semantic values; default/outline buttons, inputs and focus states work without the lavender override patch. Theme, disabled/invalid states, and representative screens verified. No unrelated dependency upgrades.

### Batch 3 — pipeline feature pilot

Unify template creation and separate validation/types from transport. Extract toolbar, settings, and canvas where props remain coherent. Migrate all pipeline-owned appearance to shared controls, token utilities and the central canvas section. Remove its feature stylesheet and its migrated rule groups from both workspace and dark override files. Preserve vendor CSS, node measurements, handles, fit/zoom, selection and keyboard behavior.

Exit: create/configure/save/reopen/duplicate/discard/delete/restore/arrange workflows pass; linked versions and dirty guards hold; desktop/mobile screenshots checked. Pipeline styles have one owner, with no leftover competing rules.

### Batch 4 — Playground

Separate draft/version ownership, history and run lifecycle. Implement the sequential polling fix with delayed/out-of-order response tests. Reuse pipeline domain functions and retrieval settings. Migrate styling and remove playground/evidence stylesheets and associated overrides only after remaining consumers are mapped (evidence is also used in comparisons).

Exit: retrieval-only and pipeline execution stay distinct; saved and preview snapshots remain exact; draft saving/reset/version navigation, pending/failure/insufficient-evidence states, citation focus, history pagination and mobile panels pass.

### Batch 5 — remaining features and shell

Migrate documents, indexes, retrieval controls, experiments, projects and settings in that order, each with its own gate. Keep current inspector and comparison boundaries. Move shared pagination out of documents and allPages out of pipeline transport. Split workspace project loading dependencies carefully so navigation does not unnecessarily reload unrelated data; retain refresh after project creation and explicit error recovery.

Exit: upload/processing/index/cancellation, experiment configuration/draft/comparison/export, project switching, URL history, mobile menu and focus behavior preserved. Delete each migrated CSS file and remove its imports only after its consumers pass.

### Batch 6 — finish consolidation and enforce standards

Remove remaining legacy files: app/linear-workspace.css, app/styles/base.css, theme.css, tokens.css and workspace.css; remove AnswerText.css, retrieval.css, experiments.css and any remaining document/feature stylesheet. Keep styles.css as the sole authored CSS file. Remove old variable aliases and `.linear-workspace` dependence after all references are gone.

Enforce with existing ESLint and a small repository check where ESLint cannot cover file presence: no authored CSS outside the central file, no feature CSS imports, and no application imports of tests/testing libraries. Extend formatting/check scripts only as needed. Do not add a CSS framework or linter dependency without an actual enforcement gap.

Update frontend standards, architecture and implementation status to describe the implemented outcome. Report bundle size; code splitting is a separate follow-up unless this change creates a regression.

## 7. Verification matrix

| Area | Required evidence |
| --- | --- |
| Theme and primitives | Token references in generated CSS; computed colors; keyboard focus, invalid and disabled states; no duplicate primary override |
| Shell | Projects loading/retry/switch, direct URLs, back/forward, remembered versions, mobile menu Escape and focus |
| Documents / indexes | Upload validation, loading/errors, chunks and pagination, progress/cancellation, retrieval settings and project isolation |
| Editor | Graph interactions, settings, template equivalence, validation, immutable saving/reopening, duplicate/discard and unsaved navigation guards |
| Playground | Both test modes, delayed polling without overlap, terminal states, saving/resetting drafts, version identity, citations, history and stale-response handling |
| Experiments | Dataset input requirements, draft continuity, run progress/cancellation, comparison/evidence, unavailable scores/cost, export |
| Responsive / accessibility | Desktop/mobile and editor intermediate width; long names/evidence; zoom/overflow; focus order and visible focus; reduced motion |
| CSS cleanup | Final import graph; one authored stylesheet; no old rules/aliases/selector-dependent behavior; necessary vendor styles preserved |

Use unit/component tests for state and domain contracts, with API/provider mocks. Keep browser journeys on isolated services. Avoid tests that merely assert new component names or implementation structure. Browser screenshots and computed-style checks are required because unit tests do not establish visual parity.

Commands from frontend: `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test -- --run`, `npm run build`; relevant `npm run test:e2e` journeys against documented test services. Run affected checks per batch and the complete frontend suite at the final gate. No backend schema change is planned; if one becomes necessary, reconsider scope explicitly.

## 8. Completion and change control

Done means one central application stylesheet, correctly mapped semantic theme variables, shared control variants, no known obsolete overrides, coherent component ownership, and passing relevant behavior/visual checks. A lower line count alone does not satisfy completion. Do not promise a CSS line target before confirming required selectors.

Each batch should be independently reviewable and reversible. Preserve the existing uncommitted work; do not reset to HEAD. Do not combine style migration, unrelated functional changes, dependency upgrades and a visual redesign in one change. Explicitly label unverified states and remaining limitations.

## 9. Sources and what they support

- [shadcn theming](https://ui.shadcn.com/docs/theming): semantic CSS-variable tokens and foreground pairs. This informs token naming, not a wholesale copy of the latest preset.
- [shadcn components.json](https://ui.shadcn.com/docs/components-json): central CSS path, CSS-variable configuration and aliases.
- [Tailwind theme variables](https://tailwindcss.com/docs/theme): @theme mappings and inline variable references.
- [Tailwind custom styles](https://tailwindcss.com/docs/adding-custom-styles): limited custom CSS and component layers alongside utilities.
- [React component boundaries](https://react.dev/learn/thinking-in-react): cohesive responsibilities and minimal state ownership.
- [React custom hooks](https://react.dev/learn/reusing-logic-with-custom-hooks): reuse named stateful logic without implying shared state between independent hook calls.
- [React Flow theming](https://reactflow.dev/learn/customization/theming): preserve library styles and use supported variables for appearance.
- [CSS cascade layers](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@layer): layer precedence matters during migration.

One central authored stylesheet is the user's project convention. These sources support its implementation; they do not claim that every React application must use the same directory structure.


## Implementation result (2026-09-12)

- Installed the form primitives with `npx shadcn@latest add button input label textarea native-select checkbox --yes --overwrite`, then added Table, Badge, Tabs, Separator, Alert, Skeleton, Accordion and Progress through the same official CLI (4.21.0). Customized generated variants and central tokens; replaced the temporary home-grown wrappers. Tailwind and its Vite plugin are pinned to 4.3.3.
- Replaced 13 authored stylesheets with one central file. Removed the empty `app/styles/` directory, obsolete answer/run/node selectors, literal primary-button patches and conflicting global navigation/control/page-spacing rules. Ordinary layouts now use Tailwind utilities. Complex responsive geometry, content typography and vendor selectors remain central; there is no claim that custom CSS has been eliminated.
- Removed unused `ask`, impossible editor running branches and duplicated pipeline defaults. `createPipelineDraft` serves the editor and Playground. `createEditableExecution` clones saved data before converting legacy retrieval settings.
- Simplified all frontend API modules, separating feature models, HTTP operations, projects and shared pagination. Explicit `createPipeline`/`createPipelineVersion` replaced the endpoint-switching `save`. Document operations now name processing and document identity. Shared transport handles server error details, timeout and cancellation consistently.
- Replaced retrieval's nested mode-switch expression with `changeRetrievalMode`, shared validation limits and named validators. Form controls reuse the same limits. Score labels preserve zero and unavailable values and do not imply confidence.
- `NodeSettings`, `RunHistory`, document/chunk inspectors and experiment comparison own coherent UI sections. Save/duplicate/CSV preview/import/experiment submission are named actions. Pipeline and Playground controller hooks keep related state and request lifecycles together; their page components compose feature sections with intent-based callbacks.
- Sequential query polling has delayed-response, selection-race, retry and completion tests. Workspace project reads are separated from the full project list, preserving refresh after creation.
- Unit/component tests remain in `tests/`; `AnswerText.test.tsx` preserves untrusted-content and citation coverage. The renamed `AnswerResult.test.tsx` accurately describes its subject. Lint checks one CSS file, empty source directories, test placement and shared-module dependencies.

Representative simplifications: template creation was repeated across editor initialization, restore and Playground reset; these now call one factory. Experiment import previously embedded its request and state updates in JSX; JSX now names `handleImportDataset`. Feature styling previously combined feature files with dark overrides; primitives now own their variants and the central stylesheet owns the semantic palette and necessary custom rules. Raw table and progress markup now uses the installed shadcn primitives, and the Documents/Indexes switch uses complete Tabs semantics.

Validation: Prettier, structure/ESLint, strict TypeScript, 66 Vitest tests across 18 files and the production build passed. A fresh isolated Compose stack passed 10 applicable Chromium journeys; the credential-free case was skipped under the enabled local embedding fixture. The initial long-lived browser stack contained queued experiment jobs, so final verification used a new isolated project and empty queue without resetting developer data. No live provider calls were used. The production build retains a 586 kB minified JavaScript chunk warning.
