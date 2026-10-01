# Website widget

## Overview

This area is a separate React and Vite app for the customer facing chat widget. A small public loader creates an iframe. The iframe presents one deployed answer pipeline and calls the browser widget API with a short lived token. Read `../AGENTS.md` and `../docs/website-chatbot-widget-plan.md` before changing its trust boundary.

## Key files

`public/v1.0.0/loader.js` creates the iframe and checks messages; private mode requests a token from the customer site's own backend. `src/main.tsx` owns the iframe UI, handshake, question submission, polling, and evidence display. `src/api.ts` defines widget transport and the versioned contract. `src/styles.css` styles the isolated frame. `vite.config.ts` and `scripts/` build and serve versioned assets with frame policy and size checks. `e2e/` contains isolated customer site and API fixtures; `tests/` contains loader tests.

## Commands

From `widget/`, you can run `npm ci`, `npm run dev`, `npm run typecheck`, `npm run test`, and `npm run build`. The widget dev server uses `http://127.0.0.1:5274`. Follow `../docs/development.md` for the isolated customer fixture and the Studio Playwright widget journey.

`npm run serve` serves the packaged `dist/` assets on `127.0.0.1:5274` through `scripts/serve.mjs` and forwards to `WIDGET_API_ORIGIN` (default `http://127.0.0.1:8000`). `npm run build:layout-fixtures` builds the React and Vue layout fixtures into the ignored `.local/`. `frame.html` is the Vite iframe entry, and `demo-static/index.html` is a plain embed test page.

## Conventions

Keep the public deployment ID separate from authorization. In private mode, the customer's backend authenticates visitors and keeps the `rqs_live_...` deployment key; the loader calls only its same origin token path. In opt-in public mode, the iframe obtains a bounded anonymous token from Studio after checking the allowed parent origin, and the customer's script contains no token path. Keep widget tokens in iframe memory, and check message source, origin, nonce, deployment, and protocol version. Render answer and citation text as text. Keep widget assets independent of the Studio shell, Clerk, React Flow, and Studio styles. Preserve versioned paths and the asset size checks when packaging.

## Gotchas

Allowed site origins and iframe policy narrow browser exposure but do not authenticate a visitor. The local customer fixture has disposable sign in and a deterministic answer double; it is not a customer authentication product. Local widget checks do not prove public hosting or live provider readiness. The Studio appearance preview does not submit paid questions. The browser route shares deployed answer admission, run ownership, and worker execution with the backend.

## Related documents

See `../docs/website-chatbot-widget-plan.md`, `../docs/development.md`, and `../docs/deployment.md`.

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
