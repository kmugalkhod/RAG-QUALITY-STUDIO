# Ingestion editor: sources panel and shared stages

Status: approved and done 2026-10-06 (owner chose option A of the mockups at https://claude.ai/artifact/XLMx1WEmc5wAN2U55rVy12)
Scope owner: ingestion editor (frontend only; the saved execution format does not change)

## Problem

With several Website sources the editor hid pipeline-wide decisions (merged or per-source indexes, adding, removing and refreshing sources) inside one source's settings, and a per-source layout drew a full copy of every stage for every source, up to 30 cards. Run results were spread over three places.

## Design

Applies to Website pipelines on schema 2. Other connectors and schema-1 drafts keep the current editor.

- **Sources panel** (left, 320px on desktop, above the canvas below 1152px): one card per source with its site, last-run status and reason, page counts and, in a per-source layout, its index name and which stages it customizes. Card actions: **Refresh only this** (merged) or **Run only this** (per source) and **Remove**. **Add website**, the page total against the 2,500 cap, and the **Output** choice (**One combined index** or **One index per source**) sit in the same panel.
- **Compact canvas**: one grouped sources card, then Extract, Clean, Chunk, Embed and Publish once. In a per-source layout Publish fans out to one card per source index. Stage cards say how many sources customize them. Cards are not draggable in this view; saved coordinates are kept unchanged for the API.
- **Settings panel** edits only the selection: a source, a stage, or a source's index. In a per-source layout a stage has **Applies to**: **All sources (shared)** or one source. A source that follows the shared settings shows **Customize … for this source**; a customized source shows its own values and **Use shared settings**. **All sources** lists the customized sources, which do not follow shared edits. With one combined index every source shares every stage, so **Applies to** is not shown.

## Shared settings without a schema change

A per-source version still saves one complete chain per source. The editor derives the shared settings of each stage as the configuration most branches use (ties go to the earliest source); a branch whose configuration differs is customized. Customizing copies the shared values to that branch and marks it customized for the editing session until its values differ; **Use shared settings** copies the shared values back. Shared edits are applied to every branch that is not customized. Adding a source copies the shared settings, and switching back to one combined index keeps the shared settings, not the first branch's.

## Acceptance criteria

- Pipeline-wide controls are no longer in a source's settings; the sources panel carries them.
- A per-source pipeline with 5 sources shows at most 12 canvas cards.
- In a per-source layout, Extract, Clean, Chunk and Embed can be customized for one source and reset; shared edits do not change customized sources; each source's index can be renamed.
- The saved execution format, previews, runs, refresh-one-source and run groups behave as before.
- Unit tests cover the shared-settings derivation and the panel; the flow is verified in the browser on desktop and at 390px.
