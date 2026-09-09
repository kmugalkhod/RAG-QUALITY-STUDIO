# RAG Quality Studio

Milestone 2A adds a project Knowledge Base: upload PDF/UTF-8 TXT files, run background parsing and character chunking, cancel or retry processing, and inspect paginated versioned chunks with PDF page provenance. React/TypeScript, FastAPI and PostgreSQL are joined by Celery and Redis. Processed documents are not indexed or searchable. Embeddings, model calls, pipelines and evaluation remain unimplemented.

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
