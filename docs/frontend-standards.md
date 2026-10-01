# Frontend standards

This document describes the frontend that exists now and the rules for extending it. Implementation status and dated verification results belong in `docs/implementation-plan.md`, not here.

## Current frontend architecture

The application is a client-rendered React workspace using strict TypeScript, Vite, Tailwind CSS, shadcn component source, Radix primitives and React Flow. Exact dependency versions are pinned in `frontend/package.json` and `frontend/package-lock.json`; those manifests are authoritative when this prose becomes stale.

- `src/main.tsx` imports the one application stylesheet and mounts the application.
- `src/app/App.tsx` owns the shell, current route, project context, mobile navigation state and page focus.
- `src/app/navigation.ts` owns hash-route parsing and the unsaved-pipeline navigation guard. There is no routing-library dependency.
- `src/app/WorkspacePage.tsx` maps routes to feature entry points. It must not absorb feature-specific state or API calls.
- `src/features/` owns project, document, pipeline, Playground, experiment and workspace behavior.
- `src/components/ui/` contains locally owned shadcn primitive source.
- `src/components/` contains shared product components.
- `src/lib/` contains shared transport, pagination, retrieval rules and utilities.
- `tests/` mirrors application source for Vitest/Testing Library tests; `e2e/` contains Playwright journeys.

`DESIGN.md` is the visual authority. It records the token based design system from [spec 0002](specs/0002-workspace-ui-redesign/index.md): the references, tokens, both themes, layout rules and anti slop rules.

## Component ownership

Use existing UI primitives before adding another abstraction. The current primitive set includes Button, Input, Label, Textarea, Native Select, Checkbox, Radio Group, Table, Badge, Tabs, Separator, Alert, Skeleton, Accordion, Progress, Sheet and Tooltip. Shared product components include PageHeader, the LoadingState, EmptyState and ErrorState components in `src/components/states/`, and the parts in `src/components/parts.tsx`.

- Shared primitive variants belong in `src/components/ui/`.
- Shared product behavior belongs in `src/components/`.
- A component used only by one feature belongs in `src/features/<feature>/components/`.
- Feature pages coordinate user intent and compose sections; they should not contain provider, persistence or transport logic.
- Controller hooks may own a feature's related state and asynchronous lifecycle. A longer cohesive controller is preferable to many forwarding hooks with unclear ownership.
- Extract a component or hook when it owns meaningful behavior, state or demonstrated reuse. Do not extract pass-through wrappers merely to reduce line counts.
- Keep short event handlers inline. Give multi-step operations names such as `saveVersion`, `runRetrieval` or `importDataset`.
- Pass intent-based callbacks where practical instead of exposing unrelated state setters to child components.
- Do not create a generic “everything” component with nested mode checks. Separate answer-pipeline and ingestion-pipeline domain behavior while sharing proven canvas or form primitives.

### Adding shadcn primitives

The existing primitives were generated with the official shadcn CLI 4.21.0 using the `new-york` style, Radix and the aliases in `components.json`. The CLI itself is not installed in the application dependency graph.

Until a deliberate shadcn upgrade is authorized, run an explicit compatible CLI version from `frontend/`:

```sh
npx --yes shadcn@4.21.0 add <component>
```

Do not use `@latest`, reinitialize the registry or pass `--overwrite` during routine additions. Review generated source, dependency changes and compatibility with the existing `radix-ui` package before keeping the result. Replacing an existing primitive requires preserving its local density, mobile target, focus, invalid and dark-theme behavior.

Application code should import `cn` through `src/lib/utils.ts`. Some existing generated primitives import the pinned `cn` package directly; normalize a primitive when making a substantive edit to it, but do not mass-rewrite untouched generated files during unrelated work.

## Styling and theming

`src/app/styles.css` is the only application-owned stylesheet. It imports Tailwind and React Flow's vendor stylesheet once. Do not add feature CSS, CSS Modules, CSS-in-JS, a second theme file or component-scoped `<style>` elements.

Current structure:

- The token block (between `/* @tokens:start */` and `/* @tokens:end */`) defines the dark palette under `:root`, the light palette under `:root[data-theme='light']`, and the approved Tailwind keys. Tailwind's default spacing, type, color, radius, shadow and blur scales are reset, so only the keys listed in `DESIGN.md` generate CSS.
- `@layer base` holds the font face, the page defaults, the focus ring and the few element rules the screens still rely on.
- `@layer components` is for shared selectors, when a pattern cannot be a primitive variant. It is empty today.
- The React Flow vendor block (between `/* @vendor:react-flow:start */` and `/* @vendor:react-flow:end */`) stays unlayered, because React Flow's own stylesheet is unlayered. It maps React Flow variables onto the tokens.
- `public/theme-init.js` sets `data-theme` before the stylesheet loads, from the stored choice or the OS setting. `src/app/useTheme.ts` owns the header toggle, the OS listener and cross tab sync.
- Inter is self hosted from `public/fonts/`; `Inter-LICENSE.txt` keeps its OFL text beside the committed font asset.

Rules for changes:

- Use only token utilities and the approved keys: grid spacing (`p-4`, `gap-2`), named sizes (`h-control-md`, `w-panel`), the five text sizes, token colors (`bg-surface`, `text-foreground-muted`, `border-border-strong`), `rounded-control`, `rounded-card` and `shadow-popover`. The guard rejects anything else.
- Define color literals only in the token block. For a one off size, use a token variable through the `(--var)` shorthand, such as `h-(--editor-canvas)`, and declare that variable in `@layer base`.
- Put reusable control appearance in the primitive's CVA variants. A one off layout need may use `className` at the call site.
- Every interactive element needs a 44px target on touch; primitives grow to 48px under `pointer: coarse` without JavaScript.
- Keep visible focus, pressed, disabled, loading, invalid, empty and error states. Disabled buttons use `aria-disabled`, never native `disabled`.
- Verify every change in both themes. Do not use opacity to repair low contrast, and keep status colors paired with a text label.
- Follow the anti slop rules in `DESIGN.md`: no gradients, glow, blur, glass, sparkle icons, purple hues or colored card backgrounds.
- Keep license text with every committed third party font. Do not add or replace fonts without recording their source and license.
- Do not edit generated `dist/` CSS; it is build output, not source.

## Routing, state and async behavior

- Keep routes parseable by `src/app/navigation.ts` and directly refreshable through the existing hash-route deployment.
- Put route query parameters under the owning feature. Validate restored IDs through project-scoped APIs before rendering them as selected.
- Clear or ignore stale project data when the project or route identity changes. Never show one project's documents, indexes, pipelines, runs or evidence in another project.
- Register the existing unsaved-change guard for editable pipeline drafts. Saved versions remain immutable; editable state must be an independent copy.
- Preserve browser Back/Forward behavior. Do not replace route state with component-only state when refresh or sharing matters.
- Poll sequentially: one request at a time, with cleanup on unmount/selection change and protection from stale responses.
- Expose refresh and polling errors. Do not silently keep old data while presenting it as current.
- Name and centralize multi-step state transitions in a controller or page function instead of embedding long promise chains in JSX.

## Domain and API boundaries

Feature `api.ts` modules contain named HTTP operations and request payload construction. Domain contracts and reusable validation live in the feature's `model.ts` or an existing domain module.

- Use `src/lib/api.ts` for same-origin API requests, response-body timeouts, cancellation signals, safe server errors and JSON requests.
- Use `src/lib/pagination.ts` for `Page<T>` and bounded collection traversal.
- Keep multipart uploads as `FormData`; the browser supplies the multipart boundary.
- Keep retrieval defaults, mode transitions and validation in `src/lib/retrieval.ts`, which is shared by the editor, Playground and Knowledge Base retrieval testing.
- Use descriptive operations such as `listProcessingRuns(projectId, documentId)` and `createPipelineVersion(projectId, pipelineId, draft)`.
- Creating a pipeline and appending an immutable version are different operations and should remain different functions.
- API payload fields retain backend `snake_case`; local variables and parameters use descriptive `camelCase`. Do not add a mapping layer solely to rename every field.
- TypeScript types document compile-time expectations; the backend remains authoritative for validation, authorization and execution.
- Shared `src/lib/` and `src/components/` modules must not import application or feature modules. Feature-to-feature imports require an actual domain dependency; prefer moving a genuinely shared contract or component to shared ownership.
- Keep model calls, secrets, database assumptions and provider-specific logic out of frontend code.
- Use braces for control flow. Prefer named conditions and early returns over nested ternaries or single-letter domain variables.

## Accessibility and responsive behavior

Accessibility and responsive states are feature requirements, not a final polish pass.

- Use the existing semantic UI primitives rather than raw buttons, inputs, selects, textareas, tables or progress controls in feature code.
- Every input needs a programmatic label. Associate hints and validation messages where they materially affect completion.
- Interactive icon-only controls require an accessible name. Decorative icons remain hidden from assistive technology when appropriate.
- Preserve the skip link, main-focus behavior, logical heading order, keyboard navigation and visible focus ring.
- Do not make dragging the only way to configure a graph. Every node setting must be reachable through labeled forms.
- Use explicit text in addition to color for queued, running, succeeded, failed, cancelled and unavailable states.
- Preserve the established mobile breakpoint behavior and minimum mobile control height. Verify narrow layouts for horizontal page overflow, inspector replacement/stacking and canvas usability.
- Tables may scroll inside a labeled/focusable region when their content cannot reflow. Do not allow the entire page to overflow horizontally.
- Respect `prefers-reduced-motion`. New animation must not block focus, reading or task completion.
- Do not put source content, prompts, credentials or sensitive metadata in browser storage. Existing remembered navigation stores identifiers only.

## Tests and enforcement

Unit/component tests live under `tests/`, mirroring `src/`. Browser journeys live under `e2e/`.

```text
src/components/AnswerText.tsx
tests/components/AnswerText.test.tsx
src/lib/retrieval.ts
tests/lib/retrieval.test.ts
tests/setup.ts
```

Test observable behavior: invalid settings, exact endpoint payloads, immutable versions, async races, failed requests, project isolation, citation safety, keyboard actions and user-visible state. Avoid tests that only assert filenames or duplicate trivial implementation details.

The jsdom `ResizeObserver` stub belongs in `tests/setup.ts`; browser journeys exercise the real observer and layout. Use deterministic API/provider fixtures in automated tests. Run opt-in live providers separately and with explicit bounds.

`npm run lint` first runs `scripts/check-structure.mjs`, which checks `src/` for extra CSS files, test/spec files and empty directories, then runs the design token guard: it rejects color literals, off scale font sizes, style props other than custom properties, pixel bracket values, keys outside the approved set, banned utilities, raw form elements under `src/features/`, and any stylesheet rule outside the token block, `@layer base`, `@layer components` and the React Flow vendor block. `LEGACY_ALLOWANCE` is zero. ESLint enforces braces in application code, blocks test imports from `src/`, and prevents shared libraries/components from importing feature or app modules. These checks do not replace code review of feature-to-feature ownership or stylesheet cascade behavior.

Run from `frontend/`:

```sh
npm run format:check
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

Run Playwright against the isolated services documented in [development instructions](development.md). Never point automated fixtures at developer data. Rebuild test services after API changes so browser tests exercise the current contract.

## Known frontend constraints

- Workspace routes are lazy-loaded from `WorkspacePage`; keep new route entry points behind the shared accessible Suspense boundary and review production chunk output when adding a feature.
- Pipeline and Playground controller hooks are intentionally longer than presentation components because they coordinate cohesive async lifecycles. Split them only around a real responsibility, not an arbitrary line limit.
- The visual journey (`e2e/visual.spec.ts`) is reviewed by eye; there are no committed pixel baselines yet, so a layout regression is caught only when someone reviews the screenshots.

## Primary guidance

- [shadcn installation](https://ui.shadcn.com/docs/installation) and [theming](https://ui.shadcn.com/docs/theming) for locally owned primitives and semantic variables.
- [Tailwind theme variables](https://tailwindcss.com/docs/theme) and [custom styles](https://tailwindcss.com/docs/adding-custom-styles) for utilities, tokens and deliberate custom CSS.
- [React component hierarchy](https://react.dev/learn/thinking-in-react) and [custom hooks](https://react.dev/learn/reusing-logic-with-custom-hooks) for component and state ownership.
- [Testing Library principles](https://testing-library.com/docs/guiding-principles) and [Playwright configuration](https://playwright.dev/docs/test-configuration) for behavior-focused tests and browser journeys.

A separate test root, hash routing and a single application stylesheet are this project's chosen conventions, not universal requirements for every React application.
