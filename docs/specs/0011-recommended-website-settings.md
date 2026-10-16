# 0011. Recommended Website settings from the site

**Date**: 2026-10-14
**Status**: Slices 0-3 built (Slice 3 on 2026-10-17); `SETTING_RECOMMENDATIONS_ENABLED` stays off pending the owner's review of the Slice 3 card and evaluation (`docs/qa/setting-recommendations-2026-10/README.md`). Trimmed 2026-10-14 by the owner's decision: Website only, computed by code, no decision model. The owner accepted the recommended defaults for D3-D7, D10 and D11 below and asked for Slices 0-3 to be built and pushed. Sources: two independent research reports (A and B, 2026-10-14, held in the session scratchpad) and a combined draft that also covered jev and Extract. That draft's extra parts are listed under "Later, optional". Code claims were checked against the working tree at `4dc466f`.

## Summary

Users still have to choose the Website source settings themselves: discovery mode, allowed origins, include and exclude path prefixes, maximum pages, crawl depth and crawl speed. A wrong choice causes real harm:

- **X1. Trailing-slash scope.** `https://docs.python.org/3/tutorial` derived the include prefix `/3/`. The crawl reached `/3/whatsnew/changelog.html` and the run failed (`docs/implementation-plan.md`, real-source round). Today the UI only warns (`SourceSettings.tsx`).
- **X2. Speed and scope picked by hand.** The real-source harness picked depth 1, 20 pages and 1 request per second by hand (`backend/scripts/real_source/sources.json`). A user without a probe cannot know these values.
- **X3. Problems appear too late.** JavaScript-only pages are flagged only after a preview (`services/website_ingestion.py`). A site's sitemap is never discovered, because robots.txt `Sitemap:` lines are never read.

The goal: the user enters a website address, the server checks the site with a small, safe probe, and **code computes** every setting from what it measured. The settings are pre-filled and shown **read-only**, each with a one-line reason, with an **Edit** button for anyone who wants to override.

The existing schemas, validators and run behaviour stay authoritative. Recommendations change only what goes into a draft.

## Why no decision model and no Extract work

- **Extract** already has one visible choice and OCR that switches on per page (spec 0008, `extractors/pdf.py`). There is little left for a user to choose, so it stays as it is.
- **jev** (`typesafe/jev-1.13` on OpenRouter) is a decision model. It picks among options it is given and cannot output numbers, URLs or reasons. It would only answer two narrow Website questions (single page or section; is a path section a utility/listing area). Code rules cover the common cases, the API is alpha with one provider, and site text would leave the system. It is kept as an optional later slice that must beat the rules on labelled sites first.

## Decisions for the owner (accepted defaults)

| ID | Decision | Accepted default |
| --- | --- | --- |
| D3 | When analysis starts | Automatically when a valid URL is committed (blur, Enter or paste), plus a **Re-analyze** button. Cached for 24 hours per input. |
| D4 | Page ceiling for large sites | 200 pages per source, server-wide `SETTING_RECOMMENDATIONS_PAGE_CEILING`. A larger value is the user's explicit edit. |
| D5 | Pre-fill or confirm first | Pre-filled. Weak evidence is labelled **Check this**. Fields the user edited are never overwritten. |
| D6 | Re-analysis of saved pipelines | Only when the user presses **Re-analyze** on a draft. The result changes the draft only; saving creates a new version. |
| D7 | Store page text in the record | No. Store URLs without query strings, counts, status codes and timings only. |
| D10 | Feature gate | `SETTING_RECOMMENDATIONS_ENABLED=false` by default. The owner turns it on after reviewing the Slice 3 evaluation. |
| D11 | Who labels the evaluation sites | Claude writes the labels before rules run; the owner spot-checks 5 rows. |

## Settings: what decides each value

Basis values: **computed** (from probe evidence), **default** (product default, no evidence), **user** (input or override).

Risk applies to a *user override*:

- **Low**: no message.
- **Medium**: the row shows "Changed from recommended (was X)".
- **High**: Medium, plus a warning line naming the consequence, plus a "Wider than recommended" list on the card.

Saving is never blocked by risk; server validation is the only gate.

### Website (`WebsiteConfig`, `backend/app/schemas/ingestion.py`)

| Field | Today | Decided by | Rule (exact) | Reason codes | Override risk |
| --- | --- | --- | --- | --- | --- |
| URL / URLs | `AnyHttpUrl`; list of 1-1000 unique | User | Never inferred. A multi-line paste means `url_list`. A URL whose path ends in `.xml` or `.xml.gz` means sitemap input. | n/a | n/a |
| `selection.mode` | `single_url`, `url_list`, `crawl`, `sitemap`; default `crawl` | Computed | 1. URL list or sitemap input: keep it. 2. Crawl input: if a sitemap (robots `Sitemap:` lines in origin, then `/sitemap.xml`, then `/sitemap_index.xml`) lists ≥ 5 in-scope URLs **and** covers ≥ 80% of the in-scope URLs the probe found by links, choose `sitemap` with that sitemap URL. 3. Otherwise `crawl`. | `mode_sitemap`, `mode_crawl_no_sitemap`, `mode_crawl_sitemap_partial`, `mode_url_list`, `mode_sitemap_input` | Medium. High when switching `single_url` to `crawl` or `sitemap`. |
| `allowed_origins` | 1-20 origins | Computed | The entered URL's origin. Add the final origin only when it is the same site: hosts equal after stripping one leading `www.`, and the scheme moves only from http to https. A redirect to any other site adds nothing and raises `redirect_other_site`. For URL lists, the origins of the URLs. | `origins_start`, `origins_redirect` | **High** when adding an origin not in the recommendation |
| `include_path_prefixes` | ≤ 50; derived from the URL's folder today (`editorModel.ts`) | Computed | Crawl or sitemap only. Let `P` be the final URL's path. If `P` ends with `/`, the prefix is `P`. Otherwise, if ≥ 50% of the start page's same-origin links start with `P + "/"`, the prefix is `P + "/"`. Otherwise it is `P`'s parent folder. A root path gives `[]`. Guard: the prefix must start with today's derived prefix of either the entered or the final URL, so it is never wider than today. Sitemap input: `[]` unless the user typed one. | `include_redirect_folder` (fixes X1), `include_links_folder`, `include_folder`, `include_none` | **High** when removing or shortening a prefix. Medium otherwise. |
| `exclude_path_prefixes` | ≤ 50; default `[]` | Computed | Candidate sections are one path segment below the include prefix (or the first segment when there is none) with ≥ 2 discovered URLs. The section holding the start URL is never a candidate. (a) Exclude when the segment exactly matches `utility-paths-v1`: `search`, `login`, `signin`, `sign-in`, `logout`, `cart`, `checkout`, `feed`, `rss`, `wp-admin`, `wp-json`, `print`, or `page` followed by a numeric segment. (b) Exclude when the include list is empty, the segment matches `^[a-z]{2}(-[a-z]{2,4})?$`, the start page lists it as an `hreflang` alternate, and it differs from `<html lang>`. | `exclude_utility_pattern`, `exclude_language`, `exclude_none` | Medium |
| `max_pages` | Strict int 1-1000, default 50; ≥ URL-list length; pipeline sum ≤ 2,500 | Computed | URL list: its length. Sitemap: `min(C, B, ceil10(N × 1.1))`. Crawl: if the probe frontier is **closed** (sampled pages linked to no in-scope URL beyond the start page's links), `min(C, B, ceil10(N × 1.1))`; if **open**, `min(C, B, ceil10(max(50, 2 × N)))` and mark Check this. `C` is the ceiling (D4), `B = 2500 − other Website sources' max_pages`, `N` is the in-scope count. Then fit the deadline: if `resolve_website_fetch_policy` raises `WebsiteScopeTooLarge`, lower to the largest value that fits. Never below 1. | `pages_sitemap`, `pages_crawl_closed`, `pages_crawl_open` (Check this), `pages_budget`, `pages_deadline`, `pages_url_list`. The row also shows the estimated time `pages / rps`. | **High** when raised. Low when lowered. |
| `max_depth` | Int 0-10, default 3; crawl only | Computed | `L1` = in-scope URLs linked from the start page; `L2` = new in-scope URLs linked from sampled pages and not in `L1`. `L2 = 0` gives 1. `L2 ≤ L1` gives 2. Otherwise 3. In sitemap or single-URL mode, keep the default and show "Not used". | `depth_toc`, `depth_two`, `depth_default`, `depth_not_used` | Medium when raised. Low when lowered. |
| `requests_per_second` | Float 0.1-5, default 2 | Computed | `min(2, 1/Crawl-delay)`, floored at 0.1. Set to `min(value, 1)` if the probe saw any 429 or 503, or a median response time over 2 s. Never above 2. | `rps_default`, `rps_crawl_delay`, `rps_slow_site` | **High** when raised |
| Server fetch policy | `WebsiteFetchPolicy` | Fixed | Unchanged and not shown | n/a | n/a |
| Warnings (not fields) | n/a | Computed | `client_rendered` (reuse `page_warnings`), `robots_blocks_start`, `non_html_start` (suggest upload or S3), `all_links_off_origin`, `start_not_found` (4xx), `redirect_other_site`. | One fixed sentence each | n/a |

Reason text is a code template filled with measured numbers, for example: "The site's sitemap lists 84 pages under /docs/, and the sample found 81 of them by links."

## Architecture

### Components and files

| Concern | File (new unless marked) |
| --- | --- |
| Settings | `backend/app/core/config.py` (edit): `setting_recommendations_enabled: bool = False`, `setting_recommendations_page_ceiling: int = Field(200, ge=10, le=1000)`, `setting_recommendations_per_project_hour: int = Field(30, ge=1, le=500)`. `.env.example` (edit). |
| Website helpers | `backend/app/connectors/website.py` (edit). Move the sitemap response checks into module-level `parse_sitemap_response(response, max_bytes)`, and robots parsing into `parse_robots(response)`. `crawl()` calls both. Behaviour unchanged; existing website tests pass untouched. |
| Probe | `backend/app/connectors/website_probe.py`. `probe_website(selection, *, connector_factory=WebsiteConnector, client=None, on_step=None) -> ProbeSignals`. Refers to `WebsiteConnector` through a module attribute so `tests/e2e_provider.py` can patch it. |
| Rules and reasons | `backend/app/services/website_recommendation.py`. Pure module: `PROBE_VERSION = "website-probe-v1"`, `RULES_VERSION = "website-rules-v1"`, `utility-paths-v1`, `recommend(signals, inputs, settings) -> Recommendation`, `RATIONALE` templates. |
| Use cases | `backend/app/services/setting_recommendations.py`: `start`, `get`, `cancel`, cache lookup, project rate limit, retention, `provenance_for_save(session, project_id, execution, recommendation_ids)`. |
| Model | `backend/app/models/setting_recommendation.py`; `app/models/pipeline.py` (edit: `settings_provenance` column). |
| Schemas | `backend/app/schemas/setting_recommendations.py`. `app/schemas/ingestion.py` (edit): `IngestionPipelineSave.recommendation_ids`. `app/schemas/pipeline.py` (edit): `VersionRead.settings_provenance`. Capabilities (edit): `setting_recommendations`. |
| API | `backend/app/api/setting_recommendations.py` (prefix `/api/projects/{project_id}`, `require_project_access`, registered in `app/main.py`). |
| Worker | `backend/app/workers/setting_recommendations.py`: task `recommendations.website` on the default queue, `soft_time_limit=150`, `time_limit=160`. `app/workers/dispatcher.py` (edit): `dispatch_setting_recommendations_once()` using `claim_fair`, called beside `dispatch_previews_once()`. |
| Migration | `backend/migrations/versions/0048_setting_recommendations.py` (latest today is `0047_index_embedding_usage.py`). |

### Probe (`website-probe-v1`)

Scope: the entered origin plus any same-site redirect target, never more.

Bounds, enforced in code:

- At most 18 HTTP requests in total.
- 1 request per second per origin; Crawl-delay honoured.
- 90 s deadline; 15 s per request.
- 5 MiB per response, 30 MiB in total; at most 5 redirects.
- User agent `settings.website_user_agent`. No JavaScript executed. Bodies dropped once signals are computed.

Steps (each sets `progress_step`):

1. **`robots`**: `GET <origin>/robots.txt` through `SafeHttpClient`. Record whether found, Crawl-delay, whether the start URL is allowed, and `Sitemap:` lines in the origin (at most 2). For a URL list, at most 5 origins.
2. **`start_page`**: call `connector.crawl()` unchanged with a probe `WebsiteFetchPolicy` (`max_pages=1`, `max_depth=0`, `requests_per_second=1`, `request_timeout_seconds=15`, `max_response_bytes=5 MiB`, `max_total_bytes=30 MiB`, `redirect_limit=5`, `deadline_seconds=90`, `retry_attempts=1`, `fetch_concurrency=1`), `selection={"mode": "single_url", "url": <start>}` and `MemoryCrawlStore`. Compute the final URL, status, media type, `<html lang>`, `hreflang` alternates, visible text length, `page_warnings`, and links (existing `_Links` parser, canonicalised as the connector does).
3. **`sitemaps`**: candidates are robots `Sitemap:` lines in origin, then `/sitemap.xml`, then `/sitemap_index.xml`. Read at most 3 top-level and 3 nested files through `parse_sitemap_response`. Count `<loc>` entries in and out of scope; the count is a lower bound when nested files were skipped.
4. **`sample_pages`**: up to 9 in-scope URLs from the start page's links, round-robin across sections, fetched with one `crawl()` call in `url_list` mode under the same policy. Per page: text length, section, links (giving `L2`), response time, 429/503 counts.
5. **`validating`**: assemble the candidate and run the validation chain.

URL-list input runs steps 1, 2 (first URL of up to 3 origins) and 5. Sitemap input runs 1, 3 and 5. Single-URL input runs 1, 2 and 5.

Stored `signals` (JSONB, at most 64 KiB): requests made (purpose, URL without query, status, outcome), robots facts, sitemap counts, section histogram (path, URL count, 3 sample paths), `L1`/`L2`, frontier closed or open, per sample page URL, text length and time, warnings. No titles, headings or text (D7).

### Validation (authoritative)

`recommend()` builds a candidate dict, then:

1. `WebsiteConfig.model_validate(candidate)`.
2. `resolve_website_fetch_policy(candidate, settings)` (deadline check).
3. Pipeline budget: `max_pages + other_sources_max_pages ≤ 2500`.
4. Guards: origins ⊆ {entered origin, same-site redirect origin}; the include guard; the start section never excluded; `requests_per_second ≤ min(2, 1/Crawl-delay)`; `max_pages ≤ ceiling`.

A failing field falls back to its default or derived value with reason `default_no_evidence`, and validation runs again. A candidate that still fails ends the job `failed` with a safe message; the form keeps today's values. Pipeline save and preview keep calling `validate_source_combination` and `validate_ingestion` exactly as today.

### Fallbacks

| Condition | Behaviour |
| --- | --- |
| Gate off | Capabilities report `enabled: false`. The UI renders today's form and no card. POST returns 503 "Setting recommendations are turned off on this server." |
| Probe failure (DNS or SSRF block, robots blocks the start URL, 4xx/5xx on the start page, deadline) | `status=failed` with the connector's safe message. The card shows it with **Retry**; the form stays editable. Saving is not blocked. |
| Duplicate delivery or stale worker | Fenced `execution_token`, as in previews. The dispatcher returns running rows older than 300 s to `queued` once and marks them `failed` the second time. |

### Caching, limits, retention

- `inputs_hash = sha256(json of {target, canonical selection, other_sources_max_pages, page_ceiling, PROBE_VERSION, RULES_VERSION})`. A `succeeded` row in the same project with the same hash, under 24 h old, is returned without re-probing unless `refresh: true`.
- At most one active (`queued` or `running`) row per (project, source node). A new request for the same node cancels the active one.
- At most `setting_recommendations_per_project_hour` new probes per project per hour; cache hits do not count. Over the limit: 429 "Analysis limit reached for this project. Try again later."
- Keep the newest 50 terminal rows per project. Versions do not depend on the rows.

### Security

- Only `SafeHttpClient` with the per-origin `allowed` callback; robots.txt honoured for every page request; nothing fetched outside the origin set.
- Page content is untrusted data; it only feeds counts and link sets. No rule can add an origin from page content.
- Routes sit under `require_project_access` (viewers get 403 on POST). Every read filters by `project_id`.

## Data model and migration `0048_setting_recommendations`

Table `setting_recommendations`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `project_id` | uuid FK `projects.id` ON DELETE CASCADE | |
| `target` | varchar(16) | CHECK `target IN ('website')` |
| `source_node_id` | varchar(80) | |
| `status` | varchar(16) | CHECK IN (`queued`, `running`, `succeeded`, `failed`, `cancelled`); reads report `expired` after `expires_at` |
| `progress` | int | CHECK 0-100; `status != 'succeeded' OR progress = 100` |
| `progress_step` | varchar(24) null | `robots`, `start_page`, `sitemaps`, `sample_pages`, `validating` |
| `inputs` | jsonb | `{selection, entered_url, other_sources_max_pages, page_ceiling}` |
| `inputs_hash` | varchar(64) | |
| `probe_version`, `rules_version` | varchar(32) | |
| `signals` | jsonb default `{}` | Bounded, no page text |
| `recommended` | jsonb null | A full valid `WebsiteConfig` |
| `fields` | jsonb default `[]` | `[{path, value, basis, risk, rationale_code, rationale, check}]` |
| `warnings` | jsonb default `[]` | `[{code, message}]` |
| `error` | text null | |
| `attempts`, `failures` | int | `failures` 0-2 |
| `execution_token` | uuid null | |
| `created_at`, `updated_at`, `started_at`, `finished_at`, `dispatched_at`, `expires_at` | timestamptz | `expires_at = created_at + 24 h` |

Indexes: `(project_id, created_at, id)`; `(status, dispatched_at, updated_at)`; `(project_id, inputs_hash, created_at)`; unique partial `(project_id, source_node_id) WHERE status IN ('queued','running')`.

Immutability: the service never updates a row after it reaches a terminal status (a test asserts this).

Column `pipeline_versions.settings_provenance`: jsonb, nullable, written only on insert by `services/pipelines.save`. Existing rows stay `NULL`. Answer pipelines always get `NULL`. The downgrade drops the column and the table.

`settings_provenance` shape (`SettingsProvenanceV1`, at most 64 KiB):

```json
{
  "schema_version": 1,
  "nodes": {
    "src-1": {
      "target": "website",
      "recommendation_id": "…",
      "entered_url": "https://docs.python.org/3/tutorial",
      "analysed_at": "2026-10-20T10:00:00Z",
      "probe_version": "website-probe-v1",
      "rules_version": "website-rules-v1",
      "fields": {
        "include_path_prefixes": {"basis": "computed", "recommended": ["/3/tutorial/"],
                                  "rationale_code": "include_redirect_folder", "rationale": "…"},
        "max_pages": {"basis": "user", "recommended": 20, "saved": 100,
                      "rationale_code": "pages_crawl_closed", "rationale": "…"}
      }
    }
  }
}
```

`provenance_for_save`:

- The client sends only `recommendation_ids` (at most 5, unique). The server loads each with `id` **and** `project_id`. A missing, foreign or non-succeeded row is recorded as `{"status": "recommendation_unavailable"}` for its node. It never raises.
- For a matched Website node, compare each managed path (`selection`, `allowed_origins`, `include_path_prefixes`, `exclude_path_prefixes`, `max_pages`, `max_depth`, `requests_per_second`) with `recommended`. Origins compared normalized and prefix lists as sorted sets. Equal keeps the recommendation's basis; different becomes `user`.
- The full provenance is copied into the version, so it survives pruning of recommendation rows.
- `execution` is stored exactly as today, so `configuration_hash`, processing identities and derivation reuse do not change (a test asserts this).

## API

All routes are under `/api/projects/{project_id}` with `require_project_access`.

| Method and path | Request | Response | Errors |
| --- | --- | --- | --- |
| `POST /setting-recommendations` | `{target: "website", source_node_id (1-80, [a-zA-Z0-9_-]), selection: WebsiteSelection, other_sources_max_pages: int 0-2500 = 0, refresh: bool = false}` | 202 `SettingRecommendationRead` (may already be `succeeded` on a cache hit) | 503 gate off; 422; 429; 404; 403 viewer |
| `GET /setting-recommendations/{id}` | n/a | 200 Read | 404 not in project |
| `POST /setting-recommendations/{id}/cancel` | n/a | 200 Read (terminal row returned unchanged) | 404 |
| `GET /ingestion-capabilities` (edit) | n/a | Adds `setting_recommendations: {enabled, page_ceiling}` | n/a |
| `POST /pipelines`, `POST /pipelines/{id}/versions` (edit) | Ingestion save adds `recommendation_ids: list[UUID] = []` (max 5) | `VersionRead.settings_provenance: SettingsProvenanceV1 \| None` | Unchanged |

`SettingRecommendationRead`: `id`, `source_node_id`, `target`, `status`, `progress`, `progress_step`, `error`, `inputs`, `probe_version`, `rules_version`, `recommended: WebsiteConfig | null`, `fields: list[RecommendationField]` (`path`, `label`, `value`, `basis`, `risk`, `rationale_code`, `rationale`, `check`), `warnings`, `evidence` (requests, robots, sitemap, sections, sample pages), `created_at`, `finished_at`, `expires_at`.

Frontend types are hand-written in `frontend/src/features/ingestion-pipelines/model.ts`, field for field with the Pydantic schemas. Regenerate the docs API reference with `docs/site/scripts/generate_api_reference.py`.

## Frontend: "Recommended settings" card

New `components/WebsiteRecommendations.tsx`, rendered by `WebsiteSettings` in `components/SourceSettings.tsx` when `capabilities.setting_recommendations.enabled`. Logic in new `recommendationsModel.ts` (`applyRecommendation`, `recommendationDifferences`, `isStale`, `wideningEdits`). Sequential polling in new `useWebsiteRecommendation.ts` (every 1 s, one request at a time, cleaned up on unmount or node change, stale responses ignored). API functions in `api.ts`.

Layout follows DESIGN.md: the `FACTS` definition list, hairline borders, no coloured background, no sparkle icon, the word "Recommended" (never "AI").

1. **URL field first**, labelled "Website address", hint "Enter a page, a section or a sitemap. Settings are recommended from the site." Analysis starts on blur, Enter or paste of a valid http(s) URL that differs from the last analysed input.
2. **Card** `<section aria-labelledby>` with heading "Recommended settings" and a meta line "Analysed 2 min ago · 14 requests". Each row shows the label, the value (mono for numbers and paths), one muted line `Why: <rationale>`, a `Check this` label when flagged (text plus `text-warning`, never colour alone), and `Changed from recommended (was X)` when edited. Rows: Discovery, Allowed sites, Pages under, Excluded, Maximum pages (with "about N min at R/s"), Crawl depth, Crawl speed.
3. **Warnings** in the existing `Callout` above the card.
4. `<details>` **What was checked**: the requests (purpose, URL, status), sitemap found or not, sample pages with text length.
5. **Actions**: **Edit** (outline, `aria-expanded`/`aria-controls` pointing at the existing form, which stays mounted), **Re-analyze** (ghost); once anything differs, "N settings changed from recommended" with **Reset to recommended**; a "Wider than recommended" list when `wideningEdits` is not empty, each with its consequence.
6. **States**: gate off (no card, today's form and trailing-slash advisory); no URL (hint); analyzing (`role="status"` naming the step, with **Cancel**); succeeded; failed (safe reason with **Retry**, form open); stale (URL or other sources' page total changed: "These recommendations are for <URL>. Re-analyze." Values kept); expired (values kept, "Analysed yesterday · Re-analyze"); viewer (read-only, no actions).
7. The trailing-slash advisory is hidden while a non-stale recommendation is applied.
8. **Pre-fill**: on success, managed fields still at default, derived or previously recommended values are replaced in the draft, which becomes dirty ("Unsaved changes"). Edited fields are kept. `IngestionPipelineEditor.tsx` keeps `appliedRecommendations: Record<nodeId, SettingRecommendation>` outside `execution`, sends its ids as `recommendation_ids` on save, and clears or reseeds it in `open(version)`.
9. **Saved versions** with `settings_provenance` show the card read-only from provenance ("Recommended on 20 Oct · 1 changed by you").
10. **Per source**: each Website source gets its own recommendation; `other_sources_max_pages` is the sum over the draft's other Website nodes.
11. Server errors still map to fields (`serverFieldErrors`).

Accessibility: programmatic labels, 44 px touch targets, `aria-live="polite"` status, focus to the form's first field on Edit, both themes and phone width with no horizontal overflow.

## Slices

Each slice is verified, then committed on local `main`. The owner asked for the result to be pushed. Default tests use transport doubles; PostgreSQL tests run in the isolated stack (`compose.test.yaml`).

| Slice | Scope |
| --- | --- |
| 0 | Labelled site set and today's baseline (free, no product code) |
| 1 | Tracer bullet: crawl input; origins, include prefix and speed; table, worker, API, gate; minimal card; provenance on save |
| 2 | Full Website rules: sitemaps, mode, pages, depth, deadline fit, exclusions, warnings, URL-list/sitemap/single-URL inputs |
| 3 | Full card UX and evaluation: every state, Reset, Re-analyze, Cancel, stale, widening warnings, saved-version view; field-agreement run on the labels |

### Slice 0: labels and baseline

- Create `docs/qa/setting-recommendations-2026-10/labels.csv` **before** writing rule code. Columns: site id, entered URL, category, expected mode, expected include prefixes, sections that must stay included, acceptable exclusions, page range, maximum depth, maximum speed, notes.
- Sites: W1 `https://docs.python.org/3/tutorial` with and without the trailing slash; W2-W4 as URL lists (from `backend/scripts/real_source/sources.json`); about 8 public sites covering a docs site with a sitemap, one without, a multilingual site with `hreflang`, a blog with tag/archive pages, a site with `Crawl-delay`, a start URL blocked by robots, a JavaScript-only page and a PDF URL.
- Record today's derived config per site (`defaultWebsite` plus `derivedIncludePrefixes`) as the baseline.
- Done when the CSV and a `README.md` stating the method exist. The owner spot-checks 5 rows later (D11).

### Slice 1: tracer bullet

Scope: migration 0048, model, config keys, `.env.example`; probe steps 1, 2 and 5 for crawl input; `recommend()` for `allowed_origins`, `include_path_prefixes` and `requests_per_second` (other fields keep defaults with basis `default`); worker, dispatcher hook, API, capabilities field, `recommendation_ids` on save and `provenance_for_save`; frontend types, API functions, `useWebsiteRecommendation`, a minimal card with rows, Why lines, Edit and pre-fill; `tests/e2e_provider.py` gains a controlled `/docs` → 301 → `/docs/` path (new paths only).

Acceptance:

- With the gate on, entering `https://<controlled>/docs` gives include `/docs/` with reason `include_redirect_folder`.
- Saving stores `settings_provenance` with basis `computed`.
- `execution` is byte-identical to a save of the same values without `recommendation_ids`.
- With the gate off, UI and API behave exactly as before.

Tests:

- pytest with PostgreSQL: migration upgrade/downgrade on a clean database; project scoping (foreign id 404 on GET, skipped in provenance); viewer POST 403; one active row per node; cache hit within 24 h and `refresh` bypass; fenced token rejects a stale worker; stale-running recovery; terminal rows never updated; provenance basis computed versus user; `configuration_hash` unchanged.
- Unit: probe against a transport double for the redirect, Crawl-delay, robots blocking the start URL, an SSRF private address (blocked), a redirect to another site (not added), and the request bound.
- Vitest: card rows and Why lines, pre-fill marks dirty, an edited field survives a new recommendation, the save payload carries `recommendation_ids`, no card with the gate off.

### Slice 2: complete Website rules

Scope: `parse_sitemap_response` and `parse_robots` moved out of closures with no behaviour change; probe steps 3 and 4; mode rules; `max_pages` (frontier, ceiling, budget, deadline fit, URL list); `max_depth`; pattern and `hreflang` exclusions; all warnings; URL-list, sitemap and single-URL inputs; validation chain with per-field fallback.

Acceptance: every rule has a test at its exact boundaries (5 or 4 sitemap URLs; 80% or 79% coverage; `L2 = 0` or `L2 = L1`; Crawl-delay 10 s or 11 s; budget 2,500 minus other sources). Existing website preview and ingestion tests pass untouched.

Tests: pytest rule table as parametrized cases on recorded `ProbeSignals` fixtures (`tests/fixtures/website_probe/*.json`); sitemap safety (DOCTYPE, gzip bound, nested index one level); the 18-request bound; the 64 KiB `signals` cap; PostgreSQL API run for each input mode.

### Slice 3: full card UX and evaluation

Scope: every frontend state in items 1-11, the "What was checked" disclosure, widening warnings, saved-version provenance view, per-source cards, `VersionRead.settings_provenance` in the version view. Then run the probe and rules over the Slice 0 labels (free, HTTP only) and record field agreement in `docs/qa/setting-recommendations-2026-10/README.md`.

Acceptance:

- UI follows DESIGN.md and `docs/frontend-standards.md`, passes `npm run lint`, and is checked at `http://127.0.0.1:5273` on desktop and phone in both themes with no console errors.
- Evaluation, scope safety with zero tolerance: no origin outside the label; no include prefix wider than the label or today's derivation; the start section never excluded; no speed above robots or 2; no page count above the ceiling. Mode correct on ≥ 90% of reachable sites; page count within the labelled range on ≥ 80%. W1 without the slash gives `/3/tutorial/`.
- Usability count: fields a user must touch for a valid draft is 1 (the URL) on ≥ 80% of labelled sites; today's count recorded alongside.

Tests: Vitest for each state, stale detection, Reset restoring all managed fields, the widening list (origin, include, pages, speed), Cancel calling the endpoint, polling stopping on unmount, stale responses ignored. Playwright: enter URL, see the recommended include, Edit then Reset, save, version shows "Recommended".

## Verification

- Unit and PostgreSQL tests per slice; the full backend suite in the isolated stack (`docker compose -p rag-studio-tests -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests`).
- `ruff check` and `ruff format --check`.
- Frontend `npm run format:check`, `lint`, `typecheck`, `test -- --run --maxWorkers=1` and `build`.
- Docs `generate_api_reference.py --check`.
- UI checked at `http://127.0.0.1:5273`. Playwright runs in a separate Compose project, never against developer data.

## Risks and rollback

| Risk | Mitigation |
| --- | --- |
| Sample bias: 10 pages misjudge a site | Exclusions only from fixed patterns; values visible with reasons; Check this on weak evidence; one Reset; the gate stays off until the owner reviews the evaluation. |
| Over-trust, where users stop reviewing scope | Page count, time and exclusions always visible, never collapsed. |
| Extra traffic to third-party sites | ≤ 18 requests at 1 per second, robots honoured, commit-only trigger, 24 h cache, per-project hourly limit. |
| Processing identity drift | Provenance outside `execution`; a hash-equality test. |
| Complexity in `SourceSettings.tsx` | Feature-owned components; gate-off path unchanged; recommendations replace derivation rather than adding a layer. |
| Hand-written frontend types drift | Type tests on API payloads; API reference `--check`. |

Rollback, cheapest first: set `SETTING_RECOMMENDATIONS_ENABLED=false` (UI and API return to today's behaviour); Alembic downgrade of 0048 (drops the table and column; `execution` was never changed, so saved pipelines and runs are unaffected).

## Later, optional (not in this spec)

- **Decision model (jev).** Two narrow Website questions (single page or section; utility section yes/no at ≥ 0.90), only narrowing scope, behind its own setting. Build only if a calibration on the labelled sites (≤ $0.10) shows fewer scope mistakes than the rules. Needs owner decisions on sending site text to TypeSafe and on using a decision model at all.
- **Extract evidence card** built from preview metrics, with recommended Extract values moved to the backend.
- **Guided setup** Sources step using the card.
- **Paid proof round** (≤ $1) comparing answer quality with default versus recommended settings.

## Out of scope

- Clean node selector and main-content inference.
- S3, Notion, Confluence and Existing-files source inference.
- Automatic changes to saved pipelines.
- JavaScript rendering, authenticated sites and linked PDFs.
