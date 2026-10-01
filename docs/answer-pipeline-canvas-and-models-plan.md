# Answer pipeline canvas and LLM model list plan

Status: implemented 2026-10-01 (option A, Phase 1 and Phase 2); see the matching entry in `implementation-plan.md`. Differences from the proposal: the catalog is fetched without a key (it is public), env models stay available next to approvals instead of acting as a ceiling, and `CHAT_CONTEXT_TOKENS` caps each model's budget. Wireframes: [mockups/answer-pipeline-canvas.html](mockups/answer-pipeline-canvas.html).

This plan covers two reported problems:

1. The Answer pipeline canvas does not fit the graph on first open, and its space and arrangement feel wrong.
2. The LLM node's **Chat model** dropdown shows no models.

## 1. Canvas fit and layout

### Root cause (verified in code)

- `PipelineCanvas.tsx` sets `<ReactFlow fitView fitViewOptions=…>`. React Flow applies `fitView` only on the first render that has nodes, and before those nodes are measured. `usePipelineEditor.ts` loads options, index versions and pipeline versions with `Promise.all` and only then calls `setNodes`. So at mount `nodes` is `[]` and the fit does nothing. The graph stays at `defaultViewport={{ x: 24, y: 80, zoom: 0.9 }}`, and the five 80px cards plus four gaps (about 600px) are clipped at the bottom.
- The `ResizeObserver` effect fits only when the canvas element resizes. Its first callback fires when `flow` is set, which is still before the nodes arrive.
- `zoomOnScroll={false}` and a small control cluster leave **Fit view** as the only recovery.
- The template and **Arrange vertically** place nodes at `x: 80`, so the graph hugs the left edge. The floating **Nodes** / **Arrange vertically** row sits over the first card.

### Fix (recommended: Option A, Docked flow)

1. **Fit after nodes are measured.** Use React Flow's `useNodesInitialized()` inside a child of `<ReactFlow>` (or check that every node has `measured`). The first time it turns true for a loaded pipeline, call `fitView({ padding: 0.15, maxZoom: 1 })`. Key it on pipeline id and version, so switching versions refits but editing does not. Remove the mount-time `fitView` prop, which can't work here. Keep the `ResizeObserver` refit for panel open and close.
2. **Center the template.** Generate template positions around `x: 0`, or let fit center them, and make **Auto-layout** follow the same rule. Saved layouts stay untouched.
3. **Free the canvas.** Move Add node, Auto-layout, Fit and Restore template into a 48px left tool rail. Put zoom − / level / + / fit in one bottom-left cluster. Add a `MiniMap` on desktop only, which is optional.
4. **Zoom input.** Enable Ctrl/⌘ + scroll zoom (`zoomActivationKeyCode`) and keep plain scroll for page scrolling. Add an `F` shortcut for fit when the canvas has focus.
5. **Status on cards.** Show a ✓ or ! badge per node from the existing `errors` list, so the LLM problem is visible on the node, not only in the strip above.
6. **Height.** Keep `--editor-canvas` but measure from the real toolbar height, so the canvas fills the viewport without page scroll on desktop.

Options B (horizontal flow with an overlay drawer) and C (guided steps) are in the wireframe. Both change spec 0002 (vertical 288×80 cards and a docked 320px panel), so they need a spec update first. A does not.

### Verification

- Vitest: the editor calls `fitView` once after loaded nodes are initialized, and not again on node edits.
- Playwright: open an existing pipeline at 1280×800 and 1440×900. Every node card's bounding box lies inside the canvas box without pressing Fit view. Also check a phone viewport.
- Visual check in light and dark at `http://127.0.0.1:5273`.

## 2. LLM node shows no models

### Root cause (verified in code)

- `GET /api/projects/{id}/pipelines/options` returns `models: generation.allowed_models()`.
- `allowed_models()` (`backend/app/providers/generation.py`) returns **only** `settings.chat_model` plus `settings.chat_models`, minus anything containing "embedding". Nothing is fetched from OpenRouter.
- Both are empty in the local `.env` (`CHAT_MODEL=` and `CHAT_MODELS=[]`), and `compose.yaml` defaults them to empty. So the list is `[]`.
- The endpoint does return an `error` ("Configure CHAT_MODEL with an OpenRouter chat model ID on the server."). The UI shows it only in the validation strip. The select itself shows only "Select a model", so it looks broken rather than unconfigured.
- The new per-organization OpenRouter key work (`provider_credentials`) provides the *key*, but not a *model list*.

### Phase 0: unblock now (configuration only, no code)

1. In `.env`, set a default and any extra approved models, for example `CHAT_MODEL=openai/gpt-4.1-mini` and `CHAT_MODELS=["anthropic/claude-haiku-4.5","meta-llama/llama-3.3-70b-instruct"]`. Use IDs you have checked on openrouter.ai/models, and keep `CHAT_CONTEXT_TOKENS` at or below the smallest context among them.
2. Recreate the containers so Compose picks up the new values: `docker compose up -d backend worker long-worker dispatcher`. A plain `restart` keeps the old environment.
3. Check `GET /api/projects/<id>/pipelines/options`: it should list the models with `error: null`, as long as an OpenRouter key is configured.

### Phase 1: an honest empty state (small frontend change)

- When `options.models` is empty, replace the select with an explicit empty state that shows `options.error`, a **Retry** button (it already exists as `retry`) and, for admins, a link to provider settings. Members see "Ask an organization admin".
- The node summary reads "No models available" instead of "Choose a model".
- Separate the "key missing or invalid" error from the "no models approved" error, so each gets its own message and action. That means returning a typed `error_code` next to the message.
- Tests: Vitest for the empty, key-missing and loaded states. Add a pytest for the options payload.

### Phase 2: an organization-managed model catalog (feature)

Goal: admins choose chat models in the UI instead of editing env vars, and the LLM node lists exactly what was approved, with real per-model limits.

- **Catalog (server only).** Call OpenRouter `GET /api/v1/models?output_modalities=text` with the organization's key through the existing credential binding. Keep `id`, `name`, `context_length`, `pricing` and `supported_parameters`, and drop expired models. Cache it with a TTL, bound the request with timeout, size and rate limits, and treat the response as untrusted data.
- **Allowlist (new table + migration).** Store approved models per organization: model ID, default flag, the context length and pricing snapshot with the time fetched, and who approved it. Env `CHAT_MODELS`, when set, stays an operator ceiling. Env `CHAT_MODEL` becomes the fallback when an organization has approved nothing.
- **API.** Extend `/pipelines/options` to return objects (`id`, `label`, `context_tokens`, `pricing`, `is_default`) instead of strings. This is a versioned response change, so update the frontend types from OpenAPI at the same time. Add admin endpoints to list the catalog and update the allowlist, enforced through `backend/app/core/auth.py` roles.
- **Validation.** `generation.configured()` checks the allowlist and uses **per-model** context tokens instead of the shared `CHAT_CONTEXT_TOKENS`. Saved pipeline versions keep their model ID. If a model is later removed, the editor flags it (wireframe state 4) and never swaps it silently. Runs and experiments snapshot the model and its pricing basis.
- **UI.** A searchable, provider-grouped combobox in the LLM node (wireframe state 1), and a **Models** card next to the existing OpenRouter key card in organization settings (wireframe state 5). Prices are labelled as OpenRouter estimates with the fetch time, and an unknown price shows as unknown, never 0.
- **Tests.** pytest with a mocked OpenRouter transport for catalog parsing and filtering, allowlist authorization (members can't edit), cross-organization isolation, and removed-model validation. Vitest for the combobox. Playwright: an admin approves a model, the LLM node lists it, and the pipeline saves and runs. That run uses the deterministic provider in the e2e stack.

### Decision needed before Phase 2

Should members choose **any** OpenRouter text model, or only models an admin approved? This plan recommends an admin allowlist. It controls cost and keeps experiment comparisons reproducible, in line with AGENTS.md's cost and reproducibility rules.
