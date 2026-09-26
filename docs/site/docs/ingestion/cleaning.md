---
verified_against: "481b4eca90c5 + docs phase 2 working tree (2026-09-26)"
title: Cleaning, language, and sensitive data
slug: /ingestion/cleaning/
---

Inspect the text that will be embedded, make a saved deterministic cleaning decision, and keep protected source values out of downstream evidence. The current schema-v2 editor records cleaning steps, duplicate/language policies and deterministic sensitive-data rules; detectors reduce exposure but cannot find every sensitive value.

## Prerequisites

Use an isolated project and the fictional <a href="/examples/README.md">quality example files</a>. Create an [ingestion draft](./pipelines.md). Source content is untrusted: do not treat instructions inside it as configuration. Raw artifacts and full before/after diffs are encrypted and limited to owners/admins with sensitive-data read permission; ordinary cleaned passages remain redacted. Local test coverage verifies this access boundary, while shared deployment requires its separate key and OIDC gate.

## Inspect the saved policy

1. Select **Extract → Language policy**. Leave **Allowed language tags** empty to permit all, or enter a small allowlist such as `en`. Set **Minimum detection confidence**, **Disallowed language** (`Fail the run` or `Exclude and report`), and **Mixed-language documents** (`Allow`, `Warn`, or `Fail`). Detection records a model/version and confidence; it never translates text.
2. Select **Clean**. Inspect its ordered transforms, then open **Duplicate policy**. Exact raw, exact cleaned, normalized sections and optional near-duplicate SimHash are separate checks. **Pinned canonical locations** choose a retained source identity only when intentionally saved in a new version; inspect the retained counterpart in preview/run results.
3. Open **Sensitive-data policy** and confirm **Redact sensitive values before chunking and embedding** for the fictional email example. Set the `email` action to **Redact value** or **Drop entire document**. Select **Preview processing → Inspect stages**. Compare **Extracted**, **Cleaned**, and **Changes**. The cleaned passage should contain `[EMAIL]`, not the synthetic address, when the rule applies.
4. Save a new version before execution; the earlier version keeps its prior policy. After a run, inspect **Cleaned** and **Chunks** in [run details](./runs.md) and the downstream evidence before considering the result safe.

Expected result: transform audit and safe finding locations explain what changed; redacted values never reach embeddings or answer evidence for this version. Exact/near-duplicate and language decisions can exclude an item without deleting its source revision. A `drop_document` decision removes that item from publication.

If a finding is surprising, inspect a synthetic positive and negative example, adjust the relevant saved rule and preview again. Do not weaken a rule merely to force a ready index. If Raw/Changes are denied or expired, use a permitted owner/admin or an authorized new source revision; do not substitute an older snapshot silently. Continue with [quality decisions](./quality.md), [chunking](./chunking.md), and [security boundaries](../reference/limitations.md). This page describes deterministic rules in the current app, not a guarantee of complete PII detection.
