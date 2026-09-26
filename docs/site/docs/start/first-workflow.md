---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: First RAG workflow
slug: /start/first-workflow/
---

Create one synthetic document, publish its exact collection version, and inspect evidence supplied to an answer. UI labels below were checked against the current app at commit `481b4eca90c5` plus documentation copy changes, 2026-09-26. Publishing and answering require a configured provider; they may incur charges. The deterministic journey is covered by isolated browser tests, not a live account claim.

## Prerequisites

Complete [local installation](./install.md) and [provider configuration](./configure.md). Download <a href="/examples/harbor-desk.txt" download>harbor-desk.txt</a>, a fictional TXT file; do not upload private or credential-bearing material for this tutorial. Use a new project to keep its versions easy to identify.

![Five stages: document, preparation, collection, saved answer version, cited evidence](/img/workflow.svg)

## 1. Create a project and upload

1. Open [the app](http://127.0.0.1:5273), select **New project**, enter `Harbor docs`, and select **Create project**. Open the new project.
2. In **Knowledge Base → Documents**, select **Add document**. The file input is labeled **Document file**. Choose `harbor-desk.txt` and select **Upload document**.
3. Select its document row if the **Process: harbor-desk.txt** inspector is not already open. Confirm the filename and source metadata are synthetic.

The upload creates a document, not a searchable index. If the file is rejected, check the upload limit in **Settings**, choose a supported nonempty file, and retry. Repeated successful uploads create separate document records; refresh the list after an interrupted request before retrying.

![Synthetic Harbor Desk file selected in the Knowledge Base upload form](/img/screenshots/01-upload.png)

## 2. Prepare content

Select **Start processing** in the document inspector. Wait until the processing history shows success, then select **Inspect 1 chunks** (the count can differ if settings change). Read the passage and its character offsets. The simple document path uses character windows; the ingestion editor also offers section-token and parent-child modes.

If parsing fails, use **Refresh history** to confirm the terminal state, correct the input or settings, then start a new processing version. A failed or cancelled version does not become prepared content. See [prepare uploaded content](../knowledge-base/prepare.md).

![Processing history for the synthetic Harbor Desk document](/img/screenshots/02-prepared.png)

## 3. Publish a collection

Open **Collections** in **Knowledge Base** and select **Publish prepared documents**. Wait for the **Uploaded documents** collection to appear with a **Ready** version. Open it and inspect **Sources**, **Versions**, and **Passages**. Record the displayed version number and verify this file is a member. Use **Test retrieval** with `When is Harbor Desk open?` to inspect a passage before generating an answer.

Publishing embeds the prepared passage and can be billed. If the button is disabled, use [provider configuration](./configure.md). If a version fails or remains pending, refresh the collection and inspect its status before starting another publication. An old **Ready** version remains the one to use until a new version succeeds. See [collections and index versions](../knowledge-base/collections.md).

![Ready Uploaded documents collection with a fixed version and one prepared source](/img/screenshots/03-collection.png)

## 4. Save an answer version

From the selected ready collection, select **Use version 1 in a pipeline** (use the actual displayed number). In the answer editor, check **Documents to search** names the exact collection version. Give the pipeline a name, select **Save version**, and then **Open Playground**. The saved version and collection membership remain fixed for this run; changing the draft later requires another save to persist it.

If validation blocks saving, open the selected node's labeled settings, resolve the shown field error, and save again. The five supported answer nodes are Question → Retriever → Prompt → LLM → Answer; arbitrary branches are rejected. See [answer pipelines](../answers/pipelines.md).

## 5. Ask and inspect evidence

In **Playground**, choose **Pipeline test** and confirm the saved version in the toolbar. Enter `When is Harbor Desk open?` under **Question** and select **Run pipeline test**. The answer should refer to Monday through Friday, 09:00–17:00 if the model follows the supplied passage. Select its citation or **Sources & details** to inspect the exact supplied passage and source label. A model can vary its wording; check the evidence rather than assuming the answer is correct.

Try `Does Harbor Desk deliver on weekends?` as an insufficient-evidence check. The source does not answer it. The app supports an **Insufficient evidence** result, but model behavior is not guaranteed for every live provider response. If a run fails, inspect **Past questions** and the error before retrying; an in-flight model call may have incurred cost. Continue with [reading answers and evidence](../answers/evidence.md) or [an ingestion pipeline](../ingestion/pipelines.md).

![Synthetic answer citing the supplied Harbor Desk passage in Sources and details](/img/screenshots/04-evidence.png)

The <a href="/img/screenshots/05-evidence-mobile.png">mobile evidence view</a> shows the same source inspector at 390px. These screenshots were captured on the isolated PostgreSQL/pgvector stack with deterministic test transport; they do not represent live-provider output.
