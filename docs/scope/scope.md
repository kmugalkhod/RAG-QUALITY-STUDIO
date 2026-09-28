# Scope: RAG Quality Studio

RAG Quality Studio helps RAG engineers and operators build versioned knowledge, inspect cited answers, and compare measured quality. The next work improves the quality decision in the private local workspace. It uses a small English question set, bounded live calls, and no billing or third party tracking.

**Build approach:** Tracer Bullet (complete one real path through the interface, API, persistence, and verification before widening it).
**Workflow:** Beta (verify each new feature in the real app, then add focused tests). A feature with an unmade decision starts with `/architect`.

These are recommendations. You can change the order or skip a step that no longer fits.

## At a glance

| # | Feature | Phase | Status |
|---|---|---|---|
| 1 | Projects and access | Existing foundation | existing |
| 2 | Sources and ingestion | Existing workflow | existing |
| 3 | Knowledge versions and retrieval | Existing workflow | existing |
| 4 | Answer pipelines and evidence | Existing workflow | existing |
| 5 | Datasets and experiments | Existing workflow | existing |
| 6 | Deployed answer API | Existing local delivery | existing |
| 7 | Documentation and operations | Existing local delivery | existing |
| 8 | Private website widget | Existing local delivery | existing |
| 9 | Reviewed quality dataset | Cancelled | dropped |
| 10 | Human answer and evidence review | Quality slice 2 | planned |
| 11 | Quality comparison decision | Quality slice 3 | planned |
| 12 | Held out confirmation | Quality slice 4 | planned |
| 13 | Public visitor website widget | Existing local delivery | existing |

## Existing foundation

### 1. Projects and access · existing

Project creation, organization membership, and project roles give each workspace a durable ownership boundary. The current Clerk mode is for local development.

**Done when:** a permitted member can work in the right project and another project or organization cannot expose its data. Code in `backend/app/core/auth.py`, `backend/app/services/projects.py`, and `frontend/src/features/projects/`.

## Existing workflow

### 2. Sources and ingestion · existing

Documents and configured sources flow through preview, processing, provenance, and durable ingestion jobs.

**Done when:** a selected source can publish a complete new index without exposing a partial index or erasing the previous ready version. Code in `backend/app/connectors/`, `backend/app/ingestion_content/`, `backend/app/workers/ingestion.py`, and `frontend/src/features/ingestion-pipelines/`.

### 3. Knowledge versions and retrieval · existing

Immutable index versions support dense, keyword, and hybrid retrieval with inspectable evidence and source lineage.

**Done when:** a project can inspect a ready index and retrieve only its own indexed passages using saved settings. Code in `backend/app/services/indexes.py`, `backend/app/pipelines/retrieval.py`, and `frontend/src/features/documents/`.

### 4. Answer pipelines and evidence · existing

Saved answer graphs and the Playground run grounded questions against selected ready indexes.

**Done when:** a question returns a cited answer or an explicit insufficient evidence result, with the supplied passages available to inspect. Code in `backend/app/services/pipelines.py`, `backend/app/services/queries.py`, `frontend/src/features/pipelines/`, and `frontend/src/features/playground/`.

### 5. Datasets and experiments · existing

Immutable CSV question sets, durable evaluation jobs, and paired reports already compare saved answer versions.

**Done when:** a member can inspect each question, answer, evidence, metric state, failure, latency, and known cost behind a comparison. Code in `backend/app/services/datasets.py`, `backend/app/services/experiments.py`, `backend/app/evaluation/`, and `frontend/src/features/experiments/`.

## Existing local delivery

### 6. Deployed answer API · existing

The local server API pins an answer release and index, applies admission limits, and saves durable customer question runs.

**Done when:** an authorized server key can submit and inspect a bounded run, while browser traffic cannot use that key route. Code in `backend/app/api/deployed_answers.py`, `backend/app/services/deployed_runs.py`, and `backend/app/workers/deployed_answers.py`.

### 7. Documentation and operations · existing

The local guide site and operator notes cover current workflows, recovery, and the boundary for shared release.

**Done when:** a local user can follow the guide and an operator can find the backup, restore, and job procedures. Code and content in `docs/site/`, `docs/development.md`, and `docs/operations.md`.

### 8. Private website widget · existing

The separate loader and iframe let an authenticated visitor ask one deployed answer pipeline through a customer backend. This is complete for local private checks in the current working tree; public hosting remains deferred.

**Done when:** a local customer fixture can obtain a visitor token, submit a question, and inspect a cited result, while a copied embed alone cannot ask. Code in `widget/`, `backend/app/api/widget.py`, and `frontend/src/features/deployments/WidgetSettings.tsx`.

### 13. Public visitor website widget · existing local delivery

An owner can opt in to public questions for an active deployment and exact site origin. A static site needs one script; Studio issues short-lived visitor tokens and applies the saved admission and spend limits. The local static page submitted a real question and displayed cited evidence. Internet hosting remains deferred.

## Cancelled work

### 9. Reviewed quality dataset · dropped

Cancelled at your request on 2026-09-29. The added review and approval workflow, implementation and spec were removed. Existing CSV imports and RAGAS experiments remain the product workflow.

## Quality slice 2

### 10. Human answer and evidence review · planned · needs a decision

Let a reviewer judge a bounded sample of actual answers, retrieved passages, and abstentions. Record the judgment beside the exact run so model scores can be checked against human evidence.

**Done when:** a reviewer can mark answer support, evidence usefulness, and abstention fit, with the reviewer and run identity retained and disagreements visible.

- [ ] Design it (spec): `/architect human answer and evidence review`

## Quality slice 3

### 11. Quality comparison decision · planned · needs a decision

Help an operator compare a baseline and one changed configuration on the same reviewed questions and compatible source versions. Put quality first within stated latency and cost limits, and show failures and unknown cost alongside successful scores.

**Done when:** the report shows paired sample counts, human judgments, model metric limits, latency, cost basis, and a measured reason to keep or reject the candidate. It does not claim proof of a root cause.

- [ ] Design it (spec): `/architect quality comparison decision`

## Quality slice 4

### 12. Held out confirmation · planned · needs a decision

Reserve questions that were not used to tune the candidate, then confirm the chosen change against them with bounded live calls. Keep the comparison and the final decision inspectable.

**Done when:** one real source flows through a cited answer and a measured baseline comparison, a separate held out set checks the chosen candidate, and the saved result states sample size, failures, latency, known and unknown cost, and limits. Changed flows meet WCAG 2.2 AA checks.

- [ ] Design it (spec): `/architect held out confirmation`

## Deferred

Public internet widget and API rollout, billing, product usage tracking, and UI translation are deferred. New retrieval methods or automatic configuration recommendations should follow measured evidence from the reviewed comparisons.

## Legend

`existing` means the local capability predates this scope. `planned` means its first unchecked command is the next design step. `/develop` builds a designed feature through its real layers. With the Beta workflow, `/check verify` and `/test` follow development. A later pass of `/scope` can reconcile shipped work and reorder the remaining slices.
