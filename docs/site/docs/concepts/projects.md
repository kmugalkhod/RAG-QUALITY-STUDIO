---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: Projects and workspace
slug: /concepts/projects/
---

Create a project, find its main sections and confirm that project selection scopes its content. UI labels match the current local app at commit `481b4eca90c5` plus documentation changes, 2026-09-26.

## Prerequisite

Start the [local app](../start/install.md). Default local mode has one loopback owner; a shared OIDC deployment has separate identity and project-role gates that this local exercise does not validate. Creating projects and switching sections make no provider calls.

## Create and navigate

1. On **Projects**, select **New project**, enter `Harbor docs` under **Project name**, then select **Create project**. Select the new project from the list.
2. Open **Overview** to see real source, preparation, publication and pipeline state. Use **Knowledge Base** for **Documents** and **Collections**; **Pipelines** for **Answer pipelines** and **Ingestion pipelines**; **Playground** for retrieval and answer tests; **Experiments** for datasets and comparisons; **Settings** for safe server status.
3. Create another synthetic project and use **Switch project** in the sidebar. Its Documents and Collections should not show the first project's file. Return to `Harbor docs` using the same switcher.

![New project form filled with a fictional Harbor docs name](/img/screenshots/00-project.png)

Expected result: the two projects have separate lists and IDs, and each project's current route can be revisited. If a project fails to load, use **Try loading again** or **View all projects**; a missing project link may have been deleted or be inaccessible in the current identity. Do not copy a project ID into a docs URL. Continue with [the first workflow](../start/first-workflow.md), [Knowledge Base](../knowledge-base/index.md), and [API authentication](../api/overview.md). Local isolation tests do not establish a shared deployment release gate.
