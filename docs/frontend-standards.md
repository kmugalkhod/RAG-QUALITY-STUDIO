# Frontend standards

## Component ownership

Use the official shadcn CLI to add UI primitives. Customize the generated Tailwind/CVA variants for this application's density and theme; do not substitute home-grown lookalikes. The current registry convention is `new-york` with Radix. `components.json` records the destination and theme configuration.

Run from `frontend/`:

```sh
npx shadcn@latest add <component>
```

Review the generated diff and dependency changes. Do not pass `--overwrite` during routine additions; replacing an existing component requires reviewing its local customizations. The current Button, Input, Label, Textarea, Native Select, Checkbox, Table, Badge, Tabs, Separator, Alert, Skeleton, Accordion and Progress primitives were installed with shadcn 4.21.0. Dependencies are pinned in the manifest and lockfile. `lib/utils.ts` re-exports the registry's `cn` helper.

Keep shared primitive variants in `components/ui/`, shared application components in `components/`, and feature-specific components in their feature. Custom application components such as `NodeSettings`, `RunHistory` and `DocumentInspector` compose primitives and own product behavior; they are not substitutes for shadcn controls.

Pages coordinate user actions and compose cohesive sections. Shared product components live in `src/components`; a feature's one-use sections live in `features/<feature>/components`. Extract a component or hook when it owns meaningful behavior, state, or reuse. Controller hooks may coordinate a feature's related async lifecycles, while components receive intent-based callbacks instead of raw state setters where practical. Do not create forwarding-only components. Keep short event handlers inline; name multi-step operations such as saving a version or importing a dataset.

## Styling and theming

`src/app/styles.css` is the **only application-owned stylesheet**. It imports Tailwind and the required React Flow package stylesheet once. Do not add feature CSS, CSS Modules, CSS-in-JS, or separate token/theme files.

- Define the supported dark theme at `:root`; map semantic tokens through `@theme inline` using `var(...)` references.
- Use Tailwind classes for ordinary layout and spacing: `flex`, `grid`, `gap-4`, `p-6`, `border-border`, `bg-background`, `text-muted-foreground`.
- Customize shared controls in their generated variants. Use component `className` for a specific layout requirement, such as a two-line mode button with `h-auto`.
- Keep necessary custom selectors for answer markup, responsive inspector geometry and React Flow in the central file. Tables use the shadcn primitive and Tailwind layout utilities. Reuse semantic colors; do not append another theme override to repair a conflicting token.
- Custom selectors currently include unlayered responsive layout rules. These outrank Tailwind's utility layer. Check computed styles when changing a layout utility; migrate its competing custom declaration in the same change. Do not move the entire stylesheet into a cascade layer without checking those interactions.
- Keep focus, disabled/invalid states, reduced motion and mobile touch targets when customizing a generated component.

## Domain and API code

Feature `api.ts` modules contain named HTTP operations and payload construction. Reusable contracts and validation live in the feature's `model.ts` or existing domain module. Retrieval defaults, mode transitions and validation remain together in `src/lib/retrieval.ts`; they serve the editor, Playground and document search.

Use descriptive function and parameter names: `listProcessingRuns(projectId, documentId)` and `createPipelineVersion(projectId, pipelineId, draft)`. Creating a pipeline and appending an immutable version are separate operations. Query-run reads belong to Playground; project reads belong to projects.

Use `lib/api.ts` for timeouts, cancellation, server errors and JSON requests. Use `lib/pagination.ts` for `Page<T>` and collection traversal. Shared libraries and shared UI must not import feature implementations. Keep multipart uploads as `FormData` so the browser provides the boundary.

API payload fields retain the backend's snake_case names. Local parameters use descriptive camelCase names. Avoid a parallel mapping layer solely to rename every response field. TypeScript contracts are compile-time descriptions; the backend remains responsible for request validation and execution.

Use braces for control flow. Prefer readable conditions and named values over nested ternaries or single-letter domain parameters. Keep editable copies independent of saved snapshots. Poll sequentially, ignore stale responses after selection changes/unmounting, and expose refresh failures instead of silently replacing results.

## Tests and checks

Unit/component tests live under `tests/`, mirroring `src/`. Browser journeys live under `e2e/`. For example:

```text
src/components/AnswerText.tsx
tests/components/AnswerText.test.tsx
src/lib/retrieval.ts
tests/lib/retrieval.test.ts
tests/setup.ts
```

Test behavior: invalid settings, immutable versions, exact endpoint payloads, async races, failed requests, citation safety and user actions. Avoid tests that only assert file names or duplicate trivial implementation details. jsdom's ResizeObserver stub is confined to test setup; browser journeys exercise actual layout.

From `frontend/`:

```sh
npm run format:check
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

Lint includes a small structure check that rejects extra CSS files, test files in `src/`, and empty source directories. ESLint enforces application/test imports and shared-module boundaries. Run Playwright against the documented isolated stacks in [development instructions](development.md); never use automated fixtures with developer data. Rebuild the test services after API changes so tests exercise the current contract.

## Primary guidance

- [shadcn installation](https://ui.shadcn.com/docs/installation) and [theming](https://ui.shadcn.com/docs/theming): distribute actual component source and customize semantic variables.
- [Tailwind theme variables](https://tailwindcss.com/docs/theme) and [custom styles](https://tailwindcss.com/docs/adding-custom-styles): utility generation, tokens and deliberate custom CSS.
- [React component hierarchy](https://react.dev/learn/thinking-in-react) and [custom hooks](https://react.dev/learn/reusing-logic-with-custom-hooks): coherent responsibilities and reusable stateful behavior.
- [Testing Library principles](https://testing-library.com/docs/guiding-principles/) and [Playwright configuration](https://playwright.dev/docs/test-configuration): observable behavior and separate browser journeys.

A separate test root and a single application stylesheet are this project's chosen conventions, not universal requirements for every React application.
