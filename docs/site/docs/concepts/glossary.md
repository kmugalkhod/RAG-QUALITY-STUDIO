---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: Glossary
slug: /concepts/glossary/
---

Use one name for each stored artifact when reading the UI and API. Terms were checked against the current local app at commit `481b4eca90c5` plus documentation changes, 2026-09-26.

## Prerequisite and example

Complete the [first local workflow](../start/first-workflow.md), then open **Knowledge Base → Collections → Uploaded documents**. Identify the document, prepared content and index version in **Sources**, **Versions** and **Passages**. Open a saved answer run in **Playground → Past questions** and identify its evidence. The example uses fictional `harbor-desk.txt`; provider-backed steps require configuration and may incur charges.

| Term | What it means | Where to inspect |
| --- | --- | --- |
| Project | Scope for documents, indexes, pipelines, datasets and runs | Project switcher and **Settings** |
| Document | Uploaded file record with source metadata | **Knowledge Base → Documents** |
| Processing version | One parser/chunker run and its resulting passages | Document **Processing history** |
| Chunk or passage | Bounded text unit stored for retrieval | **Inspect chunks** or collection **Passages** |
| Collection | Named search corpus; API calls it a `knowledge_set` | **Knowledge Base → Collections** |
| Index version | Immutable searchable membership and embedding configuration | Collection **Versions** |
| Pipeline version | Saved answer or ingestion configuration | **Pipelines** and **Saved version** |
| Run | One execution of a saved or explicit draft configuration | **Playground → Past questions** or ingestion run detail |
| Evidence | Retrieved passage actually supplied to the answer model | **Sources & details** |
| Source snapshot | Immutable selection of external source revisions, separate from an index | **Collections → Source history**, after a remote run |
| Dataset and metric | Versioned evaluation questions and scoring rule | **Experiments**, with evaluator configuration |

Expected result: you can name the exact index and pipeline versions behind one answer. A source snapshot does not itself answer questions; it can feed a later index. If a version is missing, refresh its history and inspect deletion/permission state instead of substituting the current version. See [how the workflow works](./workflow.md), [versions](./versions.md), and [API patterns](../api/patterns.md). Remote snapshots and model-judged metrics need their separate configured or live gates; the local sample does not validate them.
