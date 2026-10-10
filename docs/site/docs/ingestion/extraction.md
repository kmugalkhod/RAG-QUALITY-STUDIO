---
verified_against: "1ada4b7 + spec 0009 slice 3 working tree (2026-10-10)"
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

The Extract settings show only the choices that need a decision: **Languages in scanned pages** and **If a file can't be read well** (**Stop and let me review** or **Publish the other files and show warnings**), plus **Upgrade extraction** for a pipeline saved with an older extractor. A saved policy that matches neither choice, such as **Strict** or edited thresholds, shows as **Custom (see Advanced)**. **Advanced extraction settings** holds **Maximum OCR pages** (100 by default), the quality policy with its thresholds, and the language policy. It is collapsed and states either "Using recommended settings." or which settings differ from the recommended values; **Reset to recommended** there restores them without changing the languages or a preset quality choice. A server error on an advanced field opens the section.

Scanned pages are always read with OCR when they have no text layer, at the recommended resolution, timeout, rotation and deskew. Text, tables and headings are read with the **Auto** strategy and tables keep their structure. A real-source test found that changing those values never changed a result, so the panel no longer shows them. A pipeline saved with a different value, such as OCR off or a 300 DPI resolution, keeps it and runs exactly as saved; the panel names it on one read-only line, for example "Uses an older custom setting: OCR resolution 300 DPI.", with its own **Reset to recommended**. That line counts once in the Advanced summary, and a server error on one of those values appears on it.

With `layout-ocr-v3` and later, website tables are kept as table rows with a header row, infobox-style tables become label and value rows, and reference lists, footnote lists and inline citation markers are left out, so citations do not crowd out the page's own facts. A PDF table whose columns were merged into single cells is rebuilt as one line per printed row, and long table cells are kept whole.

`layout-ocr-v4` and later add three things. A page printed sideways (its text runs up or down the page, as in landscape appendix tables) is read from a straightened copy, so its tables come out one line per printed row, header first; block boxes are drawn on the original page, and the page's rotation shows the turn. Tables in PowerPoint slides are read as tables, in slide order, with their slide number and header row. A word that the PDF breaks across lines with a soft hyphen, such as "house-/holds", is kept whole instead of being split into two words by cleaning.

`layout-ocr-v5`, the current extractor for new pipelines, adds two more. A chart is no longer read as a table: a detected table with fewer than 30% of its cells filled, usually a chart's gridlines, is read as ordinary text, so chart titles, callouts and data labels are kept and the chart no longer counts as a malformed table that stops the file. A table keeps its caption: when a block such as "Table A-2. Households by Total Money Income…" sits directly above a table, the table's blocks are filed under that caption, which replaces a notes or references heading (such as "Endnotes") carried over from an earlier page, and a table rebuilt row by row repeats all its header lines in each group. Saved `layout-ocr-v1` to `layout-ocr-v4` pipelines keep their output until you choose **Upgrade extraction**.

Website, Notion and Confluence pages are read as structured text, so for a pipeline whose sources are only those kinds the Extract settings show just the quality choice and, under **Advanced extraction settings**, the quality and language policies, and the stage card reads **Quality and language policies**. OCR languages, **Maximum OCR pages** and the older-setting line appear only when the pipeline has an uploaded-files or Amazon S3 source; saved values are kept either way.

1. In **Stage settings**, select **Extract**. Older saved versions may show **Enable robust extraction** first; upgrading creates an unsaved draft. Those native-text versions now report PDF quality findings, such as blank pages or garbled characters, as warnings with that upgrade as the remedy; the findings never change which documents publish. New drafts use the `layout-ocr-v5` extractor. A version saved with `layout-ocr-v1` to `layout-ocr-v4` keeps that extractor so earlier runs reproduce, and shows **Upgrade extraction**; saving the upgrade creates a new version, and its next run processes documents again.
2. Select installed **Languages in scanned pages**. OCR runs only when the server reports it available; otherwise the panel shows the server's reason and scanned pages stay unread. Under **Advanced extraction settings**, **Maximum OCR pages** bounds how many scanned pages of one file are read; more pages take longer but cost no provider money.
3. Select **Preview processing**, then **Inspect stages** for the item. Compare **Extracted** with **Raw** and inspect page origin, fallback reason, rotation, confidence, block overlay and table count where that file provides them.

Expected result: page metadata identifies native/layout/OCR origin when available, and the preview shows extracted blocks before cleaning. An image-only PDF with OCR off may have no usable text or a quality failure. OCR is not an assurance that every scan or table will be read correctly.

With `layout-ocr-v2`, a large PDF table is kept whole as consecutive table blocks, each repeating the header row, up to 2,000 rows, 50 columns and 1,000 characters per cell. Only a table beyond those limits is cut and reported as a malformed-table finding. DOCX, CSV, TSV and XLSX tables follow the same rule under `layout-ocr-v2`: each table (each XLSX sheet) is kept whole in consecutive blocks that repeat its first row as the header and follow **Table evidence**, instead of one block per row. A row too large to store twice in a block keeps its full text in its own block without the structured row copy. `layout-ocr-v1` keeps its original bound of 25 rows and 10 columns.

`layout-ocr-v2` also keeps PDF structure. **Auto** uses layout blocks for every page with native text, so headings, lists and boxes are kept, and falls back to the page's plain native text only when layout analysis loses more than a quarter of it (page reason **layout text loss**). A block is a heading when it is short, does not end like a sentence and is either noticeably larger than the page's body text or almost entirely bold; one bold word in a paragraph does not make it a heading. Heading levels follow font size, the first page's largest heading is the title, and each paragraph carries the headings above it, across page breaks, into section-aware chunks. OCR text under `layout-ocr-v2` is one block per scanned paragraph, in the OCR engine's reading order, with the paragraph's line count and line boxes for inspection.

Installed OCR language packs are read again at most every five minutes by each API and worker process, so a newly installed pack can take up to five minutes to appear in capabilities and save validation.

If OCR options are disabled, install/configure the required language packs on the server and reread capabilities. For a failed page, inspect the safe finding and the original authorized artifact; correct scan orientation/quality or adjust a bounded quality policy for a reason, then preview again. A changed extraction policy needs **Save version** before a run. See [quality findings](./quality.md), [cleaning](./cleaning.md), and [previews](./previews.md). Local deterministic PDF/OCR tests cover bounded cases; external OCR services and arbitrary document quality have not been verified.
