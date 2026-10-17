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
3. Select **Preview chunks**. In **Inspect stages → Chunks** read the count, boundaries, evidence text and any embedding prefix. The summary line gives the passage count, the median, smallest and largest size, passages under 40 bytes and any passage too large to embed.
4. Open **Advanced chunking settings** only to set exact sizes. Sizes are UTF-8 bytes (an English word is about six): **Target size (bytes)**, **Maximum size (bytes)** and **Overlap (bytes)**, or the child and parent sizes for Parent and child. **Help search find passages by their section title** adds the section title to the embedded text only; it is not shown in answers. The summary says **recommended** or **N changed**, and **Reset to recommended** restores Medium with section titles on.

Switching the method starts from its recommended sizes and replaces your settings; the notice that appears has an **Undo** button.

A passage, together with its section title, must fit the embedding provider's 8,191-byte limit, so a new version accepts a maximum of at most 7,891 bytes. A version saved with a larger maximum still opens and runs: it shows **Passages can be too large to embed** with **Reset sizes to recommended**, and if a passage is too large its run stops at the Chunk stage, naming the passage and page, before any embedding is paid for.

New pipelines use `section-token-v3` and `parent-child-v3`. Like v2, they append a short piece at the start of a section, such as a chart label that extraction read as a heading, to the passage before it on the same page, within the maximum. v3 also starts overlap and splits long text between words, never inside one, counts "。！？" as sentence ends, joins a remainder under 40 bytes to the passage next to it on the same page (or, when that passage is full, takes the closing words before it), carries a short first section on a page into the section after it, and leaves out of the section title a heading the passage already starts with. A passage can still be under 40 bytes when its page holds less than that, or when the passages next to it on the page are full or are tables, lists or code, which are never split. A version saved with an earlier version keeps its chunking so earlier runs reproduce; it shows **Saved with …**, a list of what each later version changes, and an **Upgrade chunking** button. A version saved with the original character window shows **Saved with the character window**, with its sizes under Advanced.

Expected result: the preview shows passage shape without embedding; the run embeds the passages and publishes a new ready index only on success. If a field is invalid, its own message says why, for example "Overlap must be smaller than the target." An empty field is invalid, not 0. See [quality](./quality.md), [source history](./source-history.md), [embedding](./embedding.md) and [publishing](./publishing.md).
