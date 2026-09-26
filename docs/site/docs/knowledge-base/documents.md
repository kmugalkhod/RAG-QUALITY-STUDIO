---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: Upload and manage documents
slug: /knowledge-base/documents/
---

Upload a local file and inspect its document record. Current UI and server extension list reviewed at commit `481b4eca90c5` plus copy updates, 2026-09-26.

## Prerequisites

Create a project in the [local app](../start/install.md). Download <a href="/examples/harbor-desk.txt" download>harbor-desk.txt</a> for an entirely synthetic test. The server accepts PDF, TXT, Markdown, HTML, DOCX, PPTX, CSV, TSV and XLSX extensions; extraction capability differs by format and server installation. **Settings → Documents** shows the configured per-file byte limit (20 MiB by default). Upload itself does not call a model.

## Upload and inspect

1. Open **Knowledge Base → Documents**, select **Add document**, and choose the file in **Document file**.
2. Select **Upload document**. Select the new row to open **Process: harbor-desk.txt**; expand **Source metadata** to inspect document ID and SHA-256.
3. Upload the same sample a second time only if you want to test duplicate handling. The API creates another document record, while the UI groups identical content for inspection; do not assume the first upload was overwritten.

Expected result: the document row appears with processing controls. A zero-byte, unsupported, or oversized file receives validation feedback; pick a valid file and retry. After a network interruption, refresh the list first to avoid an accidental duplicate. Deletion is subject to historical dependencies; inspect the confirmation/error before removing a file. Continue with [preparing content](./prepare.md) and [collections](./collections.md). Scanned PDFs need an OCR path and may fail extraction when unavailable; this sample avoids that gate.
