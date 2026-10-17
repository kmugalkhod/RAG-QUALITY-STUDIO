---
verified_against: "spec 0012 slice 4 working tree (2026-10-18)"
title: Embedding
slug: /ingestion/embedding/
---

Turn every passage into a vector that search can compare with a question. The server sets the embedding provider, model and dimensions; the Embed stage shows them and what a run costs.

## Prerequisites

The server needs a configured embedding provider. Embedding is the only stage of a run that may be billed: previews never embed, and a vector an earlier run already made for the same text and model is reused at no cost.

## Read the Embed stage

1. Select **Embed**. The first line names the model and its dimensions, for example "Uses openai/text-embedding-3-small (1536 dimensions), set by the server."
2. After a preview, the stage says about how many passages a run would embed, about how many kilobytes of text that is, and an estimated cost marked **list price, estimate**. The estimate assumes about four bytes per token at the provider's list price and that no vector can be reused; the run records the provider-reported cost.
3. After a run, it says how many passages were embedded new and how many vectors were reused, with the provider-reported cost, or **unknown** when the provider did not report it. Failed and cancelled runs report what they paid for too.

If the server's model changed since a version was saved, the stage shows **Saved with a different embedding model** with **Use the server's embedding settings**. Saving that creates a new version; its next run embeds every passage again. If the server has no embedding configuration, saved pipelines open read-only and cannot be saved, previewed or run.

While a run embeds, its status line says why it waits, for example "Waiting for embedding request budget, resumes in 20 s" or "Retrying after a provider error (2 of 3)". If the provider keeps refusing requests for 15 minutes, the run stops with "The embedding provider kept refusing requests (rate limit)" and nothing new is published.

Continue with [publishing](./publishing.md) and [runs](./runs.md).
