# Website source node plan

Status: Stages A–D implemented 2026-10-02 (see `docs/implementation-plan.md`).

This plan simplifies the Website source node's settings, moves operational fetch
limits to the server, records the effective limits on every run, and then
hardens crawling (sitemaps, retries, page-level checkpoints, parallel fetching
and duplicate content). It is a follow-on to Phases 4–5 of the
[ingestion pipeline plan](../../ingestion-pipeline-plan.md) and must keep that plan's
guarantees: SSRF boundary in `app.connectors.safe_http`, immutable pipeline
versions, fenced execution tokens and atomic index publication.

Implement it in the stages below. Each stage is a reviewable vertical slice
with its own tests and documentation update; do not start a stage before the
previous one passes its acceptance criteria.

| Stage | Outcome | Target rating |
| --- | --- | --- |
| A | Fewer user settings, server-owned limits, effective limits recorded per run | 7.5 / 10 |
| B | Sitemap indexes, transient-error retries, JavaScript-shell warning | 8.5 / 10 |
| C | Page-level crawl checkpoints, then bounded parallel fetching | 9 / 10 |
| D | Canonical and content-hash duplicate handling | 9+ / 10 |

## 1. Current state (reviewed 2026-10-02)

- `frontend/src/features/ingestion-pipelines/components/SourceSettings.tsx`
  (`WebsiteSettings`) shows 12 settings under **Scope & fetch limits**,
  regardless of discovery mode.
- `frontend/src/features/ingestion-pipelines/editorModel.ts` (`defaultWebsite`)
  sets `include_path_prefixes: ['/']`, `max_depth: 2`,
  `request_timeout_seconds: 10`, `deadline_seconds: 300`, `concurrency: 2`.
- `backend/app/schemas/ingestion.py` (`WebsiteConfig`) requires every limit in
  the saved node configuration.
- `backend/app/connectors/website.py` (`_discover`) is used by both preview
  (`workers/previews.py`) and runs (`workers/remote_ingestion.py`, via
  `fetch_all`). Problems found:
  1. **"Preview deadline" also limits runs.** One `deadline_seconds` bounds the
     whole crawl in both paths. At 2 req/s, 300 s permits roughly 600 requests,
     so a valid `max_pages: 1000` configuration cannot finish.
  2. **Coupled budgets.** Raising `max_pages` without raising
     `max_total_bytes` (20 MB default) fails mid-run.
  3. **Editable user agent.** `robots_allowed` evaluates robots.txt against the
     configured user agent, so editing it can change what robots.txt permits.
  4. **`concurrency` is unused.** It is validated and saved, never read; pages
     are fetched sequentially (documented as intentional in
     `docs/architecture.md`, Phase 4).
  5. **Mode-blind UI.** Depth and path filters are shown for Single URL, where
     they have no effect.
  6. **Whole-stage checkpoint only.** `fetch_all` returns every outcome and
     artifact in memory; revisions are persisted after the source stage
     completes. A failure at page 900 of 1000 refetches from page 1.
  7. **Sitemap indexes unsupported.** Every `<loc>` is treated as a page; nested
     sitemaps come back as XML and are excluded as "Only HTML pages are
     supported". `.xml.gz` sitemaps are not supported.
  8. **No per-page retry.** HTTP 429/503 marks the page failed; a robots.txt
     5xx fails the source.
  9. **URL-only duplicate detection.** Tracking parameters and
     `rel="canonical"` are ignored; identical content at different URLs is
     indexed twice.
  10. **Client-rendered sites.** A JavaScript shell is fetched as an "included"
      page with almost no text and no warning.

## 2. Stage A — settings, server-owned limits and recorded policy

### 2.1 User-selected settings (saved in the node)

| Setting | Shown for | Default | Bounds |
| --- | --- | --- | --- |
| Discovery mode | always | `crawl` | single_url, url_list, crawl, sitemap |
| URL / URL list / start URL / sitemap URL | always | empty | existing URL validation |
| Maximum pages | crawl, sitemap | 50 | 1–1000 |
| Maximum crawl depth | crawl | 3 | 0–10 |
| Include path prefixes (collapsed "Filter pages") | crawl, sitemap | derived from start URL path (`/docs/x` → `/docs/`); empty for `/` | ≤ 50 entries |
| Exclude path prefixes (collapsed "Filter pages") | crawl, sitemap | empty | ≤ 50 entries |
| Allowed origins (collapsed "Advanced") | always | derived from URL(s) | 1–20 |
| Crawl speed, requests/second (collapsed "Advanced") | url_list, crawl, sitemap | 2 | 0.1–5 |

Rules:

- Single URL shows only mode and URL. URL list rejects more URLs than
  `max_pages` (server validation, mapped to the field).
- Hidden settings keep their saved values but are ignored by the connector for
  modes where they do not apply; the schema documents this.
- **Maximum pages** moves out of the collapsed section. The collapsed summary
  no longer carries the page count.
- Include prefix derivation happens only while the field is still at its
  derived value, mirroring the existing `allowed_origins` inference.

### 2.2 Server-owned limits

Add to `backend/app/core/config.py` (environment-configurable, validated):

| Setting | Default | Notes |
| --- | --- | --- |
| `website_request_timeout_seconds` | 20 | per request |
| `website_max_response_bytes` | 20 MB (raised from 2 MB after a 5–6 MB docs page failed) | per page; at most 64 MB |
| `website_max_total_bytes_cap` | 100 MB | upper bound for the derived budget |
| `website_redirect_limit` | 5 | |
| `website_user_agent` | `RAGQualityStudio/1.0 (+<docs URL>)` | never user-editable |
| `website_deadline_min_seconds` / `_max_seconds` | 60 / 3600 | clamp for the derived deadline |

Derived per run:

- `max_total_bytes = min(max_pages × max_response_bytes, cap)`
- `deadline_seconds = clamp((max_pages + robots/sitemap allowance) / requests_per_second × 1.5 + request_timeout, min, max)`
- `respect_robots = true` (no switch).

Remove from `WebsiteConfig`: `max_response_bytes`, `max_total_bytes`,
`request_timeout_seconds`, `deadline_seconds`, `concurrency`,
`redirect_limit`, `user_agent`, `respect_robots`. The `Strict` schema then
rejects them as unknown fields.

### 2.3 Effective fetch policy

1. Add `WebsiteFetchPolicy` (Pydantic, strict) holding every effective limit
   above plus a `policy_version` integer.
2. Add `resolve_website_fetch_policy(config, settings) -> WebsiteFetchPolicy`
   as the only place that combines user settings and server settings.
3. `WebsiteConnector._discover` takes the policy explicitly and reads limits
   only from it; it never reads limit fields from the node configuration.
4. **Runs:** when `services/ingestion.py` creates a run, resolve the policy for
   every Website source node and store it in `run.snapshot["fetch_policies"]`
   keyed by source node ID, beside `execution`. Workers, retries, stale
   recovery and duplicate deliveries read the policy from the snapshot and
   never re-resolve it, so a server-setting change mid-run does not alter a
   started run.
5. **Previews:** resolve the same way, store it on the preview record and
   return it in the preview response.
6. **UI:** show a read-only "Fetch limits used" line on preview results and on
   the run detail (for example "deadline 60 s · 20 MiB per page · 100 MiB total ·
   robots.txt respected · RAGQualityStudio/1.0").

### 2.4 Test data reset

The existing ingestion data is development test data and the owner has
authorized deleting it. Before deleting, list what references it:

- ingestion pipelines and their versions, ingestion runs, run node states and
  items, source previews, source snapshots, source items and revisions, and
  index versions/knowledge sets built from them;
- answer pipeline versions, queries and experiments that reference those
  indexes.

Delete only ingestion-derived rows (and the answer data that references them,
after confirming the list with the owner) through a one-off script in the
scratch area, never a migration. Do not run `docker compose down -v` and do not
touch projects, uploaded documents or unrelated answer pipelines. No
compatibility path for old Website node fields is required.

### 2.5 Tests

Backend (`backend/tests/test_website_preview.py`,
`test_website_ingestion.py`, `test_ingestion_contracts.py`):

- policy derivation: bytes cap, deadline clamp at both ends, 1000 pages at
  2 req/s fits within the derived deadline;
- removed fields are rejected; URL list longer than `max_pages` is rejected;
- run snapshot contains `fetch_policies` for every Website source;
- recovery after changing a server setting reuses the recorded policy;
- preview response contains the policy;
- connector uses the fixed server user agent for both requests and robots
  evaluation.

Frontend (Vitest/RTL):

- fields shown per mode (Single URL shows mode and URL only);
- include prefix derivation and that a user edit stops derivation;
- preview and run detail render the recorded limits.

### 2.6 Documentation

- `docs/architecture.md`: decision record — user scope vs server-owned limits,
  recorded fetch policy, removal of unused `concurrency`.
- Website node page under `docs/site/` and the generated API reference.
- `docs/implementation-plan.md`: status entry.

### 2.7 Acceptance criteria

- The Website node shows at most 8 settings, filtered by mode.
- A 1000-page crawl configuration is not rejected by an inconsistent deadline
  or byte budget.
- Every new run and preview stores the exact effective limits, and the UI shows
  them.
- No user can change the user agent or disable robots.txt.

## 3. Stage B — sitemaps, retries, JavaScript-shell warning

### 3.1 Sitemap indexes (do first; small, high value)

- Detect `<sitemapindex>` and fetch nested sitemaps up to depth 1, at most
  50 sitemaps, each within the response byte limit and counted against the
  total budget.
- Accept gzip (`.xml.gz` or `Content-Encoding`/`Content-Type` gzip) with a
  decompressed-size cap equal to the response byte limit; keep the existing
  DOCTYPE/ENTITY rejection after decompression.
- Use `<lastmod>` with the prior revision to skip unchanged pages without a
  request; record the reason.
- Record nested sitemaps as outcomes with a distinct status so the inspector
  explains them.

### 3.2 Per-page transient retries

- Retry 429, 502, 503, 504 and connection timeouts up to 3 attempts with
  exponential backoff and jitter, honoring `Retry-After` (capped, and within
  the run deadline).
- Retry robots.txt 5xx the same way before failing the origin.
- Honor robots.txt `Crawl-delay` when slower than the configured speed.
- Store the attempt count on each item; mark failed only after the last
  attempt. Do not stack these retries with worker-level retries for the same
  page.
- Retry settings live in `WebsiteFetchPolicy`.

### 3.3 JavaScript-shell warning

- After extraction, flag pages whose extracted text is below a threshold
  (initially 200 characters) as `likely_client_rendered`, with the reason
  "Likely needs JavaScript rendering — not supported".
- Show the warning in preview and run inspectors; do not add a headless
  browser.

### 3.4 Acceptance criteria

- A WordPress-style sitemap index discovers the nested pages.
- A page that returns 503 then 200 is included with attempt count 2.
- A client-rendered fixture page is flagged in preview and run results.

## 4. Stage C — page-level checkpoints, then parallel fetching

### 4.1 Crawl frontier and per-page persistence

- New table `website_crawl_frontier` (migration): `run_id`, `source_node_id`,
  `canonical_url`, `depth`, `status` (`queued`, `fetched`, `excluded`,
  `failed`, `duplicate`), `attempts`, `source_revision_id`, `reason`,
  timestamps; unique on (`run_id`, `source_node_id`, `canonical_url`).
- Persist each fetched page as a source revision and mark its frontier row in
  the same transaction, fenced by the run's execution token.
- On recovery, rebuild the queue from `queued` rows and skip completed rows; do
  not refetch or re-embed completed pages.
- Track `transferred_bytes` and elapsed time on the run so budgets and the
  deadline continue across recovery instead of resetting.
- Release page bodies from memory once persisted.
- Expose live progress ("412 / 1000 pages fetched") through the existing run
  progress fields.
- Preview may keep the in-memory path, but must use the same discovery and
  scope code.

### 4.2 Bounded parallel fetching

- Add server setting `website_fetch_concurrency` (default 4, max 8) and put the
  effective value in `WebsiteFetchPolicy`.
- Enforce the request rate per origin with a shared limiter so total requests
  to one origin never exceed the user's crawl speed.
- Frontier claiming must be safe under parallel workers (row locks or
  `SKIP LOCKED`), and byte budget accounting must be atomic.

### 4.3 Acceptance criteria

- Killing the worker mid-crawl and recovering fetches only the remaining
  pages (asserted by request count in tests).
- Duplicate delivery of the same task does not create duplicate revisions.
- With concurrency 4 and speed 2 req/s, no origin receives more than
  2 requests in any one-second window (test with a fake clock).

## 5. Stage D — duplicate content

- Strip a documented list of tracking parameters (`utm_*`, `ref`, `fbclid`,
  `gclid`) during canonicalization; record the original URL.
- Honor `<link rel="canonical">` only when it points to an allowed origin and
  page scope; otherwise ignore it and record why.
- Skip a page whose normalized content hash equals an already included page in
  the same run, with status `duplicate` and the matching URL.
- Acceptance: `/a`, `/a/`, `/a?utm_source=x` and a page with
  `rel="canonical"` → `/a` produce one included revision.

## 6. Out of scope

Each needs its own security and scope decision before it is planned:

- headless-browser rendering of JavaScript sites;
- authenticated sites (cookies, logins, headers);
- ingesting PDFs or other files linked from pages;
- user-editable user agent or robots.txt bypass.

## 7. Verification commands

- Backend: `docker compose -p rag-studio-tests -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests`, then `down` with the same project.
- Lint/format: `docker compose exec backend ruff check .` and `ruff format --check .`.
- Frontend: `npm run lint`, `npm run typecheck`, `npm run test -- --run` in `frontend/`.
- Migrations (Stage C): upgrade on a clean database.
- Browser check at `http://127.0.0.1:5273`: Website node settings per mode,
  preview limits line, run detail limits line.
