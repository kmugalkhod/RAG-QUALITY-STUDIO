---
verified_against: "481b4eca90c5 + docs phase 4 working tree (2026-09-26)"
title: Limits and FAQ
slug: /reference/limits-faq/
---

Check the current capability boundary before committing source, model or operator cost. Use a local project with the app running; [create one](../start/first-workflow.md) if needed. The configured server is authoritative for installed OCR languages, file limit and provider availability. This table was reviewed against the current schema and local tests, not against every external account or model.

| Area | Current behavior and bound | Gate or limitation |
| --- | --- | --- |
| Uploads | PDF, TXT, Markdown, HTML, DOCX, PPTX, CSV, TSV and XLSX; default 20 MiB per file, configurable up to 100 MiB. | UTF-8 text; unsafe/macro-enabled Office and malformed/encrypted PDFs fail. Scanned PDFs need a schema-v2 OCR policy and installed languages. |
| Sources | Existing Files, bounded public Website, Amazon S3, Notion and Confluence. | Credentialed sources need the local encrypted vault and a scoped account. Website blocks non-public destinations and redirects. Live accounts/hosts are not verified here. |
| Ingestion graph | Validated linear Source → Extract → Clean → Chunk → Embed → Publish with immutable saved versions. | No arbitrary branch, executable code node or infrastructure provisioning. Preview is not publication. |
| Answer graph and retrieval | Supported five-node answer template; Vector, Keyword and Hybrid retrieval. `top_k` 1–50; hybrid branch candidates up to 200. | No reranker in the current editor. Vector distance and fusion score are ranking signals, not confidence or factual accuracy. Query embeddings may bill. |
| OCR and chunking | Capability endpoint reports installed Tesseract languages and extraction profiles; OCR policy max 100 pages and 150–300 DPI. Character, section-token and parent-child chunking are versioned. | OCR/table accuracy varies; token estimates use the app's stable UTF-8 byte tokenizer. Review extracted and supplied evidence. |
| Datasets and experiments | Default 200 CSV rows and 2 MiB, configurable up to 1,000 rows/10 MiB; one or two saved answer versions per run. Faithfulness, response relevancy and context recall have explicit input requirements. | Missing references, failed/skipped items and unknown prices remain visible. RAGAS model judgments vary; no automatic certification or root-cause proof. |
| Schedules and retention | Ingestion schedule interval at least 15 minutes. New encrypted raw artifacts retain for 30 days by default, configurable 1–3,650 days; historical redacted evidence remains. | Deleting or expiring raw bytes can prevent exact reprocessing. Back up database, artifact volume and referenced keys together. |
| Access | Local mode is one loopback owner. OIDC mode supports project owner/admin/editor/viewer and protected-read audit with external artifact wrapping. | Shared ingress, real identity lifecycle and KMS/Vault service require separate acceptance; source-connection routes remain loopback guarded. |

To inspect the actual server's extraction/media/OCR options without a model call, run from the repository root after setting `PROJECT_ID` to a project you may access:

```sh
curl --fail "http://127.0.0.1:8000/api/projects/$PROJECT_ID/ingestion-capabilities"
```

Expected result: JSON with `media_types`, `profiles`, `ocr.available`, `ocr.languages`, table modes, quality/cleaning/tokenizer/chunking profiles. A 404 means the project ID is absent or not accessible; a 503 readiness failure needs the [operations checks](../operate/operations.md). **Settings → Models** shows configured embedding/answer availability, and **Settings → Documents** shows the current upload limit. Do not infer a live provider success from either configuration view.

**Can a citation prove the answer?** It proves only that the labeled passage was supplied to generation; inspect the text and provenance. **Can a failed preview or index be queried?** No: only a ready published index is queryable. **Are model calls free in the local tutorial?** No: deterministic provider doubles are test-only; configured embedding, answer and evaluation providers may bill even when a later step fails. **Does cancellation stop an in-flight request?** It stops further scheduling, but a request already sent may finish and incur cost. **Can the docs site's test-provider override be used for deployment?** No; it lives only in isolated verification and does not represent a real account.

If a selected option is missing, check the capability endpoint and [provider configuration](../start/configure.md), then adjust a new version rather than rewriting an old one. For feature-specific guidance, see [current capability boundaries](./limitations.md), [source choice](../ingestion/sources/index.md), [retrieval settings](../answers/retrieval.md), [metrics](../experiments/metrics.md), and [security](../operate/security.md). Arbitrary branching, reranking, external OCR services and unverified shared deployment are future or separate work, not instructions on this page.
