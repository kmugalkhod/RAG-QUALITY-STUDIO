---
verified_against: "d884979 + website source node Stages A–D and 2026-10-03 review fixes (working tree)"
title: Website source
slug: /ingestion/sources/website/
---

Preview a bounded public website collection and publish only the included pages into an immutable index. Website fetching is implemented and covered by a deterministic HTTP transport, but these docs do not offer a hosted fixture or claim a live public-site run.

## Prerequisites

Use a public HTTP(S) site that you own or may crawl, with stable content and an origin you can allow. A loopback or private-network fixture is intentionally rejected by the SSRF boundary. Start with one small page to bound requests; external fetches can contact the site, while embedding that content can incur model charges. The exact dollar amount depends on the configured provider.

## Preview a permitted page

1. Open **Pipelines → Ingestion pipelines → New ingestion pipeline**. Select the Source node and choose **Website** under **Source type**.
2. Choose **Discovery mode**: **Single URL**, **URL list**, **Crawl from URL**, or **Sitemap**. Enter the **Page URL**, **URLs (one per line)**, **Start URL** or **Sitemap URL**. The editor shows only the settings that apply to that mode: Single URL has no others.
3. For URL list, crawl and sitemap, set **Maximum pages** (1–1000; a URL list cannot hold more URLs than this). For a crawl, set **Maximum crawl depth** (0 fetches only the start URL). Open **Filter pages** to change include/exclude path prefixes; the include prefix follows the start URL's directory (`/docs/intro` → `/docs/`) until you edit it. Open **Advanced** to check **Allowed origins (one per line)** and the **Crawl speed** (0.1–5 requests per second).
4. Select **Preview processing** and inspect each included, excluded, duplicate and failed item. Read its URL, reason, fetch mode and processing stages. Correct scope in the draft and preview again if needed. Select **Save version**, then **Collect source & publish index** only when the source and provider costs are acceptable.

The server, not the node, sets the request timeout, per-page and total byte budgets, redirect limit, crawl deadline and user agent, and always respects robots.txt. The deadline grows with the number of pages and the crawl speed; a scope that cannot finish within the server maximum (one hour by default) is rejected when you save, preview or run, for example 1,000 pages at 0.1 requests per second. Every preview and run shows the exact limits it used as **Fetch limits used**, and a started run keeps those limits even if the server settings change.

A sitemap may be a sitemap index (for example WordPress `sitemap_index.xml`): its nested sitemaps, one level deep and at most 50, appear as items with status **sitemap**, and gzip sitemaps are accepted. When a sitemap's `lastmod` shows a page has not changed since the stored copy, a refresh reuses it without a request. Rate-limited or temporarily unavailable pages (HTTP 429, 502, 503, 504 or timeouts) are tried up to three times, honoring `Retry-After`; each item shows its attempts when there was more than one. A robots.txt `Crawl-delay` slower than your crawl speed is honored. A page with almost no server-rendered text is marked *Likely needs JavaScript rendering — not supported*; choose server-rendered pages instead.

A run saves its crawl page by page. If a worker stops mid-crawl, the run resumes with the remaining pages instead of starting over, and the run strip shows how many discovered URLs have been checked. Pages are fetched several at a time, but requests to one site never exceed your crawl speed. The same page reached through tracking parameters (`utm_*`, `ref`, `fbclid`, `gclid`), a `rel="canonical"` link inside your scope, or identical text (200 characters or more) at another URL is indexed once; the other copies are listed as **duplicate** with the URL that was kept.

Expected result: a bounded preview lists exact URL outcomes; a successful run reports new/changed/unchanged/removed counts and links to a ready index and [source snapshot](../source-history.md). It may include fewer pages than links on the seed page. The connector validates DNS and redirects, blocks non-public destinations, and enforces the recorded fetch limits; a preview cannot make a blocked destination safe by changing only the UI label.

If a URL is excluded for robots, origin, path or content type, inspect the displayed reason and adjust only within the permitted source's scope. A timeout or failed fetch is not a ready index; refresh status before retrying a saved version. Changed source content creates a new revision rather than silently mutating an old snapshot. Continue with [previews](../previews.md), [runs](../runs.md), and [snapshot reuse](../source-history.md). The deterministic test uses `controlled.example` through a test-only transport; that hostname is not a reader-facing live endpoint.
