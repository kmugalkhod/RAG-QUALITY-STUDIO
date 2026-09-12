# RAG Quality Studio

Milestone 5 adds immutable evaluation datasets and background RAGAS experiments to the existing React Flow pipeline editor, Knowledge Base and RAG playground. Upload/process/index PDF or UTF-8 TXT documents, ask questions using OpenRouter, then inspect answers, citation references and the exact evidence sent. React/TypeScript, FastAPI, PostgreSQL/pgvector, Celery and Redis retain persistent state. Configure retrieval, prompts and server-approved chat models, execute saved pipelines and inspect persisted results. Compare saved pipeline versions using reviewed questions, inspect per-question evidence and export results.

## Start with Docker Compose

Prerequisites: Docker Engine/Desktop running with Docker Compose v2 (2.24.4+ for the isolated browser configuration); ports 5173, 8000 and 5432 available.

From the repository root:

```sh
cp .env.example .env
# Optionally edit .env: choose a URL-safe local database password before first startup.
docker compose up --build -d
```

Compose waits for PostgreSQL, applies Alembic migrations through a one-shot service, starts FastAPI, Celery workers, Redis and the queue dispatcher, then serves the production frontend through nginx. The frontend proxies `/api` to FastAPI. No credentials enter the browser bundle. The sample credentials are for local development only.

Open:

- Application: http://localhost:5173
- API documentation: http://localhost:8000/docs
- API liveness: http://localhost:8000/api/health
- Database/schema readiness: http://localhost:8000/api/ready

```sh
docker compose ps
docker compose logs backend migrate worker dispatcher
docker compose down
```

`down` preserves named `postgres_data`, `document_data` and `redis_data` volumes. Do not use `down -v` for routine cleanup. Changing the password in `.env` after initialization does not change an existing PostgreSQL role's password. All published ports bind to `127.0.0.1`; authentication is not implemented, so keep this workspace local.

## Verification

Frontend (Node.js 22.12+ and npm):

```sh
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

Backend checks against the running service (unit tests run; database integration tests skip unless explicitly configured):

```sh
docker compose exec backend python -m pytest -q
docker compose exec backend ruff check .
docker compose exec backend ruff format --check .
```

Run **all backend tests**, including real PostgreSQL creation/listing, clean migrations, schema drift and downgrade/upgrade checks, in an isolated ephemeral database:

```sh
docker compose -p rag-studio-tests -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -p rag-studio-tests -f compose.test.yaml down
```

The test database lives in tmpfs and never uses the development volume. Start a fresh test stack for each run; integration tests refuse a nonempty project schema. Without `TEST_DATABASE_URL`, integration tests report explicit skips. An externally supplied test database must be empty and its name must end in `_test`.

Browser journeys use a dedicated full application stack with separate persistent test volumes (ports 5174/8001):

```sh
docker compose -p rag-studio-e2e -f compose.e2e.yaml up --build -d
cd frontend
npx playwright install chromium
E2E_BASE_URL=http://127.0.0.1:5174 npm run test:e2e
cd ..
docker compose -p rag-studio-e2e -f compose.e2e.yaml down
```

These journeys create unique test projects/documents and cover TXT/PDF processing, validation, parsing failure/retry, versioned chunk pagination, reload and mobile overflow. Test records remain in `rag-studio-e2e` volumes for inspection and restart verification. Never point browser tests at a shared or valuable dataset. The default Playwright target is the isolated stack on port 5174.

## Local development

Start the database and migrate with Compose, then run the API and Vite locally. Use only one backend/frontend on each port at a time:

```sh
docker compose up -d db redis
docker compose run --rm migrate
cd backend
uv sync --frozen
# Match your root .env credentials. The default below works with .env.example.
# Local API and local worker must share a writable storage directory.
export STORAGE_PATH="$PWD/.local-documents"
export REDIS_URL=redis://localhost:6379/0
export DATABASE_URL='postgresql+psycopg://rag:change-me-local-only@localhost:5432/rag_studio'
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Redis is internal to Compose by default. For fully local Python processes, provide a local Redis instance on 6379 or an explicit loopback-only Compose port override. Run `uv run celery -A app.workers.celery_app:celery worker --concurrency=2` and `uv run python -m app.workers.dispatcher` in separate backend terminals with the same DATABASE_URL, STORAGE_PATH and REDIS_URL. The all-Compose setup is the simplest complete workflow.

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Vite proxies `/api` to `127.0.0.1:8000`. CORS allows only `http://localhost:5173` and `http://127.0.0.1:5173`; configure `CORS_ORIGINS` as a JSON array on the backend if needed. Database requests have connection and statement timeouts.

Backend dependencies are pinned in `pyproject.toml` and `uv.lock`; Docker installs the exported `backend/requirements.lock` (including verification tooling). After intentional dependency changes regenerate it with:

```sh
uv lock --directory backend
uv export --directory backend --frozen --no-hashes --no-emit-project --all-groups -o requirements.lock
```

Frontend dependencies are pinned in `package.json` and `package-lock.json`.

## API behavior

- `GET /api/projects?limit=20&offset=0`: newest first, stable ID tie-break, `items`, `total`, `limit`, `offset`. Limit 1–100; offset nonnegative.
- `POST /api/projects`: JSON `{"name":"Support research","description":"Optional context"}`. Returns 201 with UUID and UTC creation time. Names trim whitespace and require 1–120 characters; descriptions allow up to 2,000 characters. Duplicate names are allowed.
- `GET /api/health`: API process is alive, independent of PostgreSQL.
- `GET /api/ready`: database is reachable and project/document/run/chunk schema is present; otherwise 503.
- Invalid input returns 422; database failures return a generic 503 without connection details or submitted data.

A lost response after creation may mean the project was saved. Refresh before retrying; creation is not idempotent. No shared-user authorization, project/document editing or deletion, or public deployment is included.

See [milestone progress](docs/implementation-plan.md) and [architecture](docs/architecture.md).

## Knowledge Base workflow

1. Create/open a project by clicking its name.
2. Select one PDF or UTF-8 TXT and upload it. The default limit is 20 MiB; `MAX_UPLOAD_BYTES` configures the backend and displayed UI limit (up to 100 MiB).
3. Set chunk size (1–100,000 characters) and overlap (0 to size minus one), then **Start processing**. A saved version appears in history; status/progress come from PostgreSQL.
4. Inspect completed chunks. PDF page numbers and page-relative character offsets accompany exact extracted text. Use the chunk pagination controls for longer documents.
5. Cancel queued/running work when needed. Failed/cancelled runs can be retried with **Start processing**, preserving the earlier version. Reprocessing a successful document also saves a new version.

A scanned PDF requires OCR and fails explicitly; malformed/encrypted PDFs fail in the worker. Empty/invalid UTF-8 TXT and unsupported file types fail upload. Duplicate uploads are separate documents. If a response is interrupted, refresh before retrying to avoid accidental duplicates.

Fixed windows are measured in Unicode code points, preserve whitespace, and never cross PDF page boundaries. The final window ends at the source end without adding an overlap-only tail. TXT removes an optional initial BOM. For detailed boundaries, limits and extraction caveats, see [architecture](docs/architecture.md#versioning-and-deterministic-parsing).

## Document API

All paths below start with `/api/projects/{project_id}`; wrong-project document, run and chunk IDs return 404.

- `GET /api/projects/{project_id}`: selected project metadata.
- `GET /upload-settings`: configured file limit.
- `GET /documents?limit=20&offset=0`: document metadata and latest processing run, newest uploads first.
- `POST /documents`: multipart with exactly one `file`; 201 returns immutable document metadata.
- `POST /documents/{document_id}/runs`: JSON `{"chunk_size":1000,"overlap":200}`; 202 returns the queued run. An active run returns 409.
- `GET /documents/{document_id}/runs?limit=20&offset=0`: newest processing versions first.
- `GET /documents/{document_id}/runs/{run_id}`: authoritative status, progress, settings, attempt count and safe error.
- `POST /documents/{document_id}/runs/{run_id}/cancel`: cancel queued/running work; terminal runs are unchanged.
- `GET /documents/{document_id}/runs/{run_id}/chunks?limit=20&offset=0`: complete successful chunks only; other states return 409. All collection limits are 1–100.

## Operations and current limits

The dispatcher is required: it sends PostgreSQL queued jobs every five seconds and recovers interrupted running jobs after 180 seconds. Each run permits at most three automatic attempts; parsing errors fail immediately. Redis downtime keeps jobs queued, visible and cancellable. Restarting `dispatcher` resumes delivery/recovery. `docker compose logs worker dispatcher` contains operational errors without source text.

Cancellation prevents publication, but in-flight parsing can continue until the next page checkpoint or the 120-second hard time limit. Current processing bounds are 2,000 PDF pages, 5 million extracted characters, 50,000 chunks and 10 million output characters including overlap. PDF text/layout extraction can be imperfect; inspect evidence, especially mixed text/image pages. OCR is not available.

To verify persistence in the isolated browser stack, process a file and record its document/run IDs, then run `docker compose -p rag-studio-e2e -f compose.e2e.yaml restart db redis backend worker dispatcher frontend`. After readiness returns, reopen that project, inspect the original version and start another version from the saved upload. Both PostgreSQL and `document_data` must be retained. For stronger verification, stop/start the stack with `down` and `up -d`, preserving volumes.

Back up database and document volume together while uploads/processing are stopped. Schema changes use Alembic. No deletion API exists. A process crash or ambiguous database commit can leave orphan files; the safe offline inspection procedure is in [storage architecture](docs/architecture.md#storage-and-upload-transaction). There is no automatic persistent-file cleanup. This remains an unauthenticated local workspace; shared access and production backup/restore procedures belong to a later milestone.


## Milestone 2B: indexing and retrieval

Set these values in the root `.env` (the key stays in backend/worker environments):

```dotenv
OPENROUTER_API_KEY=your-local-key
EMBEDDING_PROVIDER=openrouter
EMBEDDING_MODEL=openai/text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EMBEDDING_BASE_URL=https://openrouter.ai/api/v1
EMBEDDING_REVISION=1
EMBEDDING_REQUESTS_PER_MINUTE=60
```

Run `docker compose up --build -d` after changing settings. A plain `restart` does not load changed Compose environment values. Migration `0003` enables the vector extension and preserves existing documents/chunks. Missing credentials leave document processing available and show an actionable indexing configuration message. There is no synthetic embedding fallback.

1. Upload and successfully process one or more documents in a project's Knowledge Base.
2. Select **Prepare document set**. This resolves the current successfully processed documents to exact processing-run IDs, then saves their immutable chunk membership and embedding configuration under the project's **Uploaded documents** knowledge set. A newer failed or unfinished processing run does not replace the last successful run. API callers may submit `document_ids` to narrow the snapshot.
3. Wait for **Ready**, then select **Use document set** on that exact version. The knowledge set records its current ready version, while every earlier ready version remains usable.
4. Enter a query and a result count from 1 to 50, then select **Test retrieval**. Results show the exact index version, ranked text, filename, document/run identity, content hash, PDF page and character offsets. Cosine distance is lower for closer vectors; it is not confidence or proof of relevance. This feature does not generate answers.

Index APIs under `/api/projects/{project_id}`:

- `GET /embedding-settings`: safe provider configuration/readiness, never credentials.
- `POST /indexes`: returns 202 and the index UUID (also its durable job ID). An optional body accepts `knowledge_set_id` and one or more explicit `document_ids`; omitting the body preserves the default Knowledge Base action.
- `GET /indexes?limit=20&offset=0` and `GET /indexes/{index_id}`: history/progress with knowledge-set identity and exact processing-run count.
- `GET /knowledge-sets?limit=20&offset=0` and `GET /knowledge-sets/{knowledge_set_id}/indexes`: project-scoped knowledge sets and their immutable versions.

Existing Files ingestion is available under **Pipelines → Ingestion pipelines**. Select already processed project files, preview whether their processing versions will be reused, save the immutable graph, then run it. The durable run coordinates any required reprocessing and publishes one new ready index to the chosen knowledge set only after all embeddings succeed. Its per-file inspector retains content hashes, processing versions and chunk counts; the published link opens the exact immutable index that an answer pipeline can select.

The corresponding project-scoped API operations are `POST /ingestion-previews`, `GET/POST /source-previews/...` for durable preview progress, paginated outcomes and cancellation, `POST /pipelines/{pipeline_id}/versions/{version_id}/ingestion-runs`, and `GET/POST /ingestion-runs/...` for execution progress, items and cancellation.

Website sources support both preview and execution. Single URLs, explicit URL lists, bounded same-origin crawls and XML sitemaps use origin/path rules, robots.txt, canonical duplicate detection and hard page/depth/byte/time/rate/redirect limits. The backend revalidates DNS and redirects against non-public destinations and never renders or executes fetched HTML. A saved run stores immutable HTML revisions, extracts deterministic main content with section provenance, reports new/changed/unchanged/removed URLs and atomically publishes an exact index while preserving older ready versions. Credentialed connectors remain unavailable pending the Phase 6 secret-storage decision.
- `POST /indexes/{index_id}/cancel`: cancel queued/running indexing.
- `POST /retrieval`: `{ "index_id": "<ready UUID>", "query": "question", "top_k": 5 }`.

Each worker delivery processes at most 16 chunks (a 24,000 character batch target), with validated embeddings committed as a checkpoint. Incomplete indexes are never searchable. Transient failures retry after at least 30 seconds, with three consecutive failed attempts per batch; successful batches reset that counter. A stopped worker is recovered after 180 seconds. Cancellation invalidates its execution token: in-flight provider requests may still incur charges, but cannot publish. A user retry creates a new version; compatible, exact-text vectors can be reused only within the same project. There are no deletion endpoints or automatic vector cleanup.

The initial adapter accepts the OpenRouter endpoint and OpenAI text-embedding-3 model IDs. Indexing and vector querying must match the saved provider, model, dimensions, endpoint fingerprint and revision; incompatible settings return an error. Restore the old settings to query an older configuration, or create a new index. Increment the revision if a model alias changes behavior. Each chunk/query is conservatively limited to 8,191 UTF-8 bytes without truncation; reprocess oversized chunks with smaller settings. Indexes are bounded at 50,000 chunks. Retrieval supports exact pgvector cosine search, PostgreSQL keyword search and weighted hybrid rank fusion. There is no approximate vector index or reranking. See [retrieval settings](docs/development.md#retrieval-search-settings) for controls, API contracts and migration behavior. Shared Redis limits worker and query embedding requests to 60/minute by default; Redis must be available for provider execution. Costs are not calculated or presented as zero.

The adapter follows [OpenRouter's embedding endpoint](https://openrouter.ai/docs/api/api-reference/embeddings/submit-an-embedding-request) and uses [pgvector's SQLAlchemy cosine distance support](https://github.com/pgvector/pgvector-python#sqlalchemy).

### Bounded verification without credentials

Backend provider doubles are confined to tests. To exercise the real API, database, Redis, dispatcher, Celery and React flow with a **test-only HTTP transport**, use a separate fixture stack:

```sh
E2E_API_PORT=8002 E2E_UI_PORT=5175 docker compose -p rag-index-e2e -f compose.e2e.yaml -f compose.index-e2e.yaml up --build -d
cd frontend
E2E_BASE_URL=http://127.0.0.1:5175 E2E_EMBEDDING_FIXTURE=1 npm run test:e2e
cd ..
docker compose -p rag-index-e2e -f compose.e2e.yaml -f compose.index-e2e.yaml down
```

Do not use the fixture override with developer data. It explicitly starts `tests.e2e_provider`, which the normal application never imports. The default browser stack forces credentials empty and tests the missing-configuration UI. Its ports can also be changed using `E2E_API_PORT` and `E2E_UI_PORT`.

An optional external adapter check embeds two short strings only:

```sh
docker compose exec -e RUN_LIVE_EMBEDDINGS=1 backend python -m pytest tests/test_embedding_live.py -q
```

This requires locally configured OpenRouter credentials/credits and Redis; it is disabled by default. A complete live acceptance check additionally indexes a small real document and retrieves its evidence through the UI. Automated fixture success does not verify provider credentials, billing, model availability or semantic retrieval quality.

### RAG playground (Milestone 3)

Set `CHAT_MODEL` in the server `.env` to an OpenRouter chat model ID. This workspace uses `openai/gpt-5.6-luna`, as selected by the user. Keep `CHAT_CONTEXT_TOKENS=8192` and `CHAT_MAX_TOKENS=1024` initially; the context setting must not exceed your selected model's documented limit. `OPENROUTER_API_KEY` is reused; embedding settings remain separate. Rebuild with `docker compose up --build -d` to apply settings and migration `0004`.

Open a project, upload/process/index documents, then choose **Open RAG playground**. Select a ready index, enter a question and top k (1–50), and choose **Ask question**. Each request is independent, with no conversation history. Click valid source labels to inspect the exact evidence sent. Invalid/missing references are flagged; membership validation does not verify claim support. Insufficient evidence is explicit, and prompts do not guarantee grounding or prevent prompt injection.

History survives reloads. Failed accepted runs remain visible; refresh history before retrying an interrupted response. Runs still marked running after five minutes become interrupted failures when history/detail is read. Generation has bounded network timeouts and no automatic retry. Costs are unavailable unless returned by OpenRouter and exclude retrieval embedding charges. Standalone playground runs do not support streaming or cancellation. Saved canvas pipelines and cancellable background experiments are described below; shared access, hybrid retrieval and reranking remain deferred.

API: `POST /api/projects/{id}/query-runs` with `{ "index_id": "UUID", "question": "...", "top_k": 5 }`; list with `GET` and `limit`/`offset`, or fetch `/{run_id}`. A 201 response contains the saved run, including execution failures in `status`/`error`. Validation and missing/unready index errors use HTTP 422/404/409.

Milestone 3 deterministic browser verification uses the separate stack (alternate ports avoid existing test services):

```sh
E2E_API_PORT=8002 E2E_UI_PORT=5175 docker compose -p rag-m3-e2e -f compose.e2e.yaml -f compose.index-e2e.yaml up --build -d
cd frontend
E2E_BASE_URL=http://127.0.0.1:5175 E2E_EMBEDDING_FIXTURE=1 npm run test:e2e
```

This fixture module lives only in `backend/tests`; it does not activate fake behavior in production. See `docs/implementation-plan.md` for actual verification results and `docs/architecture.md` for persistence, budget and failure semantics.

### Visual pipelines (Milestone 4)

Open a project's **Open pipeline editor**, then **New answer pipeline**. Select Retriever to choose a ready index and top k; select Prompt to edit answer instructions; select LLM for the server-configured model, output limit and temperature. Save a version, enter a question and **Run pipeline**. Click source references to inspect evidence; expand the effective prompt to inspect actual messages/settings. **Refresh runs** reopens persisted pipeline runs. The existing Playground remains available.

The supported graph is exactly Question → Retriever → Prompt → LLM → Answer. Nodes can be dragged, selected, deleted and re-added from the palette; drag handles to connect them. Use the labeled Selected node form without dragging. Delete selected edges with Delete/Backspace. Invalid graphs show errors and cannot be saved or run. Save/discard edits before switching versions, duplicating or executing. Versions preserve configuration and layout; duplicates get a new pipeline identity. Invalid unsaved drafts are not persisted.

Prompt example:

```text
Answer concisely using the retrieved evidence.
Question: {question}
Retrieved context: {context}
```

Only these two literal variables are supported, and both are required. No code or expressions are evaluated. Source labels, grounding rules and citation formatting remain application-controlled. Keep `CHAT_MODEL` as the default; optionally set `CHAT_MODELS='["provider/another-chat-model"]'` on the server. Operators must authorize model availability and keep `CHAT_CONTEXT_TOKENS` within all allowed models' limits. Credentials never enter the browser.

Pipeline API (under `/api/projects/{project_id}/pipelines`): `GET /options`, paginated `GET /`, `POST /` (create/duplicate), `GET /{id}/versions`, `POST /{id}/versions`, `GET /{id}/versions/{version_id}`, and `POST /{id}/versions/{version_id}/runs` with `{"question":"..."}`. Runs return 202 and can be read through the existing project query-run endpoints. Apply Alembic migration `0005` before starting the updated API (`docker compose up --build -d` runs the migration service).

Runs are non-streaming background API tasks, with persisted status polled by the editor. Interrupted tasks become failed on a history/detail read after five minutes; there is no automatic paid retry, cancellation or durable generation queue. Refresh history before retrying an ambiguous response. Shared access, branching, reranking and hybrid retrieval remain deferred. Cancellable durable evaluation jobs reuse these saved pipelines as described below.

### Evaluation datasets and experiments

**Experiments** in the project sidebar supports reviewed CSV datasets, immutable versions, one/two saved pipeline candidates, RAGAS scoring, durable progress/cancellation, paired comparisons and per-question answer/evidence inspection. Preview CSV before importing; download an example from the import panel. Reference answers are optional; reference-based context recall is unavailable without them. LLM scores are estimates requiring human review, not accuracy certification.

Configure `EVALUATOR_MODEL` separately from `CHAT_MODEL`, using server-side `OPENROUTER_API_KEY`. Response relevancy reuses the configured OpenRouter embedding adapter. Recreate backend/worker/dispatcher after configuration changes. Metrics and generation errors remain separate; completed results survive failures. Unknown costs remain unavailable, and query-generation/evaluator costs are separated. See [development instructions](docs/development.md) and [architecture](docs/architecture.md) for limits, snapshots, recovery, safe CSV exports and the opt-in three-question live check.
