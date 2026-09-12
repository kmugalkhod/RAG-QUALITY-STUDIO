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

The workspace's visual authority is `DESIGN.md`. Preserve its charcoal/lavender operating interface unless the user explicitly authorizes a redesign.

## Component ownership

Use existing UI primitives before adding another abstraction. The current primitive set includes Button, Input, Label, Textarea, Native Select, Checkbox, Table, Badge, Tabs, Separator, Alert, Skeleton, Accordion and Progress.

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

- The supported dark palette is defined as semantic custom properties under `:root`.
- Tailwind maps those variables through `@theme inline`.
- Inter is self-hosted from `public/fonts/`. The font file exists, but a corresponding license file is not currently present in the repository.
- Tailwind utilities handle ordinary component layout and spacing.
- Central custom selectors handle formatted answers, complex workspace geometry, responsive inspectors and React Flow vendor integration.
- Unlayered custom rules intentionally outrank Tailwind's utility layer in parts of the current stylesheet.

Rules for changes:

- Define palette literals only when declaring semantic tokens at the root. Outside token definitions, use semantic variables or Tailwind token utilities.
- Existing isolated literals in the Overview action, queued/running status, pipeline shadow and React Flow vendor variables are legacy exceptions, not examples to copy. Normalize the touched selector to a semantic token when its visual behavior can be verified.
- Use utilities such as `flex`, `grid`, `gap-4`, `p-6`, `border-border`, `bg-background` and `text-muted-foreground` for ordinary layout.
- Put reusable control appearance in the primitive's CVA/utility variants. A one-off layout requirement may use `className` at the call site.
- Keep necessary content and vendor selectors in the central stylesheet, grouped by feature or responsibility. Remove superseded declarations in the same change instead of appending override chains at the end.
- Check computed styles before changing a utility that competes with an unlayered custom selector. Do not move the entire stylesheet into a cascade layer without regression testing every major route.
- Keep visible focus, disabled and invalid states. Preserve the existing reduced-motion behavior and ensure any new motion has a non-motion state change.
- Use semantic foreground/background pairs. Do not use opacity to repair low text contrast or introduce a second ad hoc dark palette.
- Keep license text with every committed third-party font. Restore the Inter license before a distributable release; do not add or replace fonts without recording their source and license.
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

`npm run lint` first runs `scripts/check-structure.mjs`, which checks `src/` for extra CSS files, test/spec files and empty directories. ESLint enforces braces in application code, blocks test imports from `src/`, and prevents shared libraries/components from importing feature or app modules. These checks do not replace code review of feature-to-feature ownership or stylesheet cascade behavior.

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

- The production build currently reports one JavaScript chunk above Vite's 500 kB warning threshold. Route-level lazy loading is the intended future fix; do not hide the warning by raising the threshold without measuring and documenting the trade-off.
- `src/app/styles.css` contains a substantial incumbent custom-selector cascade. New work should reduce touched duplication, but a wholesale layering or stylesheet rewrite requires route-wide computed-style and visual regression checks.
- Pipeline and Playground controller hooks are intentionally longer than presentation components because they coordinate cohesive async lifecycles. Split them only around a real responsibility, not an arbitrary line limit.
- The app currently supports one dark theme. Do not add a nonfunctional theme switch or partial light theme.
- The committed Inter font currently has no accompanying license file. This must be corrected before a distributable release; do not describe the license as included until the file exists.

## Primary guidance

- [shadcn installation](https://ui.shadcn.com/docs/installation) and [theming](https://ui.shadcn.com/docs/theming) for locally owned primitives and semantic variables.
- [Tailwind theme variables](https://tailwindcss.com/docs/theme) and [custom styles](https://tailwindcss.com/docs/adding-custom-styles) for utilities, tokens and deliberate custom CSS.
- [React component hierarchy](https://react.dev/learn/thinking-in-react) and [custom hooks](https://react.dev/learn/reusing-logic-with-custom-hooks) for component and state ownership.
- [Testing Library principles](https://testing-library.com/docs/guiding-principles) and [Playwright configuration](https://playwright.dev/docs/test-configuration) for behavior-focused tests and browser journeys.

A separate test root, hash routing and a single application stylesheet are this project's chosen conventions, not universal requirements for every React application.
