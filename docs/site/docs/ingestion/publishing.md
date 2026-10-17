---
verified_against: "spec 0012 slice 8 working tree (2026-10-18)"
title: Publishing an index
slug: /ingestion/publishing/
---

Each successful run that changed something publishes a new version of an index that answer pipelines can search. Earlier versions stay available, and an answer pipeline keeps the version it uses until you switch it.

## Prerequisites

Use a [saved ingestion pipeline](./pipelines.md). Publishing does not embed passages again; it makes the run's embedded passages available as one immutable version.

## Choose where to publish

1. Select **Publish index**. Choose **New index** and enter its **Index name**, or **Add a version to an existing index** and pick it from the list. A new pipeline's index is named after the pipeline, and the name follows a rename until you type your own.
2. A new name may not be the name of another pipeline's index, ignoring case; the field says so and the version cannot be saved. After a pipeline's first run created its index, later versions of the same pipeline add versions to it.
3. The stage says what the next run does, for example "This run publishes version 4 of Python tutorial. Version 3 stays available; if nothing changed, no version is published and it stays current. Answer pipelines keep their version until you switch." If other pipelines also publish to the index, it names them: each run replaces the version answers use by default.
4. After a run, the status line says **Replaced version M; it remains available**, or **Version M is still current** when the run failed or was cancelled. **Use in answer pipeline** opens a new answer pipeline with the published version selected.
5. A run whose passages and embedding settings are the same as the current version, for example a refresh of sources that did not change, publishes nothing: it succeeds with **No changes; version M stays current**, makes no embedding requests, and **Use in answer pipeline** selects version M. Any change, such as an added, edited or removed file or page, or other cleaning or chunking settings, publishes a new version.

Two runs of the same index cannot run at once; a second start, for example a schedule and a manual run together, is refused with a message instead of an error. Only a run whose index finished embedding reports a published version.

Continue with [runs](./runs.md), [answer pipelines](../answers/pipelines.md) and [collection versions](../knowledge-base/collections.md).
