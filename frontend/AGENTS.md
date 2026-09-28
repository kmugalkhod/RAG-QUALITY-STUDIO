# Studio frontend

## Overview

This area is the React and TypeScript Studio workspace. It manages projects, documents, pipelines, answers, experiments, and deployment settings through real API calls. Read `../AGENTS.md` and `../docs/frontend-standards.md` before changing its behavior or appearance.

## Key files

`src/main.tsx` mounts the app and imports the one authored stylesheet. `src/app/App.tsx` owns the shell and project route context. `src/app/navigation.ts` parses hash routes and guards unsaved pipeline drafts. `src/app/WorkspacePage.tsx` selects feature entry points. `src/features/` owns product behavior and feature API modules. `src/lib/api.ts` owns authenticated transport and safe errors. `src/components/ui/` contains locally owned UI primitives. `tests/` mirrors source for Vitest, and `e2e/` holds Playwright journeys.

## Commands

From `frontend/`, you can run `npm ci`, `npm run dev -- --port 5273`, `npm run lint`, `npm run typecheck`, `npm run test -- --run`, and `npm run build`. Browser journeys use `E2E_BASE_URL=http://127.0.0.1:5273 npm run test:e2e` with the documented isolated services.

## Conventions

Keep feature requests in each feature's `api.ts` and reusable domain rules in its model. The backend owns validation and authorization. Preserve `DESIGN.md`, semantic tokens, accessible controls, and responsive behavior. `src/app/styles.css` is the only authored app stylesheet. Keep answer and ingestion pipeline editors separate, and keep saved versions immutable while drafts remain editable. Clear stale project data and async responses when the route or project changes.

## Gotchas

Studio Vite uses the canonical `http://127.0.0.1:5273` URL and proxies `/api` to the backend. Do not run a second Docker or Nginx Studio frontend during local UI checks. The website widget is a separate app in `../widget/`; Studio only owns its management form and appearance preview in `src/features/deployments/`. Frontend tests use `tests/setup.ts`, while browser tests need current backend services and isolated data.

## Related documents

See `../docs/frontend-standards.md`, `../docs/development.md`, and `../docs/website-chatbot-widget-plan.md`.

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
