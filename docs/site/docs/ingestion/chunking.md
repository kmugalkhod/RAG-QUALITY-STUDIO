---
verified_against: "spec 0012 slice 4 working tree (2026-10-18)"
title: Chunking
slug: /ingestion/chunking/
---

Choose how cleaned text is split into passages that search finds and answers cite. Changing a chunking setting creates a new index version rather than rewriting an old ready one.

## Prerequisites

Use a [saved source and extraction draft](./pipelines.md) and a source you may process. Previews are free; a run embeds the passages, see [embedding](./embedding.md).

## Choose a method and a size

1. Select **Chunk**. Choose **Section-aware (recommended)**, which keeps headings and the text under them together, or **Parent and child**, which is better for tables and short facts: search finds a small passage and answers get the larger one around it.
2. Choose a **Passage size**: **Small**, **Medium (recommended)** or **Large**, each with about how many words it holds.
3. Select **Preview chunks**. In **Inspect stages → Chunks** read the count, boundaries and evidence text. **Searched as** shows what a passage is searched by when that is not just its text: its section prefix, and for a table row its "column: value" text. The same appears in **Run details → Inspect content → Chunks** and in the index's stored passages. The summary line gives the passage count, the median, smallest and largest size, passages under 40 bytes and any passage too large to embed.
4. Open **Advanced chunking settings** only to set exact sizes. Sizes are UTF-8 bytes (an English word is about six): **Target size (bytes)**, **Maximum size (bytes)** and **Overlap (bytes)**, or the child and parent sizes for Parent and child. **Help search find passages by their section title** adds the section title to the embedded text only; it is not shown in answers. The summary says **recommended** or **N changed**, and **Reset to recommended** restores Medium with section titles on.

Switching the method starts from its recommended sizes and replaces your settings; the notice that appears has an **Undo** button.

A passage, together with its section title, must fit the embedding provider's 8,191-byte limit, so a new version accepts a maximum of at most 7,891 bytes. A version saved with a larger maximum still opens and runs: it shows **Passages can be too large to embed** with **Reset sizes to recommended**, and if a passage is too large its run stops at the Chunk stage, naming the passage and page, before any embedding is paid for.

`section-token-v3` and `parent-child-v3` (spec 0012) are what the later versions build on. Like v2, they append a short piece at the start of a section, such as a chart label that extraction read as a heading, to the passage before it on the same page, within the maximum. v3 also starts overlap and splits long text between words, never inside one, counts "。！？" as sentence ends, joins a remainder under 40 bytes to the passage next to it on the same page (or, when that passage is full, takes the closing words before it), carries a short first section on a page into the section after it, and leaves out of the section title a heading the passage already starts with. A passage can still be under 40 bytes when its page holds less than that, or when the passages next to it on the page are full or are tables, lists or code, which are never split. A version saved with an earlier version keeps its chunking so earlier runs reproduce; it shows **Saved with …**, a list of what each later version changes, and an **Upgrade chunking** button. A version saved with the original character window shows **Saved with the character window**, with its sizes under Advanced.

`section-token-v4` and `parent-child-v4` (spec 0014) are available for saved pipelines; new drafts do not use them. They chunk text exactly as v3 and give each row of a table its own passage. The passage shows the table's header when it fits, the row's group label (a row such as "ALL RACES" with text only in its first cell; wrapped labels join) and the row. It is searched by its section, its group label and "column: value" pairs, so a question that names a year and a column can match one row instead of a block of look-alike rows. A group label carries on to the table's continuation pages in the searched text. In `parent-child-v4`, parents are built as in v3 and each table row is a child of its own. A table whose text does not match its stored rows is chunked as in v3.

New pipelines use `section-token-v5` and `parent-child-v5` (spec 0015) since its proof round on real sources (2026-10-22), which found they lose no answer and no top-5 search hit against v3. They keep every v3 passage unchanged, so a question about a list across several rows still finds the whole table, and add the v4 row passages beside it: in `section-token-v5` each row passage follows the passage that holds its table, and in `parent-child-v5` each row is an extra child of the parent that holds it, so the prompt receives the whole table. A table whose first row has text only in its first cell, such as a spreadsheet title, takes the next row with at least half of its cells filled as its header: the rows above it are shown with each row, its cells name the columns, and the title opens the row's searched text.

Expected result: the preview shows passage shape without embedding; the run embeds the passages and publishes a new ready index only on success. If a field is invalid, its own message says why, for example "Overlap must be smaller than the target." An empty field is invalid, not 0. See [quality](./quality.md), [source history](./source-history.md), [embedding](./embedding.md) and [publishing](./publishing.md).
