# Source snapshots and reusable index variants

Status: proposed, not implemented
Scope owner: Website ingestion, Knowledge Base, answer-pipeline handoff, and experiment lineage
Last updated: 2026-09-22

## Purpose

Let a user collect a website once, keep that exact collected content as an immutable **source snapshot**, and use it to build multiple independent indexes with different supported ingestion settings. Users can then connect each index to an answer pipeline and compare those pipelines on the same evaluation dataset.

The product must make the lineage obvious:

```text
Website
  └─ Source snapshot 3 · 43 pages · collected Sep 22
       ├─ Precise chunks index · 612 passages
       │    └─ Answer pipeline A
       ├─ Balanced index · 284 passages
       │    └─ Answer pipeline B
       └─ Broad context index · 171 passages
            └─ Answer pipeline C

Answer pipelines A/B/C
  └─ One experiment · same dataset · same source snapshot
```

This is a controlled comparison workflow, not automatic optimization. The application reports measured quality, latency, failures, and known cost; it does not declare a universal winner.

## Scope decisions

The following decisions are fixed for this plan:

- Implement the reusable snapshot workflow for **Website sources first**. Existing Files, S3, Notion, and Confluence keep their current behavior.
- A source snapshot is project-scoped, immutable, and contains exact item/revision membership plus the stored artifacts needed for offline rebuilding.
- One ready source snapshot may feed multiple knowledge sets. Each knowledge set remains the stable named index family, and every successful build creates an immutable version within that family.
- Index variants initially differ only through settings the ingestion engine already supports, especially chunk size, chunk overlap, and destination knowledge set. Adding per-pipeline embedding-provider selection is outside this scope.
- Every index version records the exact source snapshot, ingestion-pipeline version, processing settings, and embedding configuration used to build it.
- Answer pipelines continue selecting an exact immutable index version. They never silently follow the current-ready index.
- Experiments continue comparing saved answer-pipeline versions. This work adds visible source-snapshot lineage and comparison warnings; it does not add new metrics or automatic tuning.
- Existing schedules are not redesigned. A scheduled Website refresh may create a new source snapshot and index version through the existing saved ingestion version, but schedules do not automatically rebuild every variant.
- No snapshot deletion or retention policy is added in this slice. Snapshots and their artifacts remain immutable because historical indexes and experiments may depend on them.

## Non-goals

- No multi-source or cross-project snapshot composition.
- No arbitrary branching or executable workflow nodes.
- No automatic generation of many configurations.
- No automatic recommendation without a completed measured experiment.
- No live-page diff editor, content editing, or manual mutation of snapshot membership.
- No connector expansion, new vector store, reranker, or hybrid-search work.
- No changes to authentication, deployment, or billing scope.
- No replacement of the existing Knowledge Base visual system.

## Terminology and product copy

Use one term consistently at each layer:

| Product term | Meaning | Avoid |
| --- | --- | --- |
| Source | The configured Website location and crawl boundary | Scraper job |
| Source snapshot | Immutable set of pages and exact revisions collected together | Cache, stored pages, scrape dump |
| Collect source | Fetch the Website and create a new source snapshot | Scrape now |
| Refresh source | Fetch the Website again and create a newer snapshot | Reprocess |
| Index | A searchable output built from one source snapshot | Document set |
| Index version | One immutable build within a named knowledge set | Latest data |
| Build index variant | Build another named index from an existing snapshot | Reprocess stored pages |

Required helper copy:

> Build another index from the content already collected. The website will not be requested again. Embedding costs may still apply.

Required experiment confirmation:

> Same source snapshot. Differences are caused by the selected index and pipeline configurations, not different collected content.

Required mismatch warning:

> These pipelines use different source snapshots. Quality differences may come from changed source content as well as configuration.

## Current behavior and gap

The current implementation already provides useful foundations:

- Website ingestion stores immutable source items, source revisions, artifacts, provenance, and exact index membership.
- `Refresh website & run` fetches the Website and publishes an index.
- `Reprocess stored pages` can avoid another network fetch and apply a changed Website pipeline to stored artifacts.
- Knowledge Base groups immutable index versions by knowledge set and exposes records and retrieval checks.
- Answer pipelines bind to exact index IDs, and experiments bind to exact saved answer-pipeline versions.

The gap is that offline Website rebuilding obtains artifacts through the destination knowledge set's current-ready index. A stored collection cannot yet be selected independently and reused to build another knowledge set. Knowledge Base also does not expose a first-class source snapshot or show complete source → snapshot → pipeline → index lineage.

## User journey

### 1. Collect the Website once

From a saved Website ingestion pipeline, the user selects **Collect source & build index** for the first run. The run:

1. Discovers and fetches the configured Website within existing safety limits.
2. Creates a durable source snapshot only after required collection succeeds.
3. Continues through extraction, cleaning, chunking, embedding, and atomic index publication.
4. Links the published index version to the new source snapshot.

The completion state says:

> Source snapshot 3 collected: 43 pages. Balanced index version 1 is ready with 284 passages.

### 2. Build another index without fetching again

From the source snapshot in Knowledge Base, the user selects **Build index variant**. The flow asks for:

- A destination index name, creating a new knowledge set or selecting an existing compatible one.
- A saved Website ingestion-pipeline version whose Website source configuration matches the snapshot source identity.
- Confirmation of the exact snapshot and effective chunk settings.

Submission immediately returns a durable ingestion job. The worker reads the snapshot's stored artifacts and performs downstream processing without constructing or calling the Website connector.

### 3. Inspect indexes clearly in Knowledge Base

The user can see every index family and version, the source snapshot used, the effective configuration, progress, failures, records, and current-ready status.

### 4. Create answer pipelines

From a ready index version, **Use in answer pipeline** opens the answer-pipeline editor with that exact index preselected. Saving remains explicit; navigation alone never creates a pipeline.

### 5. Compare performance

In Experiments, the user selects two saved answer-pipeline versions and a dataset. The setup displays whether both candidates use the same source snapshot. Results continue to report per-question answers, evidence, metric availability, latency, failure counts, and cost basis.

## Knowledge Base information architecture

Keep the existing Knowledge Base route and split-pane interaction. Do not add a new workspace navigation item.

Rename the current **Document sets** tab to **Indexes**. The top-level tabs become:

- **Documents** — uploaded files and their processing history, unchanged.
- **Indexes** — Website source snapshots, named index families, immutable index versions, records, and retrieval checks.

Within **Indexes**, use two URL-addressable views:

- `view=indexes&mode=snapshots` — source snapshots and their downstream indexes.
- `view=indexes&mode=indexes` — index families and versions, optimized for locating an exact index.

Default to **Indexes** for returning users and to **Source snapshots** immediately after a Website collection completes.

### Source snapshots view

The left catalog groups snapshots by source identity. A Website source group shows its canonical origin and crawl scope summary. Each snapshot row shows:

- Snapshot number and `Ready`, `Collecting`, `Failed`, or `Cancelled` state.
- Collection timestamp.
- Included page count and total stored bytes.
- New, changed, unchanged, removed, excluded, duplicate, and failed counts when available.
- Number of index versions built from the snapshot.

Selecting a snapshot opens the detail inspector with:

1. Source identity and safe crawl-scope summary.
2. Exact collection status and counts.
3. Paginated included items with canonical location, media type, revision metadata, and collection outcome.
4. **Build index variant** as the primary action when the snapshot is ready.
5. **Refresh source** as a separate secondary action that creates a new snapshot.
6. A list of downstream index versions already built from this snapshot.

The empty state says:

> No Website snapshots yet. Run a saved Website ingestion pipeline to collect reusable source content.

### Indexes view

The left catalog keeps the existing knowledge-set grouping but uses the user-facing term **Indexes**. Each index-family heading shows:

- Index name.
- Number of immutable versions.
- Current-ready version.
- Source snapshot used by the current-ready version.

Each version row shows, without opening the detail panel:

- Version number and Ready/Preparing/Failed/Cancelled state.
- Current or Historical label.
- Passage count.
- Source snapshot number and collection date.
- Ingestion-pipeline name and version.
- Compact chunk setting summary.
- Embedding model identifier.

Selecting an index version opens the existing record and retrieval inspector with a new **Build lineage** section above the statistics:

```text
Source snapshot 3
Collected Sep 22 · 43 pages
        ↓
Balanced Website ingestion · version 2
1,000 characters · 120 overlap
        ↓
Balanced index · version 1
284 passages · Ready
```

The detail actions are:

- **Use in answer pipeline** — opens an answer-pipeline draft with the exact index selected.
- **Build another variant** — starts from the same source snapshot.
- Existing record inspection and retrieval check actions.

Do not show a generic **Prepare document set** action for Website-derived indexes. Uploaded-document indexing keeps its existing creation path and is labelled separately.

### Responsive behavior

- Desktop keeps the catalog and adjacent detail inspector.
- Tablet may narrow the catalog, but version identity, status, snapshot, and passage count remain visible.
- Mobile shows the catalog first; selecting a snapshot or index replaces it with a full-width detail view with an explicit Back action.
- Dense lineage metadata collapses into labelled rows on mobile; it must not become a horizontally scrolling table.
- Primary and secondary actions remain at least 44px high and keyboard reachable.

## Ingestion editor changes

The visual graph remains an editor for a supported ingestion configuration. Do not add a fake snapshot node or arbitrary graph branching.

For a saved Website ingestion version, replace ambiguous execution actions with:

- **Collect source & build index** — performs a new Website fetch, creates a source snapshot, and builds the configured destination index.
- **Build from snapshot** — opens a pipeline-level panel for selecting a compatible ready source snapshot and destination index.

The selected snapshot is an execution input, not a mutation of the source node. The run snapshot records both the saved pipeline version and chosen source snapshot.

The **Build from snapshot** panel displays:

- Source origin.
- Snapshot number, timestamp, and page count.
- A clear statement that the Website will not be fetched.
- Effective chunk configuration.
- Destination index name.
- Embedding configuration and the warning that embedding cost may apply.

If source selection, origin, or crawl scope differs from the chosen snapshot, server validation rejects the run and the UI maps the safe error to the source selector:

> This snapshot was collected with different Website source settings. Choose a compatible snapshot or collect the source again.

## Data model plan

Add explicit collection membership instead of resolving reuse through an index:

### `source_snapshots`

- `id`, `project_id`, `source_kind` (`website` in this slice).
- Immutable source-configuration snapshot and deterministic source-configuration hash.
- Status: `collecting`, `ready`, `failed`, or `cancelled`.
- Counts: discovered, included, excluded, duplicate, failed, new, changed, unchanged, removed.
- Total stored bytes where known.
- Connector version and safe source identity metadata.
- Creating ingestion run ID and timestamps.
- Composite project ownership constraints and indexes for project/source/date browsing.

Only a complete collection becomes `ready`. Failed or cancelled collections remain inspectable but cannot build an index.

### `source_snapshot_members`

- `snapshot_id`, `project_id`, `source_node_id`, `source_item_id`, and captured `source_revision_id`.
- Stable ordinal for pagination.
- Inclusion state and safe provenance needed by the inspector.
- Unique membership per snapshot/source item.
- Composite foreign keys that prevent cross-project membership.

The membership references immutable source revisions and generated artifact storage names already owned by the application. It does not copy raw bodies into PostgreSQL.

### Existing records

- Add nullable `source_snapshot_id` to Website ingestion runs and index versions through project-scoped composite foreign keys.
- Successful builds from a snapshot require an exact snapshot ID.
- Index reads expose snapshot ID, display number, collection time, source kind, ingestion-pipeline identity/version, and effective processing summary.
- Query and experiment snapshots already preserve exact index identity; extend their inspectable lineage with the source snapshot ID rather than resolving it from current state later.

### Migration and historical data

Backfill only when lineage can be proven:

1. A successful Website network-refresh run with complete `index_source_revisions` membership creates one legacy-compatible source snapshot.
2. A successful stored-artifact reprocessing run inherits the proven snapshot of its recorded `prior_ready_index_id`.
3. Multiple indexes that used the same proven captured membership point to the same snapshot.
4. If historical membership or prior-index lineage is incomplete, leave `source_snapshot_id` null and show **Legacy index — source snapshot unavailable**. Never invent equivalence.

The migration must preserve every existing index ID, current-ready pointer, pipeline version, query result, experiment result, and artifact.

## API plan

Add project-scoped, paginated reads:

- `GET /projects/{project}/source-snapshots`
- `GET /projects/{project}/source-snapshots/{snapshot}`
- `GET /projects/{project}/source-snapshots/{snapshot}/items`
- `GET /projects/{project}/source-snapshots/{snapshot}/indexes`

Replace the boolean `reuse_stored` request with a discriminated execution input while retaining backward compatibility during migration:

```json
{ "source_input": { "kind": "refresh" } }
```

or

```json
{
  "source_input": {
    "kind": "snapshot",
    "source_snapshot_id": "..."
  }
}
```

The snapshot mode must:

- Require a ready Website snapshot in the same project.
- Validate the saved pipeline's source identity and selection bounds against the snapshot configuration.
- Permit a different destination knowledge set.
- Never construct the Website connector or make a network request.
- Reuse compatible processed chunks and embeddings where their full processing and embedding hashes match.
- Create new chunks and embeddings where configuration differs.
- Preserve the prior current-ready index until the new build succeeds completely.

Extend existing index list/detail responses with bounded lineage summaries instead of requiring one request per row. Keep full snapshot membership behind its paginated endpoint.

## Worker and integrity behavior

- Collection and index construction remain distinct durable stages even when one user action runs both sequentially.
- A collection checkpoint publishes snapshot membership atomically only when required fetches and artifact writes succeed.
- A snapshot build reads only explicit immutable membership; it never queries all current project source items.
- Duplicate task delivery cannot create duplicate ready snapshots, indexes, provider work, or charges.
- Cancellation stops scheduling new work and records whether a ready source snapshot was already completed before downstream index cancellation.
- Snapshot builds retain current fenced execution tokens, bounded retries, concurrency limits, and provider-rate limits.
- An active build remains constrained per destination knowledge set. Separate destinations may build from the same snapshot concurrently only within configured embedding/provider concurrency limits.
- Snapshot reuse avoids connector/network cost, not necessarily parsing, chunking, or embedding cost.
- Logs use IDs and counts, never raw page bodies, credentials, or secret URL parameters.

## Answer-pipeline and experiment handoff

### Answer pipelines

- `Use in answer pipeline` navigates to a new answer-pipeline draft with the selected exact index version preselected.
- The retriever settings continue to display knowledge-set name and exact index version.
- Add a read-only lineage line: `Source snapshot 3 · collected Sep 22`.
- Changing to another index remains an explicit draft edit followed by an explicit save.

### Experiments

- Candidate setup shows index name/version and source snapshot for each saved answer-pipeline version.
- If all candidates share one snapshot, display **Same source snapshot**.
- If snapshot IDs differ or any candidate has unavailable legacy lineage, display a comparison caveat before submission and retain it in results/export.
- Do not block mismatched comparisons; users may intentionally compare refreshed content.
- Results continue using exact saved candidates and existing aggregation rules. Do not infer causation or call a configuration best without the user's stated criteria.

## Delivery slices

Implement in reviewable vertical slices. Do not render later-slice controls as functional before their backend paths exist.

### Slice 1 — Snapshot persistence and reads

- Add migrations, models, schemas, service reads, and project-scoped paginated APIs.
- Create a ready Website snapshot during a successful new Website collection.
- Link the first published index to that snapshot.
- Backfill only provable historical lineage.
- Add backend tests for immutability, exact membership, pagination, project isolation, failure, cancellation, and migration preservation.

Acceptance boundary: API consumers can inspect a real ready Website snapshot and its exact items, but cannot yet build a second destination from it.

### Slice 2 — Build an independent index from a snapshot

- Add the discriminated run input.
- Validate source compatibility and destination ownership.
- Build a second knowledge set from the same snapshot without Website network calls.
- Preserve atomic publication, duplicate protection, cancellation, and cost metadata.
- Keep the compatibility adapter for the old `reuse_stored` client until the frontend migrates.

Acceptance boundary: one captured snapshot can produce two ready, independently named knowledge sets with different supported chunk configurations.

### Slice 3 — Knowledge Base workflow

- Rename **Document sets** to **Indexes**.
- Add Source snapshots and Indexes modes with URL-addressable selection.
- Add snapshot detail/items/downstream-index inspection.
- Add index lineage, **Build index variant**, and **Use in answer pipeline**.
- Implement loading, empty, collecting, ready, failed, cancelled, validation, progress, retry, and mobile states using real APIs.

Acceptance boundary: a user can understand and complete the collect-once/build-many workflow without opening raw API data or interpreting internal IDs.

### Slice 4 — Pipeline and experiment lineage

- Replace the Website run copy with the two explicit execution choices.
- Add the snapshot selection panel and authoritative validation mapping.
- Show exact snapshot lineage in answer pipelines and Experiments.
- Add same-snapshot confirmation and mismatch caveat to experiment setup, results, and export.

Acceptance boundary: the complete path from one collection through two indexes, two answer pipelines, and one comparison experiment is reproducible and inspectable.

### Slice 5 — Hardening and documentation

- Verify clean migration and supported populated upgrades.
- Run backend lint/format and the complete isolated PostgreSQL/pgvector suite.
- Run frontend format, lint, strict TypeScript, unit tests, production build, and affected browser regressions.
- Run an isolated browser journey for one Website snapshot, two index variants, two saved answer pipelines, and a paired experiment without live providers.
- Inspect Knowledge Base, pipeline, and experiment states once at desktop and mobile widths.
- Update architecture, development, deployment, and user-facing documentation to match verified behavior.

## Acceptance criteria

The feature is complete only when all of the following are true:

1. A successful Website collection creates one immutable, project-scoped, ready source snapshot with exact revision membership.
2. Failed or cancelled collection never exposes a partial snapshot as ready.
3. A user can build at least two independently named knowledge sets from the same snapshot without any Website request.
4. The two builds may use different supported chunk sizes/overlaps and record their exact effective configurations.
5. Each successful build publishes a new immutable index version atomically; a failed build leaves prior ready versions and pointers unchanged.
6. Knowledge Base clearly distinguishes source snapshots, index families, and index versions.
7. Every Website-derived index detail shows its snapshot, collection time, pipeline version, chunk settings, embedding configuration, status, and passage count.
8. Snapshot and index item collections are paginated and project isolated.
9. The answer-pipeline handoff preselects an exact index but does not save automatically.
10. Experiment setup and results show whether candidates share the same source snapshot.
11. Historical records are backfilled only when equivalence is provable; uncertain legacy lineage is labelled unavailable.
12. Network, embedding, and evaluation costs are separated; snapshot reuse is never described as free.
13. Desktop, tablet, keyboard, 200% zoom, and mobile flows remain usable without hidden actions or horizontal overflow.
14. Existing uploads, non-Website connectors, saved index IDs, queries, experiments, schedules, and historical evidence remain compatible.

## Required test matrix

### Backend

- Clean migration and populated upgrade with existing Website refresh/reprocess history.
- Exact snapshot membership and immutable reads.
- Cross-project snapshot selection rejection.
- Source-config mismatch rejection.
- Ready/failed/cancelled snapshot state invariants.
- Two destinations from one snapshot.
- Different chunk configurations from one snapshot.
- Compatible chunk/vector reuse and incompatible reprocessing.
- No Website adapter construction in snapshot mode.
- Duplicate delivery, stale recovery, cancellation, destination overlap, and atomic publication.
- Historical index/query/experiment preservation.

### Frontend unit/component

- Snapshot and index lineage formatting.
- Empty/loading/error/legacy-lineage states.
- Snapshot and index URL restoration.
- Build form validation and server error mapping.
- Same-snapshot and mismatch experiment messages.
- Exact-index answer-pipeline handoff.

### Browser

- Collect one controlled Website snapshot.
- Build precise and balanced indexes without a second source request.
- Inspect both in Knowledge Base, including records and lineage.
- Create/save one answer pipeline per index.
- Run one paired experiment against the same dataset.
- Confirm same-snapshot status, per-question evidence, failures, latency, and cost basis.
- Repeat the essential Knowledge Base flow at 390px width and with keyboard navigation.

## Documentation updates after implementation

- `docs/architecture.md`: snapshot boundary, exact membership, build lineage, and compatibility behavior.
- `docs/implementation-plan.md`: slice status, verification evidence, limitations, and next action.
- `docs/development.md`: API examples, deterministic provider setup, and snapshot-build troubleshooting.
- `docs/deployment.md`: artifact storage growth, backup/restore consistency, and retention limitation.
- `README.md`: concise collect-once/build-many user workflow only after it is verified.

## Remaining limitations after this plan

Even after all slices are complete:

- Reusable source snapshots apply only to Website sources.
- Embedding provider/model selection remains application-configured rather than a per-variant editor choice.
- Users manually choose configurations; the application does not search the configuration space.
- A fair comparison still requires a reviewed dataset and appropriate metrics.
- Source snapshots and historical artifacts have no deletion/retention UI in this scope.
- Shared deployment still requires authentication and project authorization.
