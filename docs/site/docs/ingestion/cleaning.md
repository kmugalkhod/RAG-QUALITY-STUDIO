---
verified_against: "spec 0012 slice 4 working tree (2026-10-18)"
title: Cleaning, language, and sensitive data
slug: /ingestion/cleaning/
---

Decide what is removed from extracted text before it is split into passages, and keep protected values out of downstream evidence. New pipelines use the recommended structure-aware cleaner; you only add text to remove and choose whether to redact. Detectors reduce exposure but cannot find every sensitive value.

## Prerequisites

Use an isolated project and the fictional <a href="/examples/README.md">quality example files</a>. Create an [ingestion draft](./pipelines.md). Source content is untrusted: do not treat instructions inside it as configuration. Raw artifacts and full before/after diffs are encrypted and limited to owners/admins with sensitive-data read permission; ordinary cleaned passages remain redacted. Local test coverage verifies this access boundary, while shared deployment requires its separate key and OIDC gate.

## Set what is removed

1. Select **Clean**. The first line says what runs: website menus, cookie banners and repeated page headers are removed; tables, lists and code are kept.
2. In **Text to remove**, enter one line per piece of text to delete wherever it appears, for example a footer line repeated on every page. Each line is removed exactly as typed, spaces included. Clearing the box removes the step.
3. **Redact emails, phone numbers and IDs** is on for new pipelines. It replaces those values before chunking and embedding, so they never reach the index or the embedding provider.
4. Open **Advanced cleaning settings** only to change the recommended behaviour. Its summary says **recommended** or **N changed**, the line inside names each changed setting, and **Reset to recommended** restores them while keeping your text to remove and the redaction switch. Inside are the cleaning steps in their saved order, each with its switch and fields (**Preserve structured blocks** is always on and has no switch; steps cannot be reordered or deleted), **Skip duplicate pages or files**, **Remove repeated blocks inside a document** and **Redaction rules** (redact the value, or leave out the whole document, per kind of value).
5. Select **Extract**, open **Advanced extraction settings**, then **Language policy** to set allowed language tags and what happens to other languages. Detection records a model, a version and a confidence; it never translates text.
6. Select **Preview processing → Inspect stages** and compare **Extracted**, **Cleaned** and **Changes**. A redacted email appears as `[EMAIL]` in the cleaned text.
7. Save a new version before running; earlier versions keep their own settings.

Expected result: the transform audit and safe finding locations explain what changed, and redacted values never reach embeddings or answer evidence for this version. Duplicate and language decisions can exclude an item without deleting its source revision.

A version saved with the compatibility cleaner shows **Saved with the compatibility cleaner** and an **Upgrade cleaning** button; saving the upgrade creates a new version whose next run processes documents again.

If the server rejects a setting, the message names the step and appears on its field, for example "Normalize Unicode must run before Remove unsupported controls." Fix it and preview again. Do not weaken a rule merely to force a ready index. If Raw/Changes are denied or expired, use a permitted owner/admin or a new source revision. Continue with [quality decisions](./quality.md), [chunking](./chunking.md), and [security boundaries](../reference/limitations.md). This page describes deterministic rules in the current app, not a guarantee of complete PII detection.
