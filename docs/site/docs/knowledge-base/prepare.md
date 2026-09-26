---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: Prepare uploaded content
slug: /knowledge-base/prepare/
---

Create an inspectable processing version before publishing a collection. Applies to the current local document path at commit `481b4eca90c5`, reviewed 2026-09-26.

## Prerequisite

Upload <a href="/examples/harbor-desk.txt" download>harbor-desk.txt</a> as described in [Documents](./documents.md). Processing a TXT file uses the local parser and character-window settings; no embedding call occurs until publication. More advanced extract, clean and chunk settings live in the [ingestion editor](../ingestion/pipelines.md).

## Prepare

1. Open **Knowledge Base → Documents** and select the file. In **Process: harbor-desk.txt**, expand **Advanced processing options** if you need to change **Chunk size (characters)** or **Overlap (characters)**. Overlap must be smaller than size.
2. Select **Start processing**. This creates a new version. Use **Refresh history** until the run reaches a terminal state.
3. Select **Inspect 1 chunks** or the displayed count. Inspect passage text and start/end character offsets; the end offset is exclusive. A PDF inspector shows its page when available.

Expected result: one successful processing run and at least one passage. If parsing fails, inspect the run, correct file/settings, then start a new version; a previous successful version remains historical. Cancelled or failed runs are not published. For an image-only PDF, check OCR capability before retrying, rather than expecting text extraction. Next, [publish a collection](./collections.md). The exact chunk count is data/settings dependent; no live OCR engine is validated by this page.
