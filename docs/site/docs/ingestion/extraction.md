---
verified_against: "481b4eca90c5 + docs phase 2 working tree (2026-09-26)"
title: Extraction and OCR
slug: /ingestion/extraction/
---

Choose how each page becomes readable blocks, then inspect its actual page origin before indexing. Schema-v2 extraction and local OCR are implemented; installed language packs and a source's scan quality are configuration and input gates, not guaranteed outcomes.

## Prerequisites

Upload a fictional TXT or text-based PDF as in [document preparation](../knowledge-base/prepare.md), or use a reviewed two-page synthetic PDF for a page-origin check. Create an [ingestion draft](./pipelines.md) and select **Extract** in the stage navigation. `GET /api/projects/{project_id}/ingestion-capabilities` reports the installed OCR languages and bounds for your local server; substitute the ID of an isolated project. A loopback owner request needs no token in local mode:

```sh
curl --fail http://127.0.0.1:8000/api/projects/<PROJECT_ID>/ingestion-capabilities
```

Expected response shape includes `ocr.available`, `ocr.languages`, and extraction/quality profiles. Replace `<PROJECT_ID>` with the created project's ID. If the endpoint returns 404/403, check project selection or access before editing a pipeline.

## Set and inspect

1. In **Stage settings**, use **Extraction strategy**: **Auto · page-level fallback**, **Native text**, or **Layout-aware**. Older saved versions may show **Enable robust extraction** first; upgrading creates an unsaved draft.
2. Set **OCR policy** to **Off**, **Automatic fallback**, or **Always** only when the server reports OCR available. Select installed **OCR languages**, and bound **OCR resolution (DPI)**, **Maximum OCR pages**, and **Per-page timeout (seconds)**. Optional **Detect page rotation** and **Deskew scans** are bounded local corrections.
3. Select **Table evidence**: **Structured + Markdown**, **Markdown**, or **Plain text**. Select **Preview processing**, then **Inspect stages** for the item. Compare **Extracted** with **Raw** and inspect page origin, fallback reason, rotation, confidence, block overlay and table count where that file provides them.

Expected result: page metadata identifies native/layout/OCR origin when available, and the preview shows extracted blocks before cleaning. An image-only PDF with OCR off may have no usable text or a quality failure. OCR is not an assurance that every scan or table will be read correctly.

If OCR options are disabled, install/configure the required language packs on the server and reread capabilities. For a failed page, inspect the safe finding and the original authorized artifact; correct scan orientation/quality or adjust a bounded policy for a reason, then preview again. A changed extraction policy needs **Save version** before a run. See [quality findings](./quality.md), [cleaning](./cleaning.md), and [previews](./previews.md). Local deterministic PDF/OCR tests cover bounded cases; external OCR services and arbitrary document quality have not been verified.
