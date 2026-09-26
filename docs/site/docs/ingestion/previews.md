---
verified_against: "481b4eca90c5 + docs phase 2 working tree (2026-09-26)"
title: Preview processing
slug: /ingestion/previews/
---

Inspect the exact unsaved ingestion configuration and its item-level outcomes before committing to an index run. A preview is a bounded local/source operation: it does not embed, publish, or advance a ready index pointer, though a remote preview may fetch source content and retain bounded protected artifacts.

## Prerequisites

Create a schema-v2 [ingestion draft](./pipelines.md) with an explicit source. **Existing files** and the fictional <a href="/examples/harbor-desk.txt">Harbor sample</a> need no remote account; Website and credentialed sources have the gates on their [source pages](./sources/index.md). Remote collection may have API/network cost. Embeddings are charged on a later run, not on this processing preview.

## Preview and inspect

1. In the **Ingestion editor**, review **Unsaved changes** and each selected node's **Stage settings**. Select **Preview processing**. The server records an exact configuration hash and returns a queued/running preview; wait for its terminal status.
2. Read the **Processing preview** counts: included, excluded, duplicate, failed, and quality pass/warn/exclude/fail. Read each item's reason, canonical location, provider revision, fetch mode and processing status. Items are paginated.
3. Select **Inspect stages** on an item. Use **Raw**, **Extracted**, **Cleaned**, **Changes**, and **Chunks** tabs; a stage may be empty or protected. Page through bounded records. Compare the text and measurements before deciding whether the draft is safe to save.

Expected result with one prepared `harbor-desk.txt`: one included item, inspectable stages, and no new ready collection from the preview alone. The **exact config** hash identifies this draft even if it has not been saved. The [Existing Files tutorial](./pipelines.md) is a complete deterministic browser journey for this case.

If validation blocks **Preview processing**, resolve the named field in **Stage settings**. Use **Cancel preview** on an active preview; after failure, cancellation or expiry use **Retry preview** only after checking its reason and whether the source changed. A retry can refetch a remote source and its state may differ. Sensitive Raw and Changes require owner/admin access and retained encrypted artifacts. Continue with [quality findings](./quality.md) and [run inspection](./runs.md). The current preview contract is deterministically tested; live external accounts remain unverified.
