# AGENTS.md — RAG Quality Studio

## Product purpose

RAG Quality Studio is a complete full-stack application for visually configuring, executing, inspecting and evaluating retrieval-augmented generation (RAG) pipelines.

Build working software with real integrations and persistent state. The product must let users manage projects and documents, configure supported pipelines, ask questions with evidence, and compare experiments for quality, latency and cost.

Deliver incrementally. A milestone is an implementation boundary, not permission to replace functionality with mock results. Do not describe the application as a toy, portfolio-only application or production-ready before the relevant behavior has been verified.

## Working agreement

- Inspect the repository, applicable instructions, Git status and existing implementation before changing files. Preserve unrelated work.
- Follow the user's current task. Use this document for durable conventions; do not implement the whole roadmap unless requested.
- Briefly state the plan for substantial changes, then implement and verify the authorized work.
- Resolve routine implementation choices independently. Ask when a missing decision materially changes scope, data ownership, cost or architecture.
- Do not add dependencies, infrastructure or abstractions without a concrete requirement. Prefer a modular application and worker over microservices.
- Fix causes rather than masking failures. Never bypass validation, authorization or tests to obtain a successful result.
- Consult official documentation when using unfamiliar or version-sensitive APIs. Lock compatible dependency versions; avoid unrelated upgrades.
- Do not expose secrets, overwrite unrelated changes, delete persistent data or publish/deploy without appropriate task authorization.
- Keep implementation status in `docs/implementation-plan.md`, not in this file. Record material architectural decisions and trade-offs in `docs/architecture.md`.

## Technology decisions

| Area | Default |
| --- | --- |
| Frontend | React, TypeScript in strict mode, Vite |
| UI | Tailwind CSS and shadcn/ui; accessible, responsive components |
| Visual editor | React Flow (`@xyflow/react`) |
| Backend | Python, FastAPI, Pydantic |
| Persistence | PostgreSQL, pgvector, SQLAlchemy and Alembic |
| Long-running work | Celery workers and Redis, introduced with ingestion jobs |
| Evaluation | RAGAS behind an application-owned evaluator interface |
| Model access | Backend provider adapters; support a configured LiteLLM-compatible endpoint when implemented |
| Local deployment | Docker Compose with persistent volumes |
| Verification | pytest, Vitest, React Testing Library; Playwright for critical browser journeys |

Start with one embedding provider, one answer provider and pgvector. Keep provider names, model identifiers and dimensions configurable. Select the initial provider when model integration is implemented; do not assume credentials exist.

Langfuse integration, additional vector stores and advanced orchestration are extensions, not prerequisites for the foundation. Do not introduce DeepEval alongside RAGAS without a demonstrated need. Kubernetes, billing, enterprise SSO and arbitrary workflow branching are outside the initial release unless requested.

## Repository layout

Use this structure for a new repository. Respect an established equivalent layout instead of moving files unnecessarily.

```text
frontend/
  src/
    app/                 # routing, application providers and shell
    features/            # projects, documents, pipelines, playground, experiments
    components/          # shared UI
    lib/                 # API client and shared utilities
  e2e/
backend/
  app/
    api/                 # HTTP routes and dependencies
    core/                # settings, logging and security
    db/                  # persistence and sessions
    models/              # SQLAlchemy models
    schemas/             # request/response and configuration schemas
    services/            # application use cases
    pipelines/           # ingestion, retrieval, generation and graph validation
    providers/           # model, embedding and storage integrations
    evaluation/          # evaluator adapters and experiment execution
    workers/             # background tasks
  migrations/
  tests/
docs/
  architecture.md
  implementation-plan.md
  development.md
  deployment.md
sample-data/
compose.yaml
.env.example
README.md
AGENTS.md
```

Create modules when needed; do not fill empty directories with speculative implementations.

## Architecture and pipeline boundaries

Keep these operations separate:

1. **Ingestion:** validate upload, parse, chunk, embed and persist an index version.
2. **Query:** embed a question, retrieve from a selected index version, optionally rerank and generate an answer with citations.
3. **Evaluation:** execute a versioned question dataset against saved configurations and score the resulting answers and retrieved evidence.

- The visual canvas edits configuration. The backend validates and executes that configuration.
- Define typed, versioned configuration schemas shared conceptually by the UI and execution engine. Generate API types from OpenAPI where practical.
- Start with explicitly supported pipeline templates and node types. Reject unsupported edges, incompatible types, missing settings and cycles.
- Keep graph coordinates and display labels separate from execution parameters. Never execute arbitrary Python, SQL or shell supplied through nodes.
- A database connector connects to an existing configured service. Do not imply that placing a node provisions infrastructure.
- Thin API routes should delegate to services. Keep model calls and database queries out of React components.

## Data integrity and reproducibility

- Scope projects, documents, index versions, pipeline versions, datasets, jobs and results consistently. Avoid retrieval across projects.
- Use migrations for schema changes. Do not rely on automatic table creation for deployed environments.
- Preserve document provenance: source ID, content hash, version and page/section metadata when available.
- Record parser and chunking settings, including whether size and overlap are measured in tokens or characters.
- Changing parsing, chunking or embedding settings creates a new index version. Retrieval-only changes such as `top_k` can reuse a compatible index.
- Never mix incompatible embedding models or dimensions in one searchable index. Validate the query embedding against the selected index.
- Publish an index as ready only after successful ingestion. Queries must not silently use a partial index.
- Save immutable experiment snapshots: document/index version, pipeline configuration, prompt, models, dataset, evaluator configuration and relevant dependency/code versions.
- Store per-question outputs and retrieved evidence, not just aggregate scores. Represent failed and skipped items explicitly.
- Define deletion behavior for documents, stored files, chunks and dependent historical results. Avoid silent cascades that destroy experiment evidence.

## Backend, jobs and API behavior

- Use typed request/response schemas and consistent validation errors. Validate bounds such as positive chunk size, overlap smaller than chunk size and bounded `top_k`.
- Use parameterized queries and transactions. Add pagination for collections and indexes for demonstrated access patterns.
- Provide API liveness and database readiness endpoints without leaking connection details.
- Execute indexing and batch evaluation in workers. Return a job ID promptly; persist status and progress in PostgreSQL.
- Support queued, running, succeeded, failed and cancelled states, with clear partial-result handling.
- Design tasks to tolerate duplicate delivery. Bound retries, timeouts, concurrency and provider request rates; avoid stacked retry loops.
- Cancellation must stop scheduling further work and accurately represent any in-flight work that could not be interrupted.
- Persist recoverable progress and detect interrupted or stale jobs; do not leave them permanently running.
- Configure CORS explicitly. Keep server credentials out of responses and frontend configuration.

## RAG and evaluation correctness

- Preserve retrieved text, ranks, available scores and citations for inspection. Explain score semantics rather than presenting similarity as confidence.
- Citations must reference evidence actually supplied to the model. Treat retrieved content as untrusted data, not instructions.
- When evidence is insufficient, support an explicit insufficient-evidence response. Do not fabricate citations.
- Begin with dense retrieval. Add hybrid retrieval and reranking as separately tested options.
- Choose metrics with explicit input requirements. Faithfulness measures support in retrieved context; it is not overall factual accuracy.
- Reference-based metrics require appropriate reference answers, contexts or labels. Mark unavailable metrics as unavailable; never assign invented values.
- Use a small human-reviewed dataset initially, including answerable and unanswerable questions. Review generated evaluation questions before treating them as reference data.
- Record evaluator model, prompts, parameters and metric versions. Explain that model-judged scores can vary.
- Compare configurations on the same dataset and source versions. Keep a held-out dataset when tuning configurations automatically.
- Report sample counts, failures and aggregation rules alongside scores. Do not hide failures by dropping them from summaries.
- Separate indexing cost, query cost and evaluation cost. Label estimates and record their pricing basis. Unknown cost is not zero.
- Measure query latency separately from indexing, queue wait and evaluation latency.
- Recommend configurations only from measured experiments under stated criteria. Do not claim automatic root-cause proof, certification or guaranteed accuracy.

## Frontend behavior

- Build real API integrations. Use clearly labelled fixtures only in tests or an explicit sample/demo mode.
- Provide loading, empty, validation, error, progress and cancellation states as applicable.
- Use accessible labels, keyboard navigation and readable contrast. Provide forms for editing node settings rather than relying only on dragging.
- Show unsaved configuration changes and the exact saved version used by a run.
- Include an evidence inspector and per-question comparison, not just charts of aggregate metrics.
- Keep secrets out of browser storage, bundles and `VITE_*` environment variables.
- Clearly mark unfinished features; do not render functioning-looking controls that silently do nothing.

## Security and release behavior

- Use environment configuration locally and an appropriate secret store when deployed. Commit placeholders in `.env.example`, never credentials.
- Validate upload type and size; use generated storage names, safe paths and bounded parsing. Initially support text-based PDF/TXT; report unsupported scanned PDFs clearly.
- Avoid logging raw documents, prompts, personal data or credentials by default. Use project, request and job IDs for correlation.
- Introduce authentication and server-side project authorization before enabling shared access. Test access boundaries for documents, jobs, results and downloads.
- Keep initial unauthenticated development services local. A public sample demo must isolate sample data and limit access to paid execution.
- If URL ingestion is added, implement SSRF protection and bounded downloads. If external databases are added, use scoped credentials and constrained queries.
- Document backup, restore, migrations, persistent storage and deletion procedures before a production release.

## Delivery sequence

| Milestone | Required outcome |
| --- | --- |
| 1. Foundation | React shell, real project creation/listing, API health/readiness, migrations and persistent Compose database |
| 2. Ingestion | PDF/TXT upload, chunk inspection, worker progress and versioned embeddings/indexing |
| 3. RAG | Working questions, retrieval, answers, evidence inspection and insufficient-evidence handling |
| 4. Canvas | Configure, validate, save and execute supported pipelines through React Flow |
| 5. Experiments | Dataset upload, RAGAS evaluation, versioned runs and quality/latency/cost comparisons |
| 6. Release | Authentication and authorization for shared use, CI, deployment, sample workflow and operational documentation |

Document each milestone's acceptance criteria before implementation. Add reliable features in small increments; completing a milestone does not mean the entire product is complete.

## Development commands

The following are target conventions for the initial scaffold, not claims that commands already exist. Implement the relevant scripts as their tooling is introduced and keep this section and the README accurate. Before running commands, inspect the actual manifests.

| Purpose | Command and location |
| --- | --- |
| Start local services | `docker compose up --build` from repository root |
| Stop without deleting data | `docker compose down` from repository root |
| Apply migrations | `docker compose exec backend alembic upgrade head` |
| Backend tests | `docker compose exec backend python -m pytest` |
| Backend lint | `docker compose exec backend ruff check .` |
| Backend formatting check | `docker compose exec backend ruff format --check .` |
| Install frontend dependencies | `npm ci` in `frontend/` after a lockfile exists |
| Frontend lint | `npm run lint` in `frontend/` |
| Frontend type check | `npm run typecheck` in `frontend/` |
| Frontend tests | `npm run test -- --run` in `frontend/` |
| Frontend production build | `npm run build` in `frontend/` |
| Browser journeys | `npm run test:e2e` in `frontend/` with documented test services |

Keep test data in an isolated database/storage location. Automated tests must not reset developer data. Never run `docker compose down -v` as routine cleanup.

## Verification and definition of done

- Test behavior, especially project isolation, input validation, pipeline compatibility, indexing failures, job retries/cancellation and evaluation input requirements.
- Use PostgreSQL/pgvector integration tests for vector/database behavior rather than substituting SQLite.
- Mock external providers for deterministic tests. Keep live provider checks opt-in, bounded and separate from default CI.
- Add browser tests for critical completed workflows and verify important UI states visually when tooling permits.
- Check migrations on a clean database and supported upgrade paths when changing persisted schemas.
- A feature is complete when its requested UI/API/persistence path works, relevant tests pass, failures are handled and documentation matches behavior.
- Run relevant checks for changed areas. Do not claim unrun tests or unverified external integrations passed.
- Finish each task with what changed, how it was verified, any remaining limitations and the next actionable step.
- Keep this file concise enough to remain useful. Add detailed procedures to `docs/` and link them here only after those files exist.
