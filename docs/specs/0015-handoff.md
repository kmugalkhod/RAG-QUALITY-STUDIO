# Spec 0015 handoff: how to build it in a new session

Spec: [`0015-better-search-and-editor.md`](0015-better-search-and-editor.md).

**Approval:** approved 2026-10-18. The owner decided D1 (the reranker is an optional **Rerank node** in the answer graph) and approved D2-D8 as recommended.

**Start with Slice 0.** It is paid, about $0.30.

## Owner rules (apply to every slice)

- Commit each finished slice on local `main`. **Do not push until the owner asks.**
- **Saved pipelines must keep running exactly as saved:**
  - answer graph schemas 1 and 2;
  - `layout-ocr-v1`…`v6`;
  - `section-token-v1`…`v4` and `parent-child-v1`…`v4`.
- **Paid work only in Slice 0 (about $0.30) and Slice 6 (about $0.40). This spec's cap is $1.** The real-source harness cap (`COST_CAP_USD` in `backend/scripts/real_source/run.py`) is $2.50; it had spent $0.79 before this spec.
- **Never run `docker compose down -v` on the dev project.**
- **Leave the owner's unrelated local changes alone:** `docs/site/static/examples/*`, `docs/diagrams/ingestion-architecture.html`, `social/`.
- **No weak LLM judge for scoring answers:** score blind by hand with the spec 0004 rubric (`backend/scripts/clean_chunk/blind_rounds.py`, with `BLIND_SEED=search-editor-0015`), write every label before opening the key, and write a 10-label `spot_check.md` for the owner. The Rerank model only orders passages, so the rule does not apply to it.
- **Stop and ask only if a slice needs a decision the spec does not cover.** If Slice 0 meets no target without a loss, stop and report (spec stop rule).

## Environment notes for this machine

- **Low memory:** prefer one-off commands over the full stack, and do not run a Playwright browser while ingestion rounds are running. Claude Code may kill a long background command when memory is short. The harness saves its state, so rerunning it resumes and does not pay twice.
- **The backend image bakes in the code.** After changing backend code, run `docker compose up --build -d migrate backend worker long-worker dispatcher deployed-worker` before any live run. For quick checks without a rebuild, copy the tree into the container:

  ```sh
  docker compose cp backend/app backend:/tmp/dev/app
  MSYS_NO_PATHCONV=1 docker compose exec -T backend sh -c 'cd /tmp/dev && PYTHONPATH=/tmp/dev python …'
  ```
- **Git Bash on Windows:** prefix `docker compose exec` commands that pass Unix paths with `MSYS_NO_PATHCONV=1`. Long Python edits go in a file written with the Write tool, not a heredoc.
- **Scripts that call the API** must run inside the backend container against `http://127.0.0.1:8000`, because local auth trusts only loopback. Scripts that embed or chat directly must bind the project key: `with Session(engine) as s, provider_credentials.bound_for_project(s, project_id): …` (see `backend/scripts/table_rows/slice0.py`).
- **Real-source harness:**
  - Its state is `docs/qa/real-source-2026-10/raw/state.json`. Copy it to `/tmp/rs/state.json` in the container first; a container restart clears `/tmp`.
  - Stages: `python /app/scripts/real_source/run.py round|measure|retrieve|ask|fetch /tmp/rs <ROUND> --allow-paid`, run from `/app/scripts/real_source`.
  - Copy `state.json`, `structure.json` and `answers_<ROUND>.jsonl` back to `docs/qa/real-source-2026-10/raw/` afterwards.
  - The project is "Real-source test 2026-10", `c7a9c56e-bf47-429c-a934-8299c06b9005`.
  - Index IDs per round are in `state["runs"]["<track>:<round>"]["index_id"]`. The tracks are `web`, `files`, `new` and `d2`. The baselines are A5 (current defaults) and A6p (best so far).
- **Live website checks** need public DNS (1.1.1.1, 8.8.8.8): the network's DNS64 is blocked by the SSRF guard.
- **Frontend:**
  - Vite runs at `http://127.0.0.1:5273` (reuse it; never switch ports).
  - Open ingestion pipelines with `#/projects/<id>/pipelines/<pipeline_id>?kind=ingestion`; without `?kind` the page is blank, which is bug U3 of this spec.
  - The stage selector options read "2 · Extract", "4 · Chunk" and so on.
  - Run Vitest with `--maxWorkers=1`. Prettier's full check flags many files because of CRLF; check only changed files.
- **Backend checks:**
  - `ruff check` / `ruff format --check` in the container.
  - The full suite: `docker compose -p rag-studio-tests -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests`, then `down` with the same project.
  - Two failures predate this work: the `test_connections` tamper test and the Redis/Celery deployment test.
- **The API reference generator** (`docs/site/scripts/generate_api_reference.py`) fails on the committed code (`/answer-deployments` is unclassified). Edit `docs/site/docs/api/schema-models.md` by hand for schema changes, or fix the generator as a separate, reported change.

## Where to start in the code

- **Answer graph:**
  - schema and validation: `backend/app/schemas/pipeline.py` (`Execution.supported_graph`, `ORDER`, `Layout` max 5);
  - execution: `backend/app/pipelines/langchain_rag.py` (compiled graph used by Playground, experiments, deployments and widget);
  - retrieval: `backend/app/schemas/retrieval.py` and the retrieval services;
  - model calls: `backend/app/providers/generation.py` (chat), `backend/app/providers/chat_models.py` (approved models).
- **Answer editor:**
  - `frontend/src/features/pipelines/` (`components/WorkflowNode.tsx` icon map, `summarizeNodeConfig`, `NodeSettings.tsx`, `model.ts`);
  - it must stay separate from the ingestion editor in `frontend/src/features/ingestion-pipelines/`.
- **Chunking v5:**
  - `backend/app/ingestion_content/chunking.py` (`ROW_PASSAGE_VERSIONS`, `_row_passages`, `_section_groups`, `_with_row_pieces`);
  - `backend/app/ingestion_content/tables.py`;
  - `backend/app/schemas/ingestion.py` (chunk `config_version` literals);
  - `backend/app/ingestion_content/processing.py` (`V3_CHUNKER_VERSIONS`);
  - the frontend `editorModel.ts` (`chunkVersionChanges`).
- **Editor findings:**
  - U1 pipeline list: `frontend/src/features/ingestion-pipelines/` and the pipelines list API;
  - U2 phone header: `IngestionPipelineEditor.tsx` and `IngestionToolbar.tsx`;
  - U3 routing: `frontend/src/app/navigation.ts` and `WorkspacePage.tsx`;
  - U4 **Searched as**: `backend/app/workers/previews.py` (the prefix is computed only when `embedding_text` ends with the text) and `IngestionResults.tsx`;
  - U5 wording.
- **Earlier measurement scripts to reuse:**
  - `backend/scripts/keyword_search/slice0.py` (BM25 over an index);
  - `backend/scripts/table_rows/slice0.py` (reprocess documents, embed, rank vector, BM25 and hybrid, with the project key bound).

## Slice 0 in short

For the A5 and A6p indexes and the 77 answerable questions (`backend/scripts/real_source/questions.jsonl`, the ones with `phrases`):
1. Take the vector top 30, and the union with BM25 top 30.
2. Rerank each set with two models: a cheap one and `google/gemini-2.5-flash`.
3. Record, per question and setting: top-5 hit, rank-1 hit, losses against the unreranked baseline, cost and latency.
4. Write the results to `docs/qa/search-and-editor-2026-10/`.

**Target:** at least 74 of 77 in the top 5, rank 1 up by at least 10, no question lost, and per question at most $0.002 and 1.5 s added.

**Pick the cheapest setting that meets the target.** Build keyword candidates (S2) only if vector-only candidates miss it.
