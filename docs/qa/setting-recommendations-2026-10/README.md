# Recommended Website settings: labelled sites and baseline, 2026-10-14 (spec 0011, Slice 0)

Files:

- [`labels.csv`](labels.csv): 15 labelled inputs. Each row gives the settings a careful person would choose for that input, written before any recommendation code existed.
- [`baseline.csv`](baseline.csv): the config the Studio editor builds today for the same input, and how many fields a user must change to get a valid, safe draft.

Slice 3 runs the probe and rules over these rows and adds its results to this README. The work is free: it uses HTTP only, with no model or embedding calls.

## Sites

| ID | Input | Category | What it tests |
| --- | --- | --- | --- |
| W1a | `https://docs.python.org/3/tutorial` | Docs, no trailing slash | X1: the 301 to `/3/tutorial/` must give include `/3/tutorial/` |
| W1b | `https://docs.python.org/3/tutorial/` | Docs folder | Same site with the slash |
| W2 | 10 Wikipedia URLs | URL list | Real-source W2 |
| W3 | 10 GOV.UK URLs | URL list | Real-source W3 |
| W4 | 10 MDN URLs | URL list | Real-source W4 |
| S1 | `https://fastapi.tiangolo.com/tutorial/` | Docs with a sitemap | Sitemap mode: 51 tutorial URLs, 100% link coverage |
| S2 | `https://www.openbsd.org/faq` | Docs without a sitemap | Crawl mode, plus a second trailing-slash redirect |
| S3 | `https://www.sqlite.org/lang.html` | Docs without a sitemap, page start | A non-folder scope (`/lang`) that the folder rule cannot express |
| S4 | `https://www.rust-lang.org/` | Multilingual with `hreflang` | Redirect from www to the bare domain (same site); language exclusions |
| S5 | `https://hacks.mozilla.org/` | Blog with tag, category and archive pages | Utility and listing sections; a `Crawl-delay` placed before the first `User-agent` line; the page ceiling |
| S6 | `https://www.gnu.org/software/make/manual/html_node/` | Site with `Crawl-delay` | `Crawl-delay: 4`, so at most 0.25 requests per second; 172 pages |
| S7 | `https://docs.python.org/dev/tutorial/` | Start URL blocked by robots | `Disallow: /dev` |
| S8 | `https://docs.python.org/3.9/tutorial/` | Start URL blocked by robots (parser gap) | robots.txt blocks it, but Python's parser allows it |
| S9 | `https://excalidraw.com/` | JavaScript-only page | 31 visible characters, no links |
| S10 | `https://aclanthology.org/N19-1423.pdf` | PDF URL | Not HTML; should be uploaded as a file |

The W2-W4 URLs are copied from `backend/scripts/real_source/sources.json`. All sites are public, need no login, and have terms or licences that allow a small, polite probe. Each row's `notes` gives the licence where the site states one. OpenBSD's pages state no content licence, so only a few requests were made to that site.

## Method

**Date:** 2026-10-14, all sites. W2-W4 also use the real-source fetch of 2026-10-09, in which the product fetched all 30 URLs.

**Blind-labelling rule.** Labels were written from what the sites showed and from the Website settings table in spec 0011. No recommendation rule, probe or reason code was run or read. Slice 1 files were being written in the same working tree at the time and were not opened. When a label and the spec's rules are likely to disagree, the label records the human choice and the note names the conflict (S3, S4, S5, S8). Labels must not be changed after Slice 2's rules run, except to correct a factual error about the site. Any such correction is dated and explained in this README.

**What was examined.** For each site: `robots.txt` (the `*` group, `Crawl-delay` and `Sitemap:` lines), the start URL with its redirect chain followed by hand (status, final URL, media type), and the start page itself (`<html lang>`, `hreflang` alternates, visible text length, script count, and same-origin links grouped by path section). Then `/sitemap.xml` or the robots sitemap, with a count of `<loc>` entries inside the label's scope. Where depth or size needed it, one to three second-level pages were sampled (OpenBSD `ports/` and `pf/`, rust-lang `governance` and `learn`, Hacks post sitemaps, GNU `sitemap0.xml.gz`).

**How it was fetched.** Raw HTTP with `curl` through a small throwaway script, at one request per second. The two sites with a `Crawl-delay` got 4 s (GNU) and 10 s (Hacks) between requests. Each site got about 3-8 requests. The brief asked for WebFetch, but it was not used: it returns a model summary of the page and hides status codes, redirects, headers and exact link sets, which these labels depend on. robots.txt files were also run through Python's `urllib.robotparser`, the parser the Website connector uses, to see what the product itself would decide (S5, S7, S8).

**What a label means.** It is the config a careful person would save for this input. Page ranges assume the D4 page ceiling of 200.

### Column conventions (`labels.csv`)

| Column | Meaning |
| --- | --- |
| `expected_mode` | `crawl`, `sitemap`, `url_list`, `single_url` or `none`. `a\|b` means `a` is preferred and `b` is acceptable. `none` means no Website draft should be run; `expected_warnings` then names the warning code from the spec. |
| `expected_include_prefixes`, `must_stay_included`, `acceptable_exclusions` | Lists separated by `;`. `(none)` is an empty list; `n/a` means the field does not apply. `must_stay_included` lists paths that must stay in scope: they may not fall outside the include prefixes or be excluded. |
| `page_range` | Inclusive range for `max_pages`: from about the in-scope count to about twice it, never above the ceiling. |
| `max_depth` | Inclusive range for crawl mode. `n/a` when the expected mode does not use depth. |
| `max_speed` | Upper bound in requests per second: `min(2, 1/Crawl-delay)` for the `*` group, as a careful reader of robots.txt understands it. |
| `expected_origins` | Extra column, needed for the origin safety check. Origins have no trailing slash and are separated by `;`. |
| `expected_warnings` | Extra column: `robots_blocks_start`, `client_rendered`, `non_html_start` or `(none)`. |

## Baseline: what the editor builds today

The baseline follows the code at `e831c3e`. The Website parts of the working tree were checked unchanged on 2026-10-14.

- **Defaults.** `defaultWebsite()` in `frontend/src/features/ingestion-pipelines/editorModel.ts` gives mode `crawl`, no origins, no include or exclude prefixes, `max_pages` 50, `max_depth` 3 and `requests_per_second` 2. The same defaults are in `WebsiteConfig` in `backend/app/schemas/ingestion.py`.
- **Typing a URL.** `WebsiteSettings.setSelection` in `components/SourceSettings.tsx` sets `allowed_origins` to `[new URL(url).origin]`. In crawl and sitemap modes it sets `include_path_prefixes` to `derivedIncludePrefixes(url)`, which is the URL's folder, or `[]` for `/`. Nothing else changes.
- **URL lists.** The Start URL input holds one line, so the user must first set Discovery mode to "URL list". That clears the URL, sets the origins from the pasted URLs and leaves the include list empty.
- **Trailing-slash warning.** `folderStartUrl` shows the "covers every page under …" warning only when the last path segment has no dot. W1a and S2 show it. S3 and S10 (`lang.html`, `.pdf`) do not.

A draft counts as **valid and safe** when all of these hold:

- server validation and `resolve_website_fetch_policy` accept it;
- the start page can be fetched under the allowed origins;
- the deadline fits the real request rate;
- the origins are within `expected_origins`;
- the include prefixes are no wider than the label;
- the speed is at most `max_speed`.

The page count and exclusions affect quality, not safety. They count towards `touches_match_label` only.

**Today's numbers.** Of the 11 inputs that can be run (every row whose expected mode is not `none`):

- Only W1b and S1 give a valid, safe draft after the user enters the URL alone. That is 2 of 11 (18%); the spec 0011 target is 80% or more.
- W2-W4 need the mode change first.
- 6 drafts are unsafe or broken as derived:
  - W1a and S2: the scope is too wide.
  - S3: the whole site is in scope, and no warning is shown.
  - S4: the start page redirects to an origin that is not allowed, so the run cannot start.
  - S5: the draft runs at 2 requests per second, and the connector ignores the site's 10-second `Crawl-delay`.
  - S6: the deadline is set for 2 requests per second (60 s), but `Crawl-delay` forces 4 s per request, so the crawl stops after about 15 of 172 pages.
- Of the inputs that should not be run, S8 is not blocked by the product at all.

## Found while labelling (for Slice 2)

These problems are recorded so that the owner can decide on them. None of them was fixed here.

1. **The robots parser misses rules.** The connector uses `urllib.robotparser`, and the spec moves it into `parse_robots` with no change in behaviour. That parser ends a group at a blank line, so docs.python.org's `Disallow: /3.9/` (and the other end-of-life versions) is ignored (S8). It also ignores a `Crawl-delay` placed before the first `User-agent` line (S5). The labels follow the site's evident intent, so S5 (speed) and S8 (blocked) will fail unless the parsing changes or the owner relabels.
2. **The language regex is lower-case.** S4 has `pt-BR`, `zh-CN` and `zh-TW`, and the spec's `^[a-z]{2}(-[a-z]{2,4})?$` does not match them unless the comparison ignores case.
3. **The slash form of language exclusions matters.** rust-lang links point to `/es`, which redirects to `/es/`. An exclusion of `/es/` does not match the linked URL, so the label uses `/es`.
4. **Sitemap scheme.** GNU's robots.txt `Sitemap:` line uses `http://` on an `https` origin, so the spec's "in origin" check skips it. That does no harm here, because it does not list the Make manual anyway.
5. **Malformed `hreflang`.** FastAPI marks every translation `hreflang="en"`. The include prefix keeps the translations out, but rule (b) for language exclusions would not recognise them if the include list were empty.
6. **Non-folder scope.** For S3, the folder rule gives `[]`, which is wider than the human label `/lang`. Under the zero-tolerance include check this row fails by construction, although it is not worse than today.

## Owner spot-check (D11)

Please check these 5 rows. They involve the most judgement.

| Row | Question |
| --- | --- |
| S5 Hacks | Should a `Crawl-delay` before any `User-agent` line be honoured (0.1 requests per second)? Is sitemap mode preferred? Are the category, tag and author exclusions and the ceiling-bound page range (150-200) right? |
| S4 rust-lang | Both origins; the 9 language exclusions plus `/en-US`; no trailing slash on the prefixes; page range 25-60. |
| S8 Python 3.9 | Should this be labelled as blocked, when the connector's parser allows it? |
| S3 SQLite | Keep the non-folder include `/lang` (a known miss for the rules), or relabel it `(none)` with a page cap? |
| S1 FastAPI | Is sitemap preferred over crawl when both would give the same 51 pages? Is the page range 51-80 right? |

## How Slice 3 will score

Slice 3 runs the Slice 2 probe and rules on every row, with the feature on, in a local stack. It records the recommended config, the reason codes and the warnings in `results.csv` beside these files, and adds a per-site table and a summary to this README.

**Scope safety (zero tolerance, all 15 rows):**

1. Every recommended origin is in `expected_origins`, compared without a trailing slash.
2. No include prefix is wider than the label or than today's derived prefix (`baseline.csv`). A prefix is no wider when it starts with a label prefix. A label of `(none)` allows any prefix. An empty recommendation is wider than a non-empty label.
3. No exclusion matches a `must_stay_included` path or the start URL's section.
4. `requests_per_second` is at most `max_speed` and at most 2.
5. `max_pages` is at most 200 (the ceiling) and within the 2,500 pipeline budget.
6. For `none` rows: the expected warning is reported, and the result is not a crawl or sitemap draft presented as ready to run.

**Field agreement (the 11 rows that can be run):**

| Field | Counted as agreeing when | Target |
| --- | --- | --- |
| Mode | Equal to an allowed value in `expected_mode` | 90% or more |
| Origins | The same set as the label | Reported |
| Include prefixes | The same set as the label | Reported; W1a must give `/3/tutorial/` |
| Exclusions | Within `acceptable_exclusions`; S4 and S5 also report how many of the expected exclusions were found | Reported |
| `max_pages` | Within `page_range` | 80% or more |
| `max_depth` | Within the range (crawl only) | Reported |
| Speed | Equal to `max_speed`, which is also the upper bound | Reported |
| Warnings | `expected_warnings` reported | Reported |

**Usability:** for each row that can be run, count the fields a user must still change for a valid, safe draft after the recommendation is applied. The target is 1 field (the URL) on 80% or more of rows; today it is 2 of 11. The results list this count beside `touches_valid_safe` from `baseline.csv`.

The live sites may change before Slice 3 runs. If a site's robots.txt, sitemap or structure has changed since 2026-10-14, the results note it, and that row is not counted against the rules.
