---
verified_against: "481b4eca90c5 + docs phase 2 working tree (2026-09-26)"
title: Website source
slug: /ingestion/sources/website/
---

Preview a bounded public website collection and publish only the included pages into an immutable index. Website fetching is implemented and covered by a deterministic HTTP transport, but these docs do not offer a hosted fixture or claim a live public-site run.

## Prerequisites

Use a public HTTP(S) site that you own or may crawl, with stable content and an origin you can allow. A loopback or private-network fixture is intentionally rejected by the SSRF boundary. Start with one small page to bound requests; external fetches can contact the site, while embedding that content can incur model charges. The exact dollar amount depends on the configured provider.

## Preview a permitted page

1. Open **Pipelines → Ingestion pipelines → New ingestion pipeline**. Select the Source node and choose **Website** under **Source type**.
2. Choose **Discovery mode**: **Single URL**, **URL list**, **Crawl from URL**, or **Sitemap**. Enter the **Starting URL** (or **URLs (one per line)**). Confirm **Allowed origins (one per line)** contains only the intended scheme and host.
3. Open **Scope & fetch limits**. Constrain **Maximum pages**, **Maximum crawl depth**, response/total bytes, timeout, deadline, concurrency, rate and redirects. Keep **Respect robots.txt** on unless you have an explicit reason and permission to change it. Optional include/exclude path prefixes start with `/`.
4. Select **Preview processing** and inspect each included, excluded, duplicate and failed item. Read its URL, reason, fetch mode and processing stages. Correct scope in the draft and preview again if needed. Select **Save version**, then **Collect source & publish index** only when the source and provider costs are acceptable.

Expected result: a bounded preview lists exact URL outcomes; a successful run reports new/changed/unchanged/removed counts and links to a ready index and [source snapshot](../source-history.md). It may include fewer pages than links on the seed page. The connector validates DNS and redirects, blocks non-public destinations, and enforces saved budgets; a preview cannot make a blocked destination safe by changing only the UI label.

If a URL is excluded for robots, origin, path or content type, inspect the displayed reason and adjust only within the permitted source's scope. A timeout or failed fetch is not a ready index; refresh status before retrying a saved version. Changed source content creates a new revision rather than silently mutating an old snapshot. Continue with [previews](../previews.md), [runs](../runs.md), and [snapshot reuse](../source-history.md). The deterministic test uses `controlled.example` through a test-only transport; that hostname is not a reader-facing live endpoint.
