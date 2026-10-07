---
verified_against: "5c19271 + spec 0005 working tree (2026-10-07)"
title: Extraction and OCR
slug: /ingestion/extraction/
---

Choose how each page becomes readable blocks, then inspect its actual page origin before indexing. Schema-v2 extraction and local OCR are implemented; installed language packs and a source's scan quality are configuration and input gates, not guaranteed outcomes.

## Prerequisites

Upload a fictional TXT or text-based PDF as in [document preparation](../knowledge-base/prepare.md), or use a reviewed two-page synthetic PDF for a page-origin check. Create an [ingestion draft](./pipelines.md) and select **Extract** in the stage navigation. `GET /api/projects/{project_id}/ingestion-capabilities` reports the installed OCR languages and bounds for your local server; substitute the ID of an isolated project. A loopback owner request needs no token in local mode:

```sh
curl --fail http://127.0.0.1:8000/api/projects/<PROJECT_ID>/ingestion-capabilities
```

Expected response shape includes `ocr.available`, `ocr.languages`, and extraction/quality profiles. Replace `<PROJECT_ID>` with the created project's ID. If the endpoint returns 404/403, check project selection or access before editing a pipeline.

## Set and inspect

The Extract settings first show only the choices that need a decision: **Read scanned pages (OCR)**, **Languages in scanned pages** (while OCR is on) and **If a file can't be read well** (**Stop and let me review** or **Publish the other files and show warnings**). A saved policy that matches neither, such as **Strict** or edited thresholds, shows as **Custom (see Advanced)**. Every other setting is under **Advanced extraction settings**, which is collapsed and states either "Using recommended settings." or which settings differ from the recommended values; **Reset to recommended** restores them without changing the OCR choice, languages or a preset quality choice. A server error on an advanced field opens the section.

Website, Notion and Confluence pages are read as structured text, so for a pipeline whose sources are only those kinds the Extract settings show just the quality choice and, under **Advanced extraction settings**, the quality and language policies, and the stage card reads **Quality and language policies**. The OCR choice, strategy and table evidence appear when the pipeline has an uploaded-files or Amazon S3 source; saved values are kept either way.

1. In **Stage settings**, open **Advanced extraction settings** and use **Extraction strategy**: **Auto · page-level fallback**, **Native text**, or **Layout-aware**. Older saved versions may show **Enable robust extraction** first; upgrading creates an unsaved draft. Those native-text versions now report PDF quality findings, such as blank pages or garbled characters, as warnings with that upgrade as the remedy; the findings never change which documents publish. New drafts use the `layout-ocr-v2` extractor, which keeps the reading order of multi-column pages. A version saved with `layout-ocr-v1` keeps that extractor so earlier runs reproduce, and shows **Upgrade extraction**; saving the upgrade creates a new version, and its next run processes documents again.
2. **Read scanned pages (OCR)** switches between **Off** and **Automatic fallback**; under **Advanced extraction settings**, **OCR policy** also offers **Always**. The options are available only when the server reports OCR available. Select installed **Languages in scanned pages**, and under **Advanced extraction settings** bound **OCR resolution (DPI)**, **Maximum OCR pages**, and **Per-page timeout (seconds)**. Optional **Detect page rotation** and **Deskew scans** are bounded local corrections.
3. Select **Table evidence**: **Structured + Markdown**, **Markdown**, or **Plain text**. Select **Preview processing**, then **Inspect stages** for the item. Compare **Extracted** with **Raw** and inspect page origin, fallback reason, rotation, confidence, block overlay and table count where that file provides them.

Expected result: page metadata identifies native/layout/OCR origin when available, and the preview shows extracted blocks before cleaning. An image-only PDF with OCR off may have no usable text or a quality failure. OCR is not an assurance that every scan or table will be read correctly.

With `layout-ocr-v2`, a large PDF table is kept whole as consecutive table blocks, each repeating the header row, up to 2,000 rows, 50 columns and 1,000 characters per cell. Only a table beyond those limits is cut and reported as a malformed-table finding. DOCX, CSV, TSV and XLSX tables follow the same rule under `layout-ocr-v2`: each table (each XLSX sheet) is kept whole in consecutive blocks that repeat its first row as the header and follow **Table evidence**, instead of one block per row. A row too large to store twice in a block keeps its full text in its own block without the structured row copy. `layout-ocr-v1` keeps its original bound of 25 rows and 10 columns.

`layout-ocr-v2` also keeps PDF structure. **Auto** uses layout blocks for every page with native text, so headings, lists and boxes are kept, and falls back to the page's plain native text only when layout analysis loses more than a quarter of it (page reason **layout text loss**). A block is a heading when it is short, does not end like a sentence and is either noticeably larger than the page's body text or almost entirely bold; one bold word in a paragraph does not make it a heading. Heading levels follow font size, the first page's largest heading is the title, and each paragraph carries the headings above it, across page breaks, into section-aware chunks. OCR text under `layout-ocr-v2` is one block per scanned paragraph, in the OCR engine's reading order, with the paragraph's line count and line boxes for inspection.

Installed OCR language packs are read again at most every five minutes by each API and worker process, so a newly installed pack can take up to five minutes to appear in capabilities and save validation.

If OCR options are disabled, install/configure the required language packs on the server and reread capabilities. For a failed page, inspect the safe finding and the original authorized artifact; correct scan orientation/quality or adjust a bounded policy for a reason, then preview again. A changed extraction policy needs **Save version** before a run. See [quality findings](./quality.md), [cleaning](./cleaning.md), and [previews](./previews.md). Local deterministic PDF/OCR tests cover bounded cases; external OCR services and arbitrary document quality have not been verified.
