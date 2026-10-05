# Multi-source ingestion pipelines

Status: approved 2026-10-05; slices 1–5 done 2026-10-05 and verified end to end in the browser; slice 6 (concurrent site crawls and hardening) remains
Scope owner: Website ingestion, run lifecycle, ingestion editor, Knowledge Base lineage

## Purpose

Let one ingestion pipeline read several sources and either merge them into one index or build one index per source. This release supports **Website sources only**. The internals are keyed by source node, not by connector kind, so S3, Confluence, Notion and Existing Files can join later without another data-model change.

Answer pipelines are unchanged: a Retriever still selects one exact index version. Retrieving across several indexes is a separate later task.

## Decisions

These were decided in the owner interview on 2026-10-05.

| Topic | Decision |
| --- | --- |
| Connectors | Website only in this release. Mixed connector kinds are out of scope until a second connector is added. |
| Index layout | An explicit pipeline setting `index_layout`, either `merged` or `per_source`. The backend rejects a graph whose shape does not match. |
| Merged | 1–5 Website sources feed one shared Extract → Clean → Chunk → Embed → Publish chain, which builds one knowledge set. |
| Per source | Each source has its own full chain and settings inside one named pipeline. Each branch's knowledge set is named `<pipeline> · <host>` by default and can be renamed. One run group starts a child run per branch, and each child publishes on its own. |
| Source limit | At most 5 Website sources per pipeline. |
| Aggregate page cap | The sum of the sources' Maximum pages must not exceed 2,500. This is checked when saving and reported on the Maximum pages fields. |
| Merged failure | A source fails only on a whole-site failure: SSRF/DNS block, robots, sitemap seed or byte limit. A single failed page is excluded with its reason. A failed source carries forward its last good revisions, the other sources publish, and the run completes `with_warnings` with the reason for each failed source. If every source fails, the run fails and the previous ready index stays. |
| Stale carry-forward | If the Clean or Chunk settings changed since the failed source's last good revisions, those stored pages are reprocessed offline. This may cost embeddings but needs no re-crawl. |
| Duplicates | The existing raw-hash, cleaned-hash and simhash policy applies across every source in a merged run. The kept page records every source and URL it was found at. |
| Refresh | Merged pipelines get **Refresh this source**: the other sources are carried forward and a new merged version is published. Per-source pipelines get **Run this branch**. Full runs re-check every source incrementally. Schedules stay per pipeline version. |
| Busy branch | Starting a per-source group is atomic: if any branch's knowledge set already has an active run, nothing starts and the 409 response names that branch. |
| Changing layout | Saving with a different layout creates a new immutable version with new knowledge-set targets. Indexes built by the old layout stay ready. |

## Slices and acceptance criteria

Each slice is verified through its real path before the next starts.

### Slice 1 — correct merged fan-in for several Website sources (backend)

The current graph already lets several Website nodes feed one Extract node, and the worker crawls them in sequence. This slice makes that path correct and tested.

- Repeated page chrome (navigation, footer) is detected per source, so one site's pages never change how another site's pages are cleaned.
- The same URL reached from two sources is stored once. The run does not violate `uq_index_source_item`, and the kept revision's provenance lists both source nodes.
- Cross-site duplicates follow the pipeline's duplicate policy. The kept page records the excluded page's URL and source node.
- Prior revisions used for conditional requests and unchanged detection are matched by source node and location.
- Saving a pipeline with more than 5 Website sources, or mixing Website with another kind, returns a 422 that names the field.

Tests: two sites publish one index with both sites' pages; an overlapping URL; a cross-site duplicate under each policy; two sites sharing chrome text that is still kept on the site where it is not repeated; the save validation errors.

### Slice 2 — partial failure and carry-forward in merged runs

- A whole-site failure in one source records that source's outcome, keeps its last good revisions, and publishes the other sources. The run's `completion` is `with_warnings`.
- On a first run with no prior revisions, the failed source contributes nothing and the warning says so.
- If every source fails, the run fails as today.
- A failed source's previously indexed pages are never recorded as removed.
- If the processing config changed, the carried-forward pages are reprocessed from stored artifacts.
- The run read model exposes per-source outcomes: source node, host, status, error code, safe message and page counts.
- The run strip shows "Succeeded with warnings" and the reason for each failed source.

### Slice 3 — layout setting and merged editor

- Schema 2 executions gain an optional `index_layout` field (only `merged` for now, the default). This replaced the planned `IngestionExecutionV3`: a new schema version would have forked every schema-2 check in the editor for one field. Versions saved before the field read as merged; schema 1 versions run as merged.
- The editor can add and remove Website sources (1–5), with labeled, keyboard-accessible controls.
- The settings panel edits the selected source. Switching a source's connector kind is disabled while there are two or more sources.
- The 2,500-page aggregate cap is shown and validated on save.

### Slice 4 — refresh one source

- A merged run can be started for selected source nodes. It needs an existing ready index. The other sources are carried forward without requests to their sites.

### Slice 5 — per-source layout and run groups

- The validator accepts N disjoint chains in `per_source` layout, with unique publish targets.
- A run group starts one child run per branch atomically. One failed branch does not block the others from publishing.
- Groups can be listed, read and cancelled. Schedules start groups for per-source versions.
- The canvas draws branches. The results view shows each branch's outcome and links to its published index.

### Slice 6 — concurrent site crawls and hardening

- Sources in one run crawl concurrently with bounded concurrency inside the existing fair-share limits, without exhausting the database pool.
- The full isolated suites, Playwright journeys and desktop and mobile visual checks pass.

## Known limitations

- A snapshot's configuration hash covers every source, so refreshing one source still creates a new snapshot number.
- A per-source pipeline cannot yet be queried across all its branches; pick one branch's index in the answer pipeline.
