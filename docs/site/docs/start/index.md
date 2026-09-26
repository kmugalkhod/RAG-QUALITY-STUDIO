---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: Choose your path
slug: /start/
---

Choose a path that ends in an artifact you can inspect. This guide covers the current local application at commit `481b4eca90c5` plus the documentation copy and OpenAPI fix on this branch (reviewed 2026-09-26).

## Before you begin

You need Docker Compose and Node.js 22.12+ for the local app. [Install locally](./install.md) first. Upload and processing need no model credentials; publishing an index and generating an answer need a configured provider and can incur charges. No hosted shared deployment or external connector account is verified by this guide.

| Your goal | Follow | Inspect at the end |
| --- | --- | --- |
| Ask one grounded question | [First workflow](./first-workflow.md) | A ready collection version, saved answer version and cited passage |
| Control extraction and chunking | [Existing Files ingestion](../ingestion/pipelines.md) | Preview, immutable ingestion version, run items and ready index |
| Use HTTP endpoints | [API overview](../api/overview.md) | Health, readiness and a validated OpenAPI contract |
| Understand what changes between runs | [Versions and provenance](../concepts/versions.md) | IDs and immutable snapshots attached to a run |

![Accessible diagram of the source-to-answer path](/img/workflow.svg)

If a link opens an unavailable model action, inspect [provider configuration](./configure.md), then retry with a new run after resolving the missing setting. Continue with [how the workflow fits together](../concepts/workflow.md). The examples use synthetic local content; remote source and paid model acceptance remain conditional.
