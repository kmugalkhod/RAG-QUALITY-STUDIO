# Application architecture

## User documentation boundary (2026-09-26)

`docs/site/` is a separate Docusaurus 3 static site with TypeScript configuration, authored Markdown guides and a browser-local search index. Only `docs/site/docs/` and `docs/site/static/` are published by its build; engineering plans and QA evidence under the parent `docs/` directory remain outside that content root. The Vite app links to completed public slugs through `frontend/src/lib/docs.ts`; its non-secret `VITE_DOCS_BASE_URL` defaults to the local docs preview at `http://127.0.0.1:3000`. This keeps the app's canonical `http://127.0.0.1:5273` port and FastAPI's `/docs` route separate. The site is not deployed by this repository change.

Endpoint contracts and schema-model pages are generated from the canonical FastAPI `app.openapi()` into checked-in static site files; the generator's `--check` mode detects drift without requiring a running service. Auth, workflow, error, cost and capability explanations remain authored guides because OpenAPI cannot encode those runtime rules. The isolated browser test provider registers three `/api/test/` routes after app import, so its expanded schema is never used as the public reference. The large generated model catalog is excluded from local full-text indexing to keep task guides and operation headings prominent; it remains reachable through navigation and schema links.

The ingestion schema-v2 node union retains its closed Pydantic branches and inner `algorithm` discriminator for chunk variants, but removes the outer `type` discriminator because OpenAPI mappings require string references and cannot nest the chunk discriminator schema as a mapping value. The validated generated schema is the source for later endpoint-contract generation; authentication and workflow semantics remain authored explanations.

## Extract QA corrections (2026-09-26)

Section and parent-child chunk windows are bounded by both structural section and PDF page. A page-one footer and page-two answer therefore cannot share a chunk that loses page attribution. Both chunker runtime identities advanced to v2 so a new processing run cannot reuse the older cross-page output. Saved extraction derivations now carry page-level origin, fallback, rotation, confidence and language metadata in `content_derivations.pages`; the inspector reads these persisted facts rather than inferring them from counts. The PDF extractor runtime identity advanced for the same reuse boundary.

Existing Files source configuration can mark selected document IDs optional. The immutable pipeline version, ingestion snapshot and run item persist that choice. A schema-v2 quality policy with `failed_item_action=exclude` lets a failed optional processing item become an inspectable `excluded` item; a required failure still fails the run and marks other unpublished items terminal. An index is created only from ready items, and an all-excluded run fails without publication. Successful partial runs report excluded items in `failed_count`; the completion constraint requires processed plus failed to equal discovered. Old versions deserialize with no optional files. The prior ready index remains current when a required item fails.

Document processing records a safe `error_code` for typed extraction failures. The `language_excluded` code is emitted only when the saved disallowed-language action is `exclude` and a `language_not_allowed` finding caused exclusion. The ingestion worker can therefore exclude that source even when it is not marked optional, while ordinary quality failures still obey the optional-item rule. Migration 0028 adds the nullable code without changing historical failure messages; no source text is stored in it.

Save and run validation checks requested active OCR language packs against the server's installed packs. Ingestion node and chunk variants use discriminators, so a rejected field yields its own validation issue instead of every unrelated union branch. Protected artifact reads avoid unnecessary identity updates during concurrent block and thumbnail requests, retaining project authorization and audit records while reducing lock contention.

## Index inspection and current-version guidance (2026-09-14)

The Knowledge Base exposes paginated, project-scoped index records by joining immutable index membership to the exact chunk, processing run and document. Reads include passage text, offsets, source provenance, vector presence, dimensions, norm and only the first eight vector values; the full embedding is deliberately not transferred to the browser. This makes stored pgvector data verifiable without turning a 1,536-dimensional record list into an unbounded response.

Saved answer-pipeline versions continue to reference an exact immutable index for reproducibility. The editor and Playground now compare that selection with the knowledge set's current-ready index, show passage-count drift, and offer an explicit upgrade that becomes a new pipeline version. New answer pipelines begin with the newest current-ready index. The application never silently retargets a saved pipeline after ingestion publishes new data.

Website collection and index construction meet at an immutable source-snapshot boundary. **Collect source & publish index** performs bounded Website discovery/fetch, persists exact source-revision membership, and publishes the initial reusable index only after processing succeeds. Publication records immutable membership and advances the ready pointer; it does not repeat the completed embedding stage. Answer pipelines select that exact ready index version. The optional **Reprocess saved source** path reads a compatible ready snapshot without another Website request and can publish a new index version with changed processing or embedding settings. Historical revisions and indexes remain available, while changed passages can still require embeddings and provider cost.

Website extractor `html-main-v2` treats HTML elements as extraction boundaries rather than chunk boundaries. It joins adjacent cleaned paragraphs, list items and labels with stable separators, applies overlap across the complete page text, and records the common heading ancestry of every resulting window. This prevents short UI labels such as “Create agents” from becoming isolated vectors while keeping character offsets and section provenance deterministic. The extractor-version change participates in the processing hash, so stored pages are reprocessed instead of incorrectly reusing `html-main-v1` revisions.

Playground answer results include a compact RAG quality check with the exact index version, number of passages supplied and citation-link count. Its copy deliberately states that citation membership is not factual validation. Failed runs distinguish retrieval that completed before a generation-provider failure from runs with no usable evidence; the existing Sources & details inspector remains the authoritative evidence review.

## Retrieval settings extension (2026-09-12)

Retrieval uses a shared discriminated settings contract for vector, PostgreSQL keyword and weighted hybrid search. Query/source binding is separated from search tuning in the interface. The existing five-node graph remains supported; no filters, source/filter nodes or reranker were added.

Schema-v1 pipelines retain their original dense behavior. Editable copies normalize to schema v2, and saving creates an immutable new version with nested retrieval settings. Legacy flat Top k API requests normalize at the boundary; ambiguous legacy/new fields are rejected. Query and experiment snapshots persist effective settings before deferred work. Workers execute those values, including candidate counts, weight and cutoff, rather than reconstructing only Top k.

Migration 0007 adds a GIN expression index over immutable chunk text using PostgreSQL simple analysis. Keyword search uses websearch_to_tsquery/ts_rank_cd and needs no query embedding. Hybrid fuses branch ranks with complementary weights and constant 60, bounded to 200 candidates per branch and 50 output chunks. Both branches enforce index membership and project scope; identity deduplication uses processing run and ordinal. A cutoff affects only vector candidates. A failed active branch fails the run; empty branches are valid. Zero-weight branches are skipped.

Evidence distinguishes nullable distance, lexical and fusion scores and branch ranks. Run snapshots retain retrieved outputs separately from evidence supplied to generation; inspectors and experiment exports expose the recorded settings/results. The lexical index adds write cost and migration locking but avoids another search service or re-embedding. Vector search remains exact; no large-corpus recall/latency claim is made. See [retrieval settings](development.md#retrieval-search-settings) for API and operations and the [implementation plan](retrieval-settings-plan.md) for scope and acceptance criteria.

The React workspace calls same-origin `/api` endpoints. Vite proxies requests during development; nginx serves the production build and proxies requests in Compose. Tailwind provides semantic theme utilities; official shadcn component source supplies the shared controls and data-display primitives. Forms use accessible labeled controls.

FastAPI routes delegate project operations to a service using a request-scoped synchronous SQLAlchemy session. Synchronous routes run in FastAPI's thread pool. Pydantic validates and trims inputs; PostgreSQL constraints also protect stored lengths. Project IDs are UUIDs, timestamps are database-generated timezone-aware values. Listing uses bounded offset pagination and a composite timestamp/ID index. Count and rows share a repeatable-read transaction. Duplicate names are allowed because names are labels, not identities.

Alembic owns the schema. A one-shot migration service must complete before the API starts. PostgreSQL uses a persistent named Compose volume. Migration 0003 enables pgvector and stores versioned index embeddings. Document parsing/chunking is described below.

Liveness does not contact storage. Readiness verifies project, protected-document, authentication, processing-run and chunk columns are queryable, catching missing migrations as well as database outages. SQLAlchemy failures become generic 503 responses. Database connection/statement timeouts bound failures. CORS is explicit, all local published ports bind to loopback and local mode has one owner principal. Shared mode validates OIDC and project roles and requires an external KMS/Vault raw-artifact key boundary.

Unit tests exercise input and outage behavior. Database tests require a separate empty PostgreSQL database ending in `_test`, run migrations rather than create_all, and roll back test writes. Compose tests use tmpfs, never the development volume. Playwright journeys use the actual API and leave their uniquely named verification records in the separate browser-test stack.

Projects own document uploads, memberships and processing history. Project deletion is intentionally absent, so no historical evidence can be cascaded away. Celery workers perform parsing/chunking and embedding batches through the OpenRouter adapter; query generation and saved pipeline execution reuse the application RAG service described below. Backup/restore, retention, key rotation, orphan recovery and rollback procedures are defined in [ingestion operations](operations.md); public ingress remains deployment-owned.

Official implementation references: [Vite setup](https://vite.dev/guide/), [FastAPI database session dependencies](https://fastapi.tiangolo.com/tutorial/sql-databases/), [shadcn manual installation](https://ui.shadcn.com/docs/installation/manual).

## Milestone 2A: documents and processing

The Knowledge Base is a project-specific hash route (`#/projects/{id}`), so reload and browser navigation preserve project selection without new routing dependencies. Components call a feature API module; no database or parser work runs in React. Documents, processing history and chunks have bounded pagination. Polling uses fresh requests, suppresses stale responses after navigation, and displays saved run settings separately from editable settings. “Processed” means text chunks exist, not indexed or searchable.

### Storage and upload transaction

`documents` records immutable UUID identity, project, original filename, byte size, SHA-256, detected media type, artifact envelope/retention state and upload time. Repeated uploads always create separate identities. Browser MIME types are untrusted: bounded bytes and the extension are checked. UTF-8 text formats exclude NUL; PDF and Office packages require their byte signatures/package members, then receive full structural validation in the worker. Invalid signed containers therefore upload only when their outer type is valid and fail extraction with a safe error.

An ASGI body limit bounds multipart spooling to the configured file limit plus 64 KiB overhead, including requests without Content-Length. Exactly one multipart `file` field is accepted. The default file limit is 20 MiB (configurable up to 100 MiB); nginx has a 101 MiB transport ceiling. Original names are metadata only. Bytes are streamed to an exclusive generated `.part` name, hashed and fsynced; an atomic rename and directory fsync precede the database commit. API and workers share the named `document_data` volume.

Known failures before commit remove staged/final files and roll back records. An ambiguous commit or process crash can leave an unreferenced file, but must never trigger deletion of a possibly committed file. This favors referential safety over immediate reclamation. With writers stopped, operators use the [orphan inspection procedure](operations.md#stale-jobs-derivations-and-orphan-storage). Document deletion is blocked by active or historical ingestion/index references. Fenced retention cleanup removes only expired encrypted raw bytes and wrapped keys; redacted derivations, runs, chunks and historical evidence remain.

### Versioning and deterministic parsing

Every start creates a numbered `processing_runs` row, retaining chunk size, overlap, `characters-v1` and the pinned parser version. Failed/cancelled runs remain immutable history; a user retry is a new version. Only one queued/running run per document is permitted by a PostgreSQL partial unique index. Version allocation is serialized on the document row. All API access reaches documents through the requested project and runs/chunks through that document. Foreign keys preserve ownership chains.

`characters-v1` measures Python Unicode code points, not bytes, graphemes or tokens. TXT drops only an initial UTF-8 BOM; CRLF, whitespace and Unicode content otherwise remain unchanged. PDFs use pypdf's extracted text order; offsets are relative to that extracted page text. Within each nonblank page/source: start at 0, take `[start, min(start + chunk_size, length))`, advance by `chunk_size - overlap`, and stop as soon as a window reaches the end. There is no extra overlap-only trailing chunk, word-boundary adjustment or cross-page window. Blank pages produce no chunks; PDF page numbers remain 1-based and chunk ordinals are 0-based. TXT page is null. Bounds are enforced in schemas and database constraints.

PDFs are parsed with strict pypdf. Encrypted/malformed PDFs fail. Image-only pages in otherwise mixed documents fail as requiring unsupported OCR; entirely nonextractable documents fail with the same explanation. Text extraction order/layout is parser-dependent; detecting nonempty text does not certify extraction completeness. A page with both extractable text and image-contained text may still require human inspection. There is no OCR or semantic chunking.

Processing limits: 2,000 PDF pages, 5,000,000 extracted characters, 50,000 chunks and 10,000,000 total output characters (including overlap). The worker has 110-second soft and 120-second hard task limits, concurrency 2, prefetch 1, child recycling and a Compose memory limit. Large/pathological compressed PDFs may terminate a worker and are handled by bounded stale recovery. These are local-use bounds, not a hardened public parsing sandbox.

### Queue, duplicate delivery, cancellation and recovery

PostgreSQL is the durable queue and sole status authority. The API commits `queued` and returns 202 promptly; it never waits for Redis. A dedicated dispatcher scans every five seconds, sends only run IDs to Celery/Redis, and re-sends a queued run already handed to the broker only after `DISPATCH_RESEND_SECONDS` (default 300), so a busy broker backlog is not multiplied by duplicate deliveries. See "Ingestion throughput and fairness" below. Redis AOF improves queue persistence but is not necessary for reconstructing accepted jobs. A crash between broker send and recording dispatch time may duplicate a message; a broker outage leaves the durable job queued. Dispatcher transactions lock a bounded batch with `SKIP LOCKED`.

Workers open their own sessions. A short READ COMMITTED row lock claims only queued work, increments the database attempt counter, and assigns a fresh execution token. Running/terminal duplicate deliveries are no-ops. Parsing occurs outside transactions; progress and cancellation are checked between pages. Chunk count/output-size checks bound per-page window generation. Chunks remain in bounded worker memory until a final row-locked transaction verifies the token/status, inserts every chunk and marks success together. Failed/cancelled/recovered attempts cannot expose a partial successful chunk set or publish under an obsolete token.

Cancellation conditionally changes queued/running to cancelled and invalidates the token. It prevents publication immediately; an in-flight parser call may continue until its next page checkpoint or time limit. UI/API explain this distinction. Completion/cancellation are serialized by the row lock; cancelling an already terminal run returns that terminal state.

The dispatcher recovers running attempts older than 180 seconds from start (beyond the worker hard limit): invalidate the token, requeue if fewer than three attempts, otherwise mark failed with an interruption error and finish time. Transient storage/database failures also requeue up to the same three-attempt cap; the worker schedules the retry itself as a delayed Celery message (30 seconds), and the dispatcher resends it only if that message is lost; deterministic parser errors fail immediately. There is no stacked Celery automatic-retry loop. If database access fails while recording an error, stale recovery performs the eventual transition after connectivity returns. Queued work can remain queued while workers/broker are offline; this is visible and cancellable. Keep the dispatcher running (`restart: unless-stopped`); restart it to resume recovery after an outage. Operators should inspect failed runs and adjust inputs/settings before starting new versions.

### Verification boundaries

Shared pytest fixtures require an empty dedicated PostgreSQL database ending in `_test`. API-only tests roll back; worker integration tests commit to that isolated database and delete only their own IDs after each case. Upload storage is pytest's temporary directory. The isolated backend Compose database is tmpfs. `compose.e2e.yaml` runs the complete app with its own database, Redis and document volumes and alternate loopback ports; browser and restart checks never touch development storage. No embeddings, vector extension/index, model calls, question answering, canvas or evaluation are part of 2A.

Implementation references: [Celery task acknowledgement, limits and duplicate delivery](https://docs.celeryq.dev/en/stable/userguide/tasks.html) and [pypdf text extraction and OCR limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

The nginx API proxy resolves the Compose backend service through Docker DNS with a five-second cache, so recreating the API container does not leave the frontend pointed at its old address. See [nginx variable proxy_pass resolution](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass).


## Milestone 2B: versioned indexes and dense retrieval

`index_versions` combines an immutable knowledge-set snapshot identity and its durable indexing job. Migration `0009` moves every historical project index, without changing its ID, into that project's generated **Uploaded documents** knowledge set. Version allocation and the partial active-job constraint are now scoped to a knowledge set. Creation persists exact `(processing_run_id, chunk_ordinal)` membership into `index_chunks`; the reusable construction service requires explicit successful processing-run IDs. The compatibility Knowledge Base action resolves either its submitted document IDs or the current default document selection to an explicit latest-successful run list before calling that service. Those immutable runs retain parser, character chunking and source provenance. Later processing and uploads never alter prior membership or ready vectors.

A dimensionless pgvector `vector` column supports different saved dimensionalities across index versions. Each member's dimensions use a composite foreign key to its parent index and a `vector_dims` check; zero vectors are rejected. Application validation rejects incorrect count/order/model, non-finite values and dimension mismatches before a batch is committed. The worker marks success only when every member has a vector. Queries require an explicit successful index and filter by both index UUID and source project, preserving provenance via exact chunk joins. There is no approximate vector index initially; exact cosine search is bounded by 50,000 members and database statement timeouts.

The provider interface has one runtime adapter: OpenRouter REST, using `openai/text-embedding-3-small`, 1536 dimensions by default. Server settings hold `OPENROUTER_API_KEY` as a secret value; responses expose only model/provider/dimensions, endpoint fingerprint and revision. Queries compare all those settings to the saved snapshot before contacting the provider. No fallback silently changes models or returns synthetic embeddings. Custom providers and endpoint routing require a separately implemented adapter. HTTP requests have bounded connect/read timeouts, no redirect following or SDK retry loop, a response size cap, strict validation, and safe errors. Conservative per-input UTF-8 byte limits avoid truncating evidence or requiring a tokenizer dependency. A Redis atomic counter imposes a shared 60-second request budget across API and workers; failure to reserve prevents a provider call.

Indexing extends the existing Celery/Redis/PostgreSQL queue: short row-lock claim, execution token, one bounded embedding batch outside write transactions, then a fenced checkpoint commit. Each delivery handles up to 16 pending members; batches target at most 24,000 characters. Successful checkpoints requeue the remaining work and reset consecutive failures. Only three consecutive failed attempts for a batch are allowed; transient failures wait at least 30 seconds before dispatch, and deterministic/configuration failures terminate immediately. Stale attempts older than 180 seconds lose their token and consume the same failure budget. There is no task-level automatic retry loop. Attempts count batch claims, not whole-index restarts.

Completed vector checkpoints may be reused for exact matching text and complete configuration only inside their original project, including checkpoints from failed/cancelled builds. One lookup per batch finds candidates through an indexed SHA-256 of the embedded text (`chunks.embedding_text_hash`, maintained by a database trigger, migration `0039`), then compares full text, preventing hash-only reuse. Partial snapshots remain unsearchable. Cancellation invalidates the token before further scheduling; a request already in flight may complete and be billed, but its response cannot commit under the obsolete token. Redis outages leave accepted jobs durably queued; dispatcher restarts recover delivery. On complete publication the knowledge set's project-constrained `current_ready_index_id` changes atomically; older ready indexes remain searchable and saved answer pipelines retain their exact selected index.

The Knowledge Base extends existing form, list, polling and error patterns. Index history, progress, cancellation and explicit ready-version selection are distinct from document processing. The retrieval panel renders source text as plain React text, with rank and distance semantics, and clears old results when inputs/version change. No chat, answer generation, relevance threshold or confidence score is implied.

Milestone 2B tests use real PostgreSQL/pgvector. Unit tests mock only external transports/providers. `compose.index-e2e.yaml` explicitly boots a test module with deterministic HTTP responses for a separate browser stack; no fixture option exists in production settings or app imports. Live checks remain opt-in. Persistent source/chunk/index/embedding deletion is not implemented; foreign keys retain historical dependencies, with no cascade cleanup.

The OpenRouter adapter accepts the exact upstream model name (for example `text-embedding-3-small`) as an alias of its requested namespaced ID (`openai/text-embedding-3-small`). This response form was observed in the bounded live check; unrelated providers/models remain invalid and stored configuration retains the namespaced ID.

## Milestone 3: single-turn RAG execution

`POST /api/projects/{project_id}/query-runs` validates a ready project-owned index before accepting a run. Invalid request/index selection returns 422/404/409 without creating a run. Accepted executions commit a `running` row first; provider/configuration/retrieval failures become persisted `failed` results with safe errors. A composite index/project foreign key prevents cross-project run ownership. No deletion cascades are introduced. Query history and detail reads recover runs older than five minutes as interrupted failures; this recovery is read-triggered, not an automatic retry or background generation queue. A lost client response should be checked in history before resubmission.

Answer execution is compiled with LangChain 1.4's current LCEL runnable API. The validated Question → Retriever → Prompt → LLM → Answer graph becomes a `RunnableSequence`; the retriever implements `BaseRetriever`, query embeddings implement `Embeddings`, prompt rendering uses `ChatPromptTemplate`, and generation implements `BaseChatModel`. These are application-owned bridges: project-scoped SQL/pgvector search, provider allowlists, rate limits, timeouts, no-retry billing policy, context bounds, evidence labels and citation checks remain enforced by this application rather than delegated to arbitrary chains. LangChain and `langchain-core` are direct pinned dependencies; `langchain-community` remains pinned for RAGAS compatibility.

Generation remains behind `AnswerProvider`, with `OpenRouterChat` as the network adapter beneath the LangChain chat-model contract. The user selected `openai/gpt-5.6-luna`; its catalog context limit was 1,050,000 tokens at verification. `CHAT_MODEL`, `CHAT_CONTEXT_TOKENS` (conservative local default 8,192) and `CHAT_MAX_TOKENS` (1,024) are independent of embeddings, and use the existing server-only OpenRouter key. Operators must keep the configured context budget within the selected model's documented context limit. Models are never silently substituted. The actual returned model is also recorded.

The existing shared Redis provider-request budget also bounds chat calls. HTTP uses a five-second connect timeout, 45-second read/write/pool timeouts, a 55-second elapsed response check and a one-megabyte response cap. No application/SDK retries or OpenRouter provider fallback are enabled: retries are manual to avoid duplicate billing after an ambiguous response. Synchronous API workers perform this bounded increment; worker-based batch evaluation is still deferred. Nginx and the playground allow 180 seconds for retrieval plus generation. This is non-streaming and has no cancellation endpoint.

Prompt `grounded-single-turn-v1` contains exactly one system message and one JSON-encoded user message with the current question and untrusted evidence. Context selection greedily includes whole chunks in retrieval rank order if they fit; labels derive from rank (`S1`, `S2`, …) and remain stable if oversized chunks are skipped. Each message's UTF-8 byte length conservatively budgets text tokens plus 256 envelope tokens; output capacity is reserved separately. This deliberately underuses context instead of relying on a model-specific tokenizer dependency. It is a conservative accounting policy, not exact token measurement for arbitrary future model templates. A question that cannot fit or retrieval whose chunks all exceed capacity fails explicitly; empty retrieval returns insufficient evidence without a generation call. There is no similarity cutoff. Saved snapshots retain prompt version, exact messages, all included text and source identifiers/hash/processing version/page/offsets/rank/distance, omitted count, retrieval embedding configuration and chat parameters.

Answers remain plain text. Bracketed references are checked against included source labels, with unknown or malformed grouped labels flagged and never replaced. Valid references are clickable and focus the corresponding evidence. Missing citations are flagged on substantive answers. This only checks reference membership, not semantic support. An `INSUFFICIENT_EVIDENCE` prefix represents model-declared insufficiency; prompts cannot guarantee grounding or prevent prompt injection, and answers still require inspection.

Runs store retrieval, generation and total wall duration in milliseconds (failed stages included when started), returned native token counts, and generation cost only if OpenRouter reports a finite nonnegative USD value. Cost is explicitly generation-only and excludes query embedding/indexing/evaluation charges; unknown costs remain null. No pricing estimate is invented. Unknown stage timings remain null, and empty retrieval records zero generation time because no generation occurred. Exact prompt/evidence snapshots intentionally persist potentially sensitive content in the local database and are not emitted to ordinary application logs.

API/usage references: [OpenRouter request and response schema](https://openrouter.ai/docs/api/reference/overview), [usage accounting](https://openrouter.ai/docs/guides/guides/usage-accounting), and [model catalog](https://openrouter.ai/api/v1/models). The live check returned 173 and 177 total tokens with generation costs $0.0000536 and $0.0000614 respectively; these are provider-reported charges, not price estimates or benchmark claims.

## Milestone 4: saved visual pipelines

The project pipeline editor uses pinned `@xyflow/react` with application-owned custom nodes. The canvas is configuration, never executable code. Version 1 execution JSON requires exactly one Question → Retriever → Prompt → LLM → Answer, unique IDs and exactly the four ordered edges. Pydantic discriminated node schemas reject unknown types/settings, cycles, branches, disconnected/missing nodes and invalid parameters. Both save and run validate project ownership, index readiness and the server chat allowlist. Layout is a separate typed JSON object containing finite bounded positions for exactly those IDs. Labels and handles derive from supported types. React performs equivalent early validation; the backend is authoritative.

`pipelines` is the project-scoped identity/name; append-only API saves create `pipeline_versions` with numbered immutable execution, layout and name. A pipeline row lock serializes numbering, and unique/composite foreign keys protect version identity and project ownership. Concurrent repeatable-read conflicts return a safe database error; clients refresh before manually retrying. No update/delete endpoint exists for versions, and no cascade deletes historical evidence. Duplication creates a new pipeline identity and version 1 from the selected saved configuration/layout. Invalid drafts remain in browser memory until corrected; saving requires a valid executable graph. The editor blocks switching/execution with unsaved edits until save/discard and warns before browser unload.

`CHAT_MODEL` remains the playground default; optional server `CHAT_MODELS` is a JSON array of additional operator-approved OpenRouter chat IDs. All share the conservative `CHAT_CONTEXT_TOKENS` ceiling, which must fit every allowed model. Options expose IDs, budgets and safe missing-configuration errors, never credentials. Editable generation parameters are only `max_tokens` (128–8192 and below context capacity minus prompt reserve) and `temperature` (0–2), both already supported by the adapter. Models are not fetched from the provider or substituted automatically.

Prompt templates require literal `{question}` and `{context}` placeholders. Other braces, attribute access, formatting expressions and custom code are rejected. A single-pass regular-expression substitution inserts the question and JSON-encoded application-labeled evidence; inserted content is never evaluated or substituted again. The rendered instructions are a field in the existing JSON user message, with question/evidence fields retained. The original system grounding and citation policy is fixed. Full messages, including any repeated context in the template, participate in existing conservative context budgeting. Editable instructions cannot configure source labels or citation formatting. This is code-execution safety, not a guarantee against model prompt injection or unsupported answers.

Pipeline run POST commits an existing `query_runs` row with a composite project/version foreign key and returns 202 with its ID/status. FastAPI runs the bounded LangChain-compiled RAG service after the response in its background thread pool with a new database session. The saved frontend execution graph is parsed again at execution time and supplies the exact retriever settings, prompt template, model parameters and authored node IDs; persisted redundant fields cannot silently replace it. Unsupported or corrupted graphs fail instead of executing. The UI polls the persisted query detail each second and renders real running/succeeded/insufficient/failed state. Each run snapshots the immutable pipeline execution/version plus LangChain and `langchain-core` versions, LCEL composition, node order, effective prompt/model/embedding configuration, exact index identity/version, evidence, messages, timings and provider usage/cost. Existing playground requests compile the same default five-stage chain synchronously.

This increment has no durable generation queue, streaming, cancellation or automatic retries. Process loss before/during a background task leaves a running row; the existing five-minute read-triggered recovery marks it failed. Submission response loss is ambiguous: inspect run history before another paid request. Execution timing begins in the background executor and excludes scheduling delay. Provider limits and rate budget remain unchanged. A future worker migration can replace scheduling without changing the saved graph schema or RAG engine.

References: [React Flow TypeScript](https://reactflow.dev/learn/advanced-use/typescript), [state helpers](https://reactflow.dev/api-reference/hooks/use-nodes-state), and the user-provided [AI Elements workflow example](https://elements.ai-sdk.dev/examples/workflow), used as a reference for structured node headers/content/footers and connection handles. Conditional paths and decorative execution animations from that example are outside this release.

Visual defaults use a readable 90% canvas zoom with panning; explicit Fit View provides an overview. The node-settings selector and canvas selection share state, including on create/reopen/add. Unsaved-state comparisons canonicalize JSON object keys because PostgreSQL JSONB does not preserve insertion order. Template runs identify prompt protocol `grounded-pipeline-template-v1`; historical snapshots retain their original prompt identifiers.

## Project workspace frontend (2026-09-10)

The frontend retains the existing React/Vite stack and API adapters. The layout reference is [shadcn/ui's sidebar blocks](https://ui.shadcn.com/blocks?category=sidebar), adapted to this product rather than importing a dashboard or its sample metrics. The current charcoal/lavender design supersedes the earlier green theme. No routing dependency or backend change is required.

`app/App.tsx` owns the persistent sidebar, project switcher, current-project header, mobile navigation and page boundary. `app/navigation.ts` parses hash routes and checks unsaved pipeline changes before updating the rendered route. Hash routes work with the existing nginx configuration and direct refresh. A dirty editor also installs a native unload warning. Rejected history navigation restores the editor URL without unmounting its draft; native browser history may retain a duplicate entry at that restored location.

| URL after `#` | Responsibility |
| --- | --- |
| `/` | Project creation and paginated listing |
| `/projects/:projectId/overview` | Actual source/index/pipeline counts and a contextual next action |
| `/projects/:projectId/knowledge-base` | Upload, processing jobs, indexing and retrieval diagnostics |
| `/projects/:projectId/knowledge-base?document=:documentId` | Open a document's processing history, provenance and bounded chunk inspector |
| `/projects/:projectId/pipelines` | Saved pipeline list and create/open actions |
| `/projects/:projectId/pipelines/new` | Five-node template editor |
| `/projects/:projectId/pipelines/:pipelineId` | Reopen a saved pipeline, select immutable versions, edit/save/duplicate |
| `/projects/:projectId/playground?pipeline=:pipelineId&version=:versionId` | Execute a specific saved version, inspect answers and evidence |
| `/projects/:projectId/settings` | Read-only project identity, upload support and configured embedding/answer availability |

The legacy `/projects/:projectId` hash opens Knowledge Base. New project-list links open Overview. Experiments is absent because evaluation has not been implemented; evaluation work remains paused.

Project content is keyed by project/page/editor identity. The shell only renders project content when its fetched project ID matches the route. Feature requests ignore late responses after unmount. Project switches discard previous documents, indexes, selections, answers and errors immediately; neither data nor evidence is reused across project boundaries. Document detail lookup walks the project's paginated document API because no individual-document endpoint exists. This is a deliberate compatibility trade-off, with extra read requests for large projects.

The editor owns graph configuration only: palette, canvas, selected-node forms, validation, canonical dirty state and save/duplicate/version controls. Test pipeline is enabled only for an unchanged saved version and navigates to Playground with its immutable IDs. Playground is the sole answer runner and reuses `RunResult`; direct index queries remain available for compatibility. Pipeline selection is validated through project-scoped version requests. The exact Playground link is remembered in per-project session storage (IDs only) for sidebar return navigation. Answers and history remain server-persisted; unsaved drafts are memory-only.

Previous runs, timings/token/cost metadata, processing options and retrieval diagnostics use native expandable details. A scrollable, keyboard-focusable chunk list prevents large documents from consuming the whole workspace. Mobile navigation is an inline collapsible region with an expanded state and Escape/focus support; it is not a modal drawer. Canvas settings stack below the graph on small screens. Settings presents available configuration without credentials or unsupported edit controls; configured availability does not prove provider connectivity.

Verification uses the existing isolated PostgreSQL/pgvector/Celery stack and deterministic provider fixtures. Frontend tests cover parsing and rejected dirty navigation; Chromium journeys cover project switching, direct links, refresh/history, mobile navigation and the source → process → index → saved pipeline → answer/evidence workflow. Provider calls in these browser tests are test doubles, not live paid model checks.

### Linear workspace design

The user rejected the first workspace visual treatment and selected Linear as the reference. The selected charcoal/lavender appearance is now defined by semantic shadcn tokens in `src/app/styles.css`; the old `linear-workspace.css` override file was removed. The Knowledge Base pilot has now been extended to every route. Documents use a semantic table; selecting a row opens an adjacent inspector, which replaces the table on mobile. Add document discloses and focuses the existing upload form. Documents/Collections view selection is stored in the hash query (`view=indexes`) and responds to refresh/history. Feature APIs and job behavior are unchanged.

The pipeline editor is a viewport-height flex workspace below the project header, with a compact version/action toolbar, bounded validation area, flexible React Flow canvas and independently scrolling 300px settings panel. The palette overlays the canvas; closing settings returns its width to the graph. Mobile stacks settings below a 55dvh canvas and allows page scrolling. React Flow fits the graph on initial load; users can zoom, pan, fit, or center a node through the labeled selection field. Save is primary for a draft; Test is primary for an unchanged saved version. This follows Linear’s compact chrome and Dify’s canvas-first workflow structure without adding either product’s unsupported capabilities.

### Dark editor reference refinement

The user supplied a dark vertical editor reference after the Linear pass. The shared theme now uses charcoal/lavender semantic tokens. New pipeline templates use vertical positions and top/bottom handles; saved coordinate layouts remain unchanged until Arrange vertically is chosen. This action edits the draft, participates in canonical dirty tracking and is reversible with Discard. Orientation is inferred from saved position ranges; horizontal nodes keep their former width. `useUpdateNodeInternals` refreshes handle bounds on orientation changes, and a cleaned-up ResizeObserver refits the canvas when its container changes size. Model/index settings and execution APIs are unchanged.

A browser regression exposed a save/refresh race: the UI could announce a saved version before the new pipeline URL had been installed while fetching its version list. Save now replaces the URL immediately after the successful save response, before announcing the saved state. Refresh therefore targets the persisted pipeline even while the versions request is pending.

## Milestone 5: immutable datasets and experiments

Dataset identity and append-only versions are project-scoped. CSV accepts UTF-8/BOM, question and optional reference_answer in either order, properly quoted multiline fields, bounded file/row counts, 4,000-character questions and 12,000-character references. Preview reports logical CSV record numbers including the header. Import revalidates the bytes and requires the preview hash. A new version never edits historical questions. Composite project foreign keys connect dataset versions, experiments, pipeline versions and query results; no deletion cascades or update endpoints are introduced.

An experiment stores its durable queue state in PostgreSQL, following existing indexing/processing conventions. Each item identifies a question ordinal and candidate. The dispatcher uses the existing Celery/Redis transport and sends only IDs. Each delivery claims one generation or one metric stage with a row lock and execution token. Generation uses `queries.execute`/`queries.finish`, with an atomic experiment-item/query linkage committed before provider calls. Scores use the exact saved `query_runs.snapshot.evidence` passed to the answer model, never a second retrieval. Dataset rows, pipeline execution, model parameters, index identity/version, embedding configuration, evaluator settings and application source hash are snapshotted on submission.

Completed answers and metric checkpoints survive subsequent failures. Completed-question/candidate progress advances after all selected metrics reach terminal states; failed generation is terminal with skipped evaluation, while missing references remain unavailable. An experiment can succeed as a completed batch while individual generation/metric results fail; summaries report these failures explicitly. Cancellation marks a request while a stage runs, checks between evaluator calls, preserves in-flight results, then marks unfinished items skipped. A queued cancellation finishes immediately. Duplicate running or terminal task delivery does nothing. Stage soft/hard limits are 330/360 seconds, with stale recovery after 420 seconds; the existing 30-second dispatch resend handles lost broker deliveries. Interrupted paid stages are **not retried** (retry budget zero) because charges may already have occurred. Recovery salvages a committed query result or records the interrupted stage as failed and continues remaining work. No stacked SDK/RAGAS/Celery retry loop is used.

RAGAS is pinned to 0.4.3. Its collections API is isolated behind the application `Evaluator` protocol. Custom implementations of `InstructorBaseRagasLLM` and `BaseRagasEmbedding` reuse the bounded OpenRouter HTTP adapters, server-only credentials and shared Redis rate budget. Structured responses are parsed against RAGAS's output schemas without repair retries. `langchain-community==0.4.1` is pinned because 0.4.2 removes the VertexAI module imported by RAGAS 0.4.3. These are transitive framework dependencies, not additional application evaluation engines. RAGAS telemetry is disabled.

`EVALUATOR_MODEL` is independent of `CHAT_MODEL`; this session selected `openai/gpt-5.6-luna`. Snapshots retain RAGAS version, adapter hash, temperature, output limit, strictness=3, embedding configuration, system instruction and exact RAGAS prompt definitions/examples. Each metric stores actual requests, returned model/usage, validated structured judgments and safe errors. Faithfulness measures support for answer claims in supplied evidence, response relevancy compares generated-question embeddings to the original question, and reference-based context recall measures support for reference claims. Abstentions and empty answers make response metrics unavailable. Context recall may still score an abstention if a reference and context exist. Missing references, empty context, non-finite scores and no generated relevancy questions are unavailable rather than invented zeros. RAGAS's cosine-based relevancy is not clamped to a confidence percentage.

Each metric mean uses its own successfully scored denominator. Paired comparisons use only shared successfully scored question ordinals and show both means, B−A and shared count. There is no composite winner. Query timing excludes queue wait and evaluation. Query token/generation cost totals show known sample coverage; unknown is never zero. Evaluation LLM call charges are stored separately. Relevancy's total evaluation cost remains unavailable because the existing embedding adapter does not return billing data. CSV exports prefix spreadsheet-active strings, including leading whitespace and control characters, with an apostrophe.

The workspace adds `#/projects/:projectId/experiments` and `.../experiments/:experimentId`: preview/import, version inspection, one/two pipeline setup, input requirements, persisted polling/cancellation, summaries, paired and per-question comparison, exact evidence and structured judge output. Different indexes receive a visible comparison caveat. Full immutable snapshots are inspectable. Collection APIs retain bounded offset pagination; the local UI loads all pages for selectors/history. Detail responses are bounded by configured dataset limits but can be large because evidence and judge prompts are retained. Project authorization is server enforced; local mode is one loopback owner and shared mode uses OIDC memberships.

Versioned references: [Faithfulness](https://docs.ragas.io/en/v0.4.3/concepts/metrics/available_metrics/faithfulness/), [Response relevancy](https://docs.ragas.io/en/v0.4.3/concepts/metrics/available_metrics/answer_relevance/), [Context recall](https://docs.ragas.io/en/v0.4.3/concepts/metrics/available_metrics/context_recall/). Installed source and custom component abstract interfaces were inspected before implementation; deterministic adapter tests execute the actual three metric classes.

### Browser selection continuity (2026-09-12)

Knowledge Base links retain document/view and an explicit selected `index` query parameter. The frontend resolves that ID through the project-scoped index endpoint, restores its persisted state, and gates passages, retrieval and pipeline handoff on readiness. Hash changes cancel stale selection requests. Per-project session navigation remembers Knowledge Base and saved-pipeline Playground destinations; switching projects reuses only that project's destination. This stores navigation identifiers, not credentials or source text, and does not change execution snapshots or authorize cross-project access.

### Knowledge Base presentation model (2026-09-23)

The Knowledge Base presents the existing execution boundaries as a user-facing
sequence: documents are added, immutable processing versions prepare content,
prepared content is published into a searchable collection, and retrieval targets an
exact immutable collection version. This is presentation and navigation state; it does
not weaken the persisted document, processing-run, knowledge-set or index-version
contracts.

Document navigation loads every project-scoped document page before consolidating
uploads with the same content hash, selecting the most actionable persisted record and
paginating those complete groups in the UI. The underlying uploads and their histories
remain unchanged. Collection navigation likewise loads every paginated index-version
page before grouping versions under their stable knowledge-set identity, then paginates
those complete groups in the UI. Collection detail keeps the selected index UUID and
section in the hash. Overview and provenance use only persisted index metadata;
provider/model/vector data is disclosed on demand. Stored passages and retrieval
results continue to use their existing paginated, project-scoped endpoints, and
pipelines still bind the selected immutable index UUID.


### Playground draft execution and sidebar

Retrieval tests use the existing project-scoped retrieval API without answer generation. Pipeline previews validate a typed execution graph and use the existing query engine; each run records the exact execution, prompt and generation configuration plus optional base pipeline/version in its JSON snapshot. Preview runs do not claim a saved pipeline version or mutate one. Explicit saving uses the existing immutable version API. No database migration is required.

Playground layout rules live in the central application stylesheet; shared controls use shadcn variants and ordinary layout uses Tailwind utilities. On desktop the inspector occupies a reserved right column over the workspace height; its header and save area remain fixed while fields scroll. Messages and source details scroll independently, keeping the composer visible.

## Ingestion pipeline contracts and kinds (Phase 1, 2026-09-12)

Migration `0008` adds `pipelines.kind` as a required constrained string (`answer` or `ingestion`). It uses an explicit nullable-add/backfill/non-null sequence so every pre-existing row becomes `answer`, and adds `(project_id, kind, created_at)` for filtered project listings. Pipeline versions continue to store immutable execution/layout JSON and do not duplicate kind; the parent pipeline is authoritative, and append operations reject a request whose kind differs. Downgrade removes only the discriminator/index/constraint and retains pipelines, versions and query references. Re-upgrading therefore classifies every retained row as `answer`; rollback cannot preserve an ingestion distinction and backend/frontend versions must be rolled back together.

`POST /api/projects/{project}/pipelines` remains backward compatible: an omitted kind selects the strict answer request. Ingestion requests require explicit `kind: ingestion`. `GET /api/projects/{project}/pipelines` retains its unfiltered legacy behavior and accepts the bounded enum filter `?kind=answer|ingestion`; current frontend consumers that require executable answer pipelines always request `answer`. Version reads use the parent route for project isolation. Answer run, preview and experiment submission reject ingestion parents before execution-schema parsing. No ingestion run endpoint or worker exists in this phase.

Answer execution remains in `app.schemas.pipeline`. The separate `app.schemas.ingestion` module defines schema version 1 with one to ten discriminated Existing Files/Website source nodes, then exactly one Extract, Clean, character-window Chunk, Embed and Publish-index node. Every source must feed Extract and the rest must form the exact linear chain. Unknown fields/node/connectors, duplicate IDs/edges/documents/URLs, mismatched layouts, unsafe URL credentials, non-origin allowlist entries, invalid chunk overlap and out-of-bounds crawl settings are rejected and server-owned limits are rejected as unknown fields. Save-time service checks scope Existing Files IDs to the project and requires the saved embedding provider/model/dimensions/revision to equal server configuration. The publish node carries the intended knowledge-set name until Phase 2 introduces the stable project-scoped record and resolves it authoritatively.

`app.connectors.base` is the provider-independent boundary. Immutable contracts cover connection checks; stable external identity/display/canonical location/media type/provider revision/time/parent/non-secret metadata; paginated discovery results and typed failures; and changed, unchanged or failed fetch results with hashes/content references and sanitized retry classification. Connector implementations may raise the same typed safe error for validation/connection failures. Deterministic doubles live only in backend tests. No crawler or credentialed provider SDK is imported downstream.

The frontend extends the existing Pipelines list rather than the answer editor. The active kind is stored as a validated hash query (`kind=answer|ingestion`) and remembered under a project-specific session key for project-switch return navigation. Lists call the real server filter. Ingestion types/API calls belong to `features/ingestion-pipelines`; the production list deliberately disables creation and provides no open, preview, connector, run or worker control until the end-to-end phase exists. Existing answer routes and immutable editor behavior are unchanged apart from the explicit **New answer pipeline** label.

## Knowledge sets and explicit index membership (Phase 2, 2026-09-12)

Migration `0009` adds stable project-scoped `knowledge_sets`, backfills one **Uploaded documents** set for every existing project and associates every historical `index_versions` row without replacing its UUID. A composite `(knowledge_set_id, project_id)` foreign key prevents cross-project index association. Index version uniqueness and active-build exclusion are per knowledge set. The optional current-ready pointer is constrained to an index from the same project and uses PostgreSQL's column-specific `ON DELETE SET NULL` action so clearing an index cannot null the knowledge set's required project identity. New projects create their default knowledge set in the same transaction.

The indexing service has two deliberate boundaries. `create_index_from_processing_runs` accepts a non-empty unique list of project-owned successful processing runs, verifies every run contributes chunks, bounds the combined snapshot to 50,000 chunks and writes exact membership before queuing. The existing `POST /indexes` flow remains compatible: omitted selection means the current successfully processed documents, while optional `document_ids` narrows that selection; either form is first resolved to concrete run IDs. Cross-project, missing, incomplete, duplicate and empty selections fail before a paid embedding call or queued index exists.

Project-scoped `GET /knowledge-sets` and `GET /knowledge-sets/{id}/indexes` expose bounded collection reads. Existing index routes include the knowledge-set ID/name, exact per-set version, distinct processing-run count and whether the index is the current ready version. Knowledge Base groups versions under the real knowledge-set name, and every answer editor or Playground selector labels the name plus exact version. Persisted pipeline/query/experiment index UUIDs are unchanged and never follow the current-ready pointer automatically. No ingestion run, source revision, Website fetch or credentialed connection exists in Phase 2.

## Existing Files ingestion execution (Phase 3, 2026-09-12)

Migration `0010` introduces durable `ingestion_runs` and `ingestion_run_items`. Composite foreign keys bind each run to one project-owned immutable pipeline version and knowledge set, bind every item to a document and processing run from that project/document, and bind at most one index version back to its publishing ingestion run. A partial unique index permits only one queued/running run per destination. Database checks constrain stages, counters, progress and terminal publication invariants; execution tokens and dispatch timestamps remain internal.

Submission validates the saved ingestion graph again, locks its destination and explicitly selected documents, and rejects missing, unprocessed, active or latest-failed files. A latest successful processing run is reused only when parser version and character chunk size/overlap match. Otherwise submission creates a new immutable processing version and snapshots that exact ID. The run snapshot also records document content hashes, source-node ownership, pipeline/version identity, destination and the complete server embedding configuration. Later stages consume only those IDs; they never rescan all project documents.

The coordinator is deliberately orchestration-only. It checkpoints selected processing status, asks the existing explicit-membership index service to create one linked immutable index in the same transaction, then waits for the existing embedding worker. Only a fully successful index advances the run/items to succeeded. Cancellation invalidates the coordinator token and cancels ingestion-created processing and linked unpublished indexes; reused historical processing is never cancelled. Stale recovery consumes a three-failure budget and fences the same child work when exhausted. An already in-flight provider request may finish, but obsolete tokens and terminal parent state prevent its result from publishing.

`POST /ingestion-previews` performs synchronous, bounded Existing Files discovery only and explains reuse/reprocessing without parsing or embedding. Saved-version execution returns 202; project-scoped run and paginated item reads expose safe status, progress, failure and provenance fields, while cancellation is a distinct POST. Existing Files uses no connection and stores no credential. Website and credentialed connectors remain unavailable.

The separate ingestion editor owns its React Flow model, node settings, preview/run polling and result inspector. It uses explicit `kind=ingestion` routes and never weakens the answer editor's five-node schema. Source documents are keyboard-accessible checkboxes, chunk/destination values are ordinary labeled controls, and only the exact unchanged saved version can execute. The published link opens `view=indexes&index=<immutable UUID>`; answer pipelines continue selecting that UUID rather than a mutable knowledge-set pointer.

## Public Website discovery and durable previews (Phase 4, 2026-09-12)

Migration `0011` adds `source_previews` and `source_preview_items`. A preview stores the validated immutable execution snapshot, project ownership, constrained aggregate counters, worker fencing/dispatch timestamps and terminal state; the partial project index permits one active preview. Per-URL outcomes are paginated and retained with source node, canonical location, media type, status, safe reason, size and crawl depth. Terminal retention is capped when new previews are submitted. Preview rows cascade only with their project and cannot reference or create processing runs, source revisions, embeddings or indexes.

`app.connectors.safe_http` is the website SSRF boundary. It accepts credential-free HTTP(S), canonicalizes IDNA hosts/default ports/paths, rejects metadata names and every non-public, multicast, reserved or unspecified IPv4/IPv6 answer, then connects to the approved address while retaining the original Host header and TLS SNI. DNS and scope are checked again for every redirect. Response and total bytes, request timeout, overall deadline, redirect count and identity encoding are enforced while streaming; response bodies never enter errors or logs. This uses Python's pinned standard library rather than introducing another crawler dependency.

`WebsiteConnector` validates single-URL, URL-list, crawl and sitemap selections. It applies explicit origin/path scope before fetch, checks robots.txt by default, performs rate-bounded discovery, parses only HTML links without executing content, rejects entity/doctype sitemap input and records canonical duplicates, exclusions and failures. The configured concurrency value remains part of the immutable contract but Phase 4 intentionally makes no parallel requests; Phase 5 can introduce bounded parallel fetching only with equivalent fencing and budget tests.

`POST /ingestion-previews` now returns 202 for both Existing Files and Website sources. The dispatcher claims queued/stale previews and a Celery worker executes behind an execution token; cancellation or obsolete delivery prevents result commit. `GET /source-previews/{id}` and its paginated `/items` plus POST `/cancel` are project-scoped. The editor exposes every Website bound, uses sequential polling and keeps Website run disabled with explicit preview-only copy until immutable revision/publication behavior exists.

## Website revisions and incremental publication (Phase 5, 2026-09-12)

Migration `0012` adds stable `source_items`, immutable `source_revisions`, per-URL `website_run_items` and explicit `index_source_revisions`. Stable identities are project, connector-kind and canonical-URL hashes. Each revision binds generated raw-artifact storage, content/extracted hashes, safe HTTP validators, fetch time, deterministic extraction configuration and a completed synthetic processing run; these website documents are hidden from upload and Existing Files selection paths. Chunk JSON provenance carries source URL, revision and section hierarchy into retrieval evidence.

Website execution snapshots the saved graph, destination, prior-ready index and complete embedding configuration. The Phase 4 safe client permits only bounded `If-None-Match` and `If-Modified-Since` headers. A 304 reuses the prior stored body; otherwise content hashes determine new/changed/unchanged status. Deterministic HTML extraction ignores scripts/styles and common layout containers, prefers main/article content and creates section-local character windows. Exact extracted-content duplicates reuse a revision, and index construction reuses only embedding vectors compatible in project, text and full provider configuration.

The fenced ingestion coordinator persists discovery/revision membership before delegating to the existing bounded embedding worker. Removed prior URLs are retained historically but omitted from the replacement membership. Required fetch/extraction failures prevent index creation; embedding failure or cancellation cannot advance the destination. Only the existing atomic index completion transaction updates `knowledge_sets.current_ready_index_id`, after which the coordinator marks the run and URL items succeeded. Earlier ready indexes and the answer pipelines that name them remain unchanged.

## Organization OpenRouter keys (2026-10-01)

Shared Clerk organizations bring their own OpenRouter key instead of spending the operator's `OPENROUTER_API_KEY`. Migration `0037` adds `provider_credentials`, unique per `scope_key` (`organization:<clerk org id>`, or `instance` in local owner mode) and provider, plus `provider_credential_events`, which keeps created, rotated, deleted, tested and rejected-by-provider events after a key is removed and never holds secret material.

Keys reuse the artifact envelope boundary (`core/artifact_crypto.py`): a per-write 32-byte data key encrypts the key with AES-GCM and is wrapped by the local keyring, AWS KMS or Vault Transit. Associated data binds the scope, row ID and provider, so a ciphertext copied to another organization's row fails to decrypt. Storing a key requires artifact encryption; without it the API returns 503 and the settings page explains why. Before storing, the server calls OpenRouter `GET /api/v1/key` with bounded timeouts and no redirects, and rejects keys OpenRouter refuses as well as management or provisioning keys, which cannot call inference.

`GET /api/organizations/current/provider-credentials` returns status and a redacted hint (`sk-or-v1-…abcd`) to any member. `PUT`, `POST …/test` and `DELETE` require the Clerk `org:admin` role (the local owner in local mode). No response, log or browser state carries the key.

Provider calls resolve the key per project. Each entry point (query execution, retrieval tests, index creation and the indexing worker, ingestion run creation, answer validation, experiment submission and the evaluator stage, deployment release validation and the deployed-answer worker, and the provider options endpoints) wraps its work in `provider_credentials.bound_for_project`. That decrypts the key once and binds it in a context variable (`providers/credentials.py`) that the embedding, chat and RAGAS adapters read. In Clerk mode an unbound call, a missing key or a rejected key fails closed with an "ask an organization admin" error and never falls back to the environment key. Local mode prefers a stored instance key and otherwise uses `OPENROUTER_API_KEY`; OIDC deployments, which have no organization, keep the operator's environment key. An OpenRouter 401 marks the stored key `rejected` until an admin replaces or retests it. The Redis request budget is keyed per credential (`rag:openrouter:<credential id>:requests`), so one organization cannot exhaust another's budget.

Clerk mode is still loopback-only in development, so startup does not yet require KMS or Vault for it. Before Clerk is opened to shared access, apply the same KMS/Vault requirement that `validate_security_configuration` enforces for OIDC.

## Organization chat model approvals (2026-10-01)

Before this change the LLM node could offer only `CHAT_MODEL` and `CHAT_MODELS`, so an empty environment produced an empty model list with no explanation. Organization admins now approve chat models from the live OpenRouter catalog in **Organization settings**, and the answer editor lists the approved models alongside the server's own.

Migration `0038` adds `chat_model_approvals`, keyed by the same `scope_key` as `provider_credentials` and unique per scope, provider and model, with at most one default per scope (partial unique index). Each row snapshots the catalog label, context length and OpenRouter prompt and completion prices at approval time. A price OpenRouter reports as variable or missing is stored as NULL and shown as unknown, never as zero.

The catalog comes from OpenRouter `GET /api/v1/models?output_modalities=text`, a public endpoint, so no key is sent. The request has bounded timeouts, a 20 MB body cap and no redirects. The response is treated as untrusted data: only well-formed IDs, text-output models, contexts of at least 2,048 tokens and non-expired, non-embedding entries are kept. The parsed catalog is cached in process for six hours. Listing the catalog, approving, removing and choosing the default require `org:admin` (the local owner in local mode). Members can read the approved list. OIDC deployments have no organization, so they keep environment models only.

`provider_credentials.bound_for_project` also binds the scope's approvals in a context variable (`providers/chat_models.py`). `generation.configured()` validates the requested model against the union of approvals and server models, so saves, previews, deployments and the deployed-answer worker apply one rule. Server models stay available so existing pipelines keep working. An organization default outranks `CHAT_MODEL`. Each model's prompt budget is `min(catalog context, CHAT_CONTEXT_TOKENS)`: the server value remains a ceiling, and deployment reservations, which use it as the worst case, stay an upper bound. Removing an approval never rewrites saved versions. Validation reports the model as not approved until an admin approves it again, and the editor keeps showing it.

`GET /pipelines/options` keeps `models: string[]` for existing consumers and adds `model_options`, `default_model`, `error_code` (`no_models`, `provider_key` or `configuration`) and `can_manage_models`, so the editor can explain an empty list and route admins to the settings page.

## Encrypted source connections (Phase 6, 2026-09-13)

Migration `0013` adds project-scoped `source_connections` and append-only lifecycle `source_connection_events`. A connection row stores provider kind, AES-GCM ciphertext, a random 96-bit nonce, secret schema version, server key version and deliberately redacted metadata. Composite connection/project keys protect audit ownership; unique project/name and bounded kind/status constraints remain database-enforced. API response schemas omit all encryption envelope fields. Audit events contain only action, outcome, connector kind and a fixed safe result code—never request data or provider responses.

The user selected application-level AES-256-GCM. `cryptography==46.0.3` is pinned, and the implementation follows its authenticated-encryption requirement that a nonce must never repeat for one key. Every create, credential replacement and re-encryption generates a fresh 12-byte nonce. Authenticated associated data binds schema version, project UUID, connection UUID and connector kind, so copied or altered ciphertext fails closed. A versioned JSON keyring supplies exactly 32-byte base64-decoded keys from server environment only; the active key encrypts new writes while retained older versions permit controlled re-encryption. Authentication-tag, payload-schema, missing-key and configuration errors collapse to one safe application error. [Cryptography AESGCM documentation](https://cryptography.io/en/46.0.3/hazmat/primitives/aead/)

Typed credential envelopes cover S3, Notion and Confluence. The application-owned tester interface receives decrypted values only within the service call, and all three released credentialed sources register real bounded adapters. Connector results map to application-owned safe copy, while arbitrary exceptions and provider text become a generic failure, preventing reflected credentials or response bodies.

Connection routes fail closed unless vault configuration and project authorization are valid. Compose publishes services only on loopback. Local mode additionally requires loopback Host/Origin; shared mode uses OIDC memberships before project-scoped connection access. Frontend credential state is ephemeral, submitted only in POST bodies and cleared after every result; released credentialed source configurations persist only opaque connection IDs.

## Amazon S3 source revisions (Phase 7A, 2026-09-13)

Migration `0014` widens source/document kinds for S3, adds provider revision to preview items and keys immutable source revisions by source identity, content hash and deterministic processing-configuration hash. Existing website rows are backfilled with a stable legacy configuration hash so website refresh also creates a new revision when parsing, cleaning or chunking changes. Downgrade is refused while S3 ingestion history exists rather than silently destroying published evidence.

The pinned Boto3 client is constructed only from an AES-256-GCM-decrypted project-owned S3 connection; ambient credential discovery is never used. Region, connect/read timeout, standard bounded retry count and optional expected bucket owner are explicit. `ListObjectsV2` pagination, page/object/byte bounds and TXT/PDF/storage-class filters produce inspectable preview outcomes. The canonical location is `s3://bucket/percent-encoded-key`; a VersionId is authoritative when available, otherwise the revision combines opaque ETag, size and last-modified. Fetch uses VersionId or `If-Match`, bounds the body and rejects a changed response.

S3 runs reuse the existing fenced ingestion coordinator and generic remote run-item table. Provider I/O occurs outside database transactions. Changed objects are stored under generated encrypted artifact identities and parsed through the bounded released-format adapters; source revision and chunk provenance record connection, bucket, key, version, ETag, size and modification time. Refresh membership is exact: compatible unchanged revisions/vectors are reused, missing keys become removed only from the replacement index, and any required failure prevents index creation or current-ready publication. Connection IDs are server references, not credentials, and project authorization gates previews and runs.

## Notion source revisions (Phase 7B, 2026-09-13)

Migration `0015` widens source/document kinds for Notion while refusing downgrade if Notion history exists. The connector uses the official REST contract with `Notion-Version: 2026-03-11` through the already pinned `httpx==0.28.1`; this avoids coupling the application-owned boundary to a lagging generated SDK. Bearer credentials come only from the project-scoped AES-256-GCM vault. Requests have a hard count, timeout, one bounded retry and fixed sanitized authentication, permission, not-found, throttling and provider mappings.

Discovery supports all shared pages, explicit page UUIDs, or selected data-source UUIDs. Pagination is internal and bounded; results are stable-sorted by UUID. Page UUID forms the canonical `notion://page/...` identity and `last_edited_time` forms the provider revision. Recursive block extraction preserves block identity/type/depth and heading hierarchy while converting supported content to inert plain text. The worker checks the page revision after extraction to reject concurrent changes.

The contract follows Notion's official [pagination](https://developers.notion.com/reference/pagination), [data-source query](https://developers.notion.com/reference/query-a-data-source), [page retrieval](https://developers.notion.com/reference/retrieve-a-page), [block-child retrieval](https://developers.notion.com/reference/get-block-children) and [status-code](https://developers.notion.com/reference/status-codes) references.

Notion uses the same fenced remote coordinator and exact index-membership model as S3. Compatible unchanged page revisions skip content fetch and embedding; changed content produces generated immutable artifacts, processing runs, source revisions and chunk-level Notion provenance. Trashed pages are excluded, and pages absent from a complete refresh are removed from the new membership while historical evidence remains. Permission loss, cancellation, stale delivery, extraction failure or embedding failure cannot advance the current-ready pointer.

## Confluence source revisions (Phase 7C, 2026-09-13)

Migration `0016` widens source/document kinds for Confluence and refuses downgrade while Confluence history exists. Only root HTTPS `*.atlassian.net` Cloud sites are accepted. The pinned HTTP client sends Basic email/API-token authentication to that single origin, follows no redirects, revalidates public DNS for every request and streams JSON under the configured byte limit. Request count, timeout, one retry and `Retry-After` delay are bounded, and provider bodies never enter errors or logs.

REST API v2 discovery supports all accessible pages, exact spaces or exact pages plus optional title/label filters. Provider cursors are extracted but never followed as arbitrary URLs. Stable page identity and version number/timestamp flow into immutable source revisions. The exact storage-format body is revision-checked and parsed without executing markup; chunk provenance retains page, space, element ordinal and heading path. Confluence then uses the shared fenced remote coordinator: compatible revisions avoid fetch/embedding, refresh membership is exact, and partial, failed, cancelled or stale work cannot advance the ready-index pointer.

Website, S3, Notion and Confluence now share one application-owned immutable-artifact
persistence boundary. It owns project/kind/identity lookup, exact revision reuse,
generated artifact storage, synthetic document/processing/chunk rows and best-effort
file cleanup; each connector still owns its identity input, extraction, processing hash,
media types and provenance. Remote discovery and publication advancement live in a
separate worker module selected through an explicit supported-kind map, while the main
ingestion worker retains claim/fencing, Existing Files processing, embedding checkpoints
and terminal job lifecycle. This is an ownership refactor only: transactions, source
snapshot behavior, cancellation checks and atomic ready-index publication are unchanged.

## Ingestion scheduling and recovery (Phase 8, 2026-09-14)

Migration `0017` adds project-scoped `ingestion_schedules`. Each row references one immutable ingestion-pipeline version through a composite project foreign key and stores a validated interval or timezone-aware daily cadence, paused/enabled state, next due time, last run/outcome and an internal claim token. Schedule-to-run references are composite and bidirectional; database checks require scheduled runs to carry a schedule and manual runs not to carry one. The existing partial unique active-run index on knowledge-set destination remains the authoritative overlap fence across manual runs and every schedule.

The dispatcher refreshes terminal outcomes, recovers claims older than 60 seconds and claims at most 20 due rows using `FOR UPDATE SKIP LOCKED`. It creates a run through the same ingestion service, advances the next occurrence from the current time so missed intervals coalesce, and records safe skipped/failed outcomes without disabling the schedule. A run committed before an interrupted schedule checkpoint is found by schedule/due identity and adopted. After run creation commits, the dispatcher reacquires the schedule lock and verifies the claim token/status before writing; a concurrent pause or cadence edit therefore remains authoritative.

Schedules start paused and never alter their saved pipeline version. Immediate schedule execution uses the same destination lock but leaves the automatic due time unchanged. Credentialed versions retain the local Host/Origin and encrypted-vault gates. There is intentionally no delete or retention endpoint: pausing prevents future automatic runs while schedules, immutable revisions, indexes and historical evidence remain available.

## Robust ingestion processing boundary (Phase 0, 2026-09-24)

Schema-v1 and schema-v2 ingestion executions are intentionally separate discriminated
contracts. Historical v1 JSON remains readable and executable through the unchanged
parser/character-window path. New drafts use v2. The editor never rewrites a selected
v1 version: **Upgrade as draft** clones it, maps explicit v2 runtime/profile versions
and leaves the immutable source version untouched.

`app.ingestion_content` is the application-owned current-behavior boundary. It owns
native TXT/PDF extraction, deterministic cleaning, character-window chunking, typed
stage errors and canonical processing identities. Connector modules still own safe
fetching and provider-native extraction/provenance, but Website, S3, Notion and
Confluence no longer carry independent general-purpose cleaners or window loops. The
cleaner takes an explicit semantic version: legacy mode preserves the historical final
collapse-and-trim behavior, while v2 standard mode makes `normalize_whitespace=false`
preserve source whitespace except for configured literal removal.

Migration `0020` adds nullable canonical processing configuration, its SHA-256 and a
deterministic output hash to `processing_runs`. Null is meaningful legacy lineage, not
an inferred version. Existing Files v2 reuses any successful run with the exact
configuration hash; changes to Extract, Clean or Chunk create a new immutable run.
Runtime extractor/cleaner/chunker versions are exposed from persisted configuration in
run items. Remote synthetic processing runs store the same identity that their source
revision already uses. No canonical block IR, derivation table, OCR, layout engine,
semantic chunker, near-duplicate or sensitive-data policy is introduced at this phase.

## Canonical content derivations and lineage (Phase 1, 2026-09-24)

`app.ingestion_content.contracts` is the strict application-owned representation for
extracted and cleaned content. It is independent of SQLAlchemy and connector SDKs.
Every block has a deterministic ID, contiguous reading-order ordinal, explicit bounded
type, text, optional page/normalized geometry/heading path, bounded JSON attributes and
a discriminated artifact/provider/derived source span. Unclassified native content is
retained as `unknown`; the system does not invent geometry or semantic structure.

Migration `0021` adds immutable `content_derivations`, `content_blocks` and
`chunk_block_spans`. Derivations are unique by processing run and kind and are bound to
the same project-owned document and processing run with composite foreign keys. Span
rows reference an existing chunk, an existing block and the `cleaned` derivation from
that exact run. The processing worker and shared remote-artifact boundary insert chunks,
both derivations, blocks and spans in one caller-owned transaction before marking the
run successful; failed, cancelled, duplicate or fenced attempts cannot publish partial
canonical records.

Schema-v2 Existing Files, Website, S3, Notion and Confluence adapters all construct the
same IR before shared deterministic cleaning/chunking. The character-window algorithm
continues to produce Phase 0 evidence text and offsets. Per-block native/provider paths
map a chunk to one exact local block range; Website retains its historical joined-block
windowing and records every intersecting block range, excluding synthetic separators
from source coverage. Schema-v1 execution is not backfilled or inferred.

Project-scoped API reads expose the two derivations, primary-key-paginated blocks and
bounded spans. The run inspector is read-only and labels legacy runs without canonical
records as unavailable. This phase intentionally does not add OCR, layout engines,
table reconstruction, quality policy, semantic chunking, near-duplicate logic or
sensitive-data transforms.

## Layout-aware PDF extraction and OCR (robust ingestion Phase 2, 2026-09-24)

Schema-v2 extraction uses an application-owned adapter contract. `pypdf` remains the
strict native-text and page-count adapter; PyMuPDF 1.28.2 supplies normalized layout
blocks, reading order, safe thumbnails and bounded table rows; a local Tesseract 5.5.0
subprocess supplies OCR TSV and engine confidence. The container installs only the
pinned English and orientation language data. OCR has no network path or runtime model
download, and subprocess environment, time, output, page and pixel limits are explicit.

Docling 2.130.0 was evaluated before engine selection. Its current standard installation
requires a newer settings stack plus Torch, Transformers and model assets. That footprint
does not fit the existing 768 MiB isolated worker or deterministic offline packaging
gate, so it is not selected or exposed. This is a measured packaging decision, not a
claim that the smaller adapter is generally more accurate.

Auto extraction records its page rule: fewer than 20 native characters selects OCR
when automatic OCR is enabled; otherwise a detected table, separated columns or a
material native/layout character-count delta selects layout output; uncomplicated pages
retain native text. Explicit Native and Layout-aware profiles bypass the corresponding
Auto choice. Every page records Native, Layout or OCR origin, fallback reason, size,
rotation and available OCR confidence. Confidence remains an OCR-engine observation,
not factual confidence.

The versioned quality policy maps measured empty pages, character anomalies, ambiguous
reading order, malformed/truncated tables and OCR confidence to pass, warn, fail or
exclude before cleaning, chunking, embedding or publication. Failed/cancelled/fenced
attempts commit neither chunks nor derivations and cannot advance a knowledge set's
current-ready pointer. Schema-v1 and `native-text-v1` schema-v2 executions retain their
historical parser behavior and data.

Extract configuration versions are frozen once released (decision D1 of
[the Extract node improvement plan](extract-node-improvement-plan.md), 2026-10-06).
`layout-ocr-v1` output is pinned by digests in `backend/tests/extract_corpus.py`; fixes
ship in `layout-ocr-v2`, which has its own extractor version and therefore its own
processing identity. New drafts default to v2 and saved v1 nodes upgrade only through
an explicit draft change. The first v2 change keeps the computed column reading order
and places each table after the last block above it in the same column band, where v1
re-sorted every block by position and interleaved columns. The trade-off is that the
extractor keeps small, version-gated branches instead of one current behavior.

v2 also keeps whole PDF tables (Slice 2). A table becomes consecutive `table` blocks,
each repeating the header row and recording `table_id`, `group_index`, `group_count`,
`row_start` and `row_end`, sized to the 16 KiB block-attribute limit; each block's box
is the union of its PyMuPDF row bands when available. Section-aware chunking already
splits a large table block by rows and repeats its header, so the extractor does not
size groups to chunk settings. Splitting is not a quality finding; only tables beyond
2,000 rows, 50 columns or 1,000 characters per cell are cut and counted as malformed.

v2 PDF structure (Slice 3): layout blocks are classified per page, then a document-wide
pass picks one title (the first page-1 heading when it is larger than every other
heading), ranks distinct heading font sizes into at most six levels and gives every
following block the open heading path, across pages. The title is not part of paths,
matching how a Markdown `# Title` followed directly by `## Section` already chunks.
Auto uses layout blocks unless they hold under 75% of the page's native characters; the
v2 column test needs narrow blocks on both halves of the page so headings and indented
list items do not read as columns. The trade-off is that a body-size, fully bold short
line is treated as a heading even when an author meant emphasis.

The inspector fetches project-scoped, annotation-free PNG thumbnails from the immutable
raw artifact and overlays normalized block geometry in the browser. Structured table
rows and their deterministic Markdown/plain-text evidence are both bounded. See the
[reviewed corpus baseline](ingestion-corpus-baseline.md) for the exact release sample,
thresholds and limitations.

## Deterministic structure-aware cleaning (robust ingestion Phase 3, 2026-09-24)

Schema-v2 cleaning now selects either the compatibility `standard-v1` implementation or
the separately versioned `structure-aware-v1` profile. Structure-aware configuration is
a strict ordered discriminated union. Transform IDs, types, settings, enabled state and
order participate in the canonical processing hash; invalid duplicate or incompatible
orders are rejected before save. The selected cleaner runtime version is derived from
that profile and is persisted with the processing run rather than inferred from current
defaults. Schema-v1 and existing standard-v1 hashes and output remain unchanged.

The application-owned cleaner operates only on canonical blocks. It implements bounded
Unicode/control cleanup, paragraph-only PDF reflow and dehyphenation, positional repeated
margin detection, empty/literal removal, safe Website selector tokens, semantic/main and
cross-page chrome removal, protected structure retention and final useful-content bounds.
Website HTML is parsed into inert semantic blocks; scripts, styles and arbitrary CSS are
neither executed nor accepted. Existing Files and every remote connector invoke the same
engine after connector-specific extraction.

The extracted derivation is immutable. Each enabled transform produces bounded block
change records, safe aggregate metrics and duration, while rewritten cleaned blocks name
their parent extracted IDs. Transform audits remain on the existing cleaned-derivation
JSON column, so Phase 3 requires no schema migration. Project-scoped cleaning-diff reads
join immutable extracted and cleaned blocks, reconstruct removed/rewritten before and
after text on demand and paginate the response; they do not persist a second unbounded
copy of source text. The run inspector exposes the exact engine, transform counts and
ordered attribution. See the
[reviewed cleaning baseline](cleaning-corpus-baseline.md) for measured precision, recall
and corpus limits.

## Structure-aware chunking and derivation reuse (robust ingestion Phase 4, 2026-09-24)

Schema-v2 ingestion selects one versioned chunking profile. Historical
`character-window-v1` execution remains unchanged. `section-token-v1` and
`parent-child-v1` use the registered `utf8-byte-v1` tokenizer, whose identity is saved
with the processing configuration so a future tokenizer change cannot silently alter an
old pipeline version. Target sizes guide grouping, while validated hard maxima are
authoritative.

The chunker consumes immutable cleaned blocks rather than reparsing concatenated text.
Section paths, block types and exact source spans survive grouping and deterministic
paragraph/sentence/token splitting. Faithful evidence is stored in `chunks.text`;
optional heading enrichment is stored in `chunks.embedding_text`. Provider input uses
the latter, while retrieval and generation evidence use the former. Findings make any
required hard split of protected content explicit.

Parent/child processing persists a parent row and its retrieval-child rows under the
same project, document and processing-run ownership constraints. Index membership
contains children only. Retrieval matches a child vector but outer-joins its immutable
parent and supplies the parent text as evidence; matched-child identity and text remain
in the retrieval snapshot. Legacy rows without a parent continue to supply themselves.

`processing_derivations` maps a processing run to the exact immutable extracted and
cleaned derivations it consumes. This separates extraction/cleaning identity from the
full processing hash: a chunk-only variant can reuse compatible derivations without
mutating their source run. A source-snapshot variant resolves the exact stored revision
membership and never constructs the connector, so no source request occurs. New chunks,
embeddings and index membership are still written under a new immutable run/index, and
atomic publication advances the current-ready pointer only after all required children
are embedded.

## Quality, duplicate and language policy (robust ingestion Phases 5–6)

An asynchronous preview saves the exact unsaved schema-v2 execution, uses the same
extract/clean/chunk engine and persists bounded stage representations, findings,
decisions, timing and safe cost basis. It never embeds, creates an index or moves a ready
pointer. Quality aggregation retains pass, warn, exclude and fail denominators. Preview
expiry/cancellation is fenced, and a retry creates a new preview identity.

Duplicate policy compares project/run-scoped raw and cleaned hashes, normalized sections
and optional bounded SimHash. Canonical selection is deterministic and persists both the
retained and excluded identities; no source revision is deleted. Language policy records
the deterministic detector version, document/page confidence, allowlist and mixed-language
decision without translating evidence. Duplicate and language decisions remain attached
to immutable preview/run items.

## Sensitive data, protected artifacts and released formats (robust ingestion Phase 7)

Migration `0025` adds OIDC identities/project memberships, sensitive-access audits,
artifact envelope/retention state and protected derivation/preview payloads. Local mode
maps loopback requests to one deterministic owner. Shared mode verifies OIDC tokens and
enforces owner/admin/editor/viewer membership on every project route; viewer writes are
denied, and only owner/admin may read protected raw/extracted/diff/thumbnail/finding
locations. Granted and denied protected accesses store identity/action/resource metadata,
never source text or detected values.

Each new protected artifact uses a random AES-256-GCM data key and content nonce. The
data key is envelope-wrapped by a versioned local development key, AWS KMS symmetric key
with an encryption context, or Vault Transit AEAD key with associated data. Shared mode
rejects the local keyring and incomplete external configuration. Project/document/purpose
AAD prevents envelope or protected-block copying. Rewrap changes only the data-key
envelope; fenced retention cleanup removes expired ciphertext and clears its envelope,
while redacted derivations/index/query/experiment history remains. Legacy plaintext is
explicit and is never silently treated as protected.

The saved cleaning policy runs deterministic bounded detectors for email, phone, IP,
checksum-valid payment cards, supported government IDs and recognizable secrets. Each
class redacts with an irreversible placeholder or drops the document before chunking and
provider calls. Persistence contains class/detector/count and bounded locations only—no
original, reversible map or guessable hash. This reduces exposure but cannot guarantee
that all sensitive data is detected.

Released Markdown/HTML, DOCX, PPTX, CSV/TSV and XLSX adapters validate bytes/container
members, archive size/ratio/path/encryption bounds and inert XML/text structure before
mapping to the canonical IR. HTML scripts/styles are ignored, Office macros and legacy
binary formats are rejected, and spreadsheet formulas are retained only as text. No
macro, script, formula, shell content or document action is executed. Apache Tika and
other formats remain unadvertised because no evaluated Java parser boundary is shipped.
The [release baseline](robust-ingestion-release-baseline.md) records the exact measured
corpus and limitations.

## Frontend organization

Ingestion runs also persist one `ingestion_run_nodes` row for every node in the
immutable saved execution graph. Workers move those rows through queued, running,
succeeded, failed and cancelled states at the actual connector, extraction,
cleaning, chunking, embedding and atomic-publication boundaries. This table is
separate from the coarse run stage so a checkpoint can commit while an artifact
transaction holds the parent run lock. Execution tokens still fence worker
transitions, and terminal run handling resolves the active and remaining node
states in the same transaction. The run read contract returns the ordered node
states; the React Flow editor renders them by immutable node ID and only falls
back to legacy stage projection for historical rows created before migration
`0019`. Multiple document workers can reach the shared Extract, Clean and Chunk
checkpoints concurrently, so a transition locks the run's ordered node set and
updates it at `READ COMMITTED`; checkpoints therefore move forward monotonically
without a repeatable-read serialization failure.

The frontend separates workspace navigation, route rendering, and project-loading lifecycle. Document/chunk inspectors and experiment comparison/configuration components belong to their respective features. Unit/component tests live in `frontend/tests/`, mirroring `src/`; browser journeys remain in `frontend/e2e/`. Application imports cannot reference test code or testing libraries (enforced by ESLint).

The application now has one authored stylesheet, `src/app/styles.css`, with root shadcn semantic tokens mapped through Tailwind `@theme inline`. Tailwind and its Vite plugin are pinned to 4.3.3. The official shadcn CLI installed Button, Input, Label, Textarea, Native Select, Checkbox, Table, Badge, Tabs, Separator, Alert, Skeleton, Accordion and Progress using the existing Radix/new-york convention. Local variant changes preserve the compact dark workspace. Required React Flow package CSS is imported once; it is not an authored feature stylesheet.

Feature API modules expose descriptive operations; shared transport handles JSON, server validation errors, cancellation and a timeout covering response reads. Domain models have no HTTP dependency. Projects own their API; generic pagination no longer depends on documents or pipelines. Pipeline template construction is shared between the canvas and Playground, and editable graphs clone saved execution data before legacy conversion. Query polling permits one request at a time and ignores stale responses. Project navigation no longer refetches the full project list for each page.

Pipeline and Playground controller hooks coordinate their feature lifecycles while small page components compose intent-based feature sections. Node settings, run history, document/chunk inspection and experiment comparison have distinct component boundaries. Shared product components live in `src/components`; feature-only sections live under their feature's `components` directory. Necessary responsive layout and vendor rules remain in the central stylesheet, including unlayered rules whose precedence requires computed-style checks. [Frontend standards](frontend-standards.md) document the maintained boundaries and checks.

Long-running frontend reads use one request at a time and bind responses to the selected immutable run ID. Ingestion execution polling owns its timer for the lifetime of that run, retries transient safe read failures, ignores late results after navigation or selection changes, and refreshes terminal items and schedule metadata before publishing terminal state for the still-selected pipeline version. This ordering prevents the terminal-state render from cleaning up its own in-flight detail reads. Experiment comparison polling likewise retries transient reads until PostgreSQL reports a terminal state. These are presentation recovery rules only: PostgreSQL job state and worker fencing remain authoritative.

## Reusable Website source snapshots

Website collection and index construction have separate immutable boundaries. A successful refresh atomically publishes one project-scoped source snapshot with exact ordered source-revision membership; failed or cancelled collection never exposes partial membership as ready. Every Website-derived index stores its snapshot ID, while its ingestion run retains the exact saved pipeline version, effective processing/embedding configuration, destination, counters, and costs. A snapshot build validates the saved Website source configuration against the snapshot hash, reads only that membership, and never constructs the Website adapter. Compatible processing and embeddings may be reused; configuration changes create new work. Current-ready index pointers advance only after complete publication.

Snapshot and index APIs are project-scoped and paginated. Legacy index lineage is populated only where the historical run proves equivalence; otherwise clients display lineage as unavailable. Answer pipelines continue binding exact index UUIDs. Experiment submission copies the selected index and source-snapshot lineage into its immutable candidate snapshot, so later refreshes cannot change a comparison. Same-snapshot status is descriptive and does not block deliberate cross-snapshot comparisons.
## Clerk organization authorization (2026-09-26)

Clerk is an opt-in development authentication mode alongside the existing loopback-only local owner and generic OIDC modes. The React shell loads `@clerk/react` only when the ignored Vite publishable key is configured. Clerk supplies sign-in, sign-up, sign-out, organization creation/switching and its organization profile for invitations. Pending session tasks, including required organization setup after sign-up, render before the project workspace. The application API client requests a fresh session token for every JSON request and CSV download. No browser-controlled organization or project ID is accepted as authorization evidence.

The FastAPI Clerk adapter verifies an RS256 session token against the configured instance JWKS and exact issuer, checks expiry/not-before/issued-at, requires a session/user subject, validates the frontend `azp` against the authorized origins when Clerk includes it, and rejects pending organization-selection sessions. Clerk documents that `azp` can be omitted when the original Frontend API request has no Origin; an absent claim is allowed only within this loopback-only development mode, while any supplied claim must match the configured origin. It then checks the active organization's membership through Clerk's Backend API on every request, so removal takes effect without waiting for a JWT refresh. Backend API failure fails closed as 503. Initial identity creation retries PostgreSQL serialization conflicts a bounded number of times, which matters when Clerk completes organization setup concurrently with the first API read. A project role is read from PostgreSQL only when its `organization_id` equals the verified active organization. The existing owner/admin/editor/viewer access rules and owner/admin sensitive-read checks remain authoritative across the project-scoped routers. The Clerk development mode is loopback-only while raw artifacts lack a shared KMS/Vault boundary; public shared deployment remains gated separately.

Migration 0029 adds nullable `projects.organization_id`. A pre-existing project is backfilled only when `LEGACY_PROJECT_ORG_ID` is explicitly supplied; otherwise migration fails before changing data. Downgrading removes this association, so the same explicit owner mapping is required again before re-upgrade. New Clerk projects always store the verified active organization and grant their creator the project owner role. Local-owner projects may remain null to preserve local development. Organization admins can explicitly claim organization-owned legacy projects with no project membership. Project owners/admins can grant project roles only to current members of that same organization; admins cannot grant owner/admin. A Clerk invitation alone grants organization membership, not project access. Project-scoped CSV responses use the same bearer authorization as JSON.
## Deployable answer endpoint (local server-to-server implementation)

Migrations 0030–0034 add organization-owned deployments, immutable release/event rows,
versioned hashed keys, durable answer runs and usage buckets, per-deployment ceilings,
and 24-hour management command receipts. Existing pipeline/index/query/experiment rows
are not rewritten. Composite foreign keys bind deployment, release, project, pipeline,
index, key and run ownership. A database trigger rejects release/event changes. The
active release pointer is a deferred composite foreign key to the same deployment.

Owner/admin may create and change a deployment; editor/viewer can read safe release and
run summaries. Every release snapshots the validated answer execution/hash and exact
ready index ID/embedding configuration/hash. Its retriever must name that index. Saving
a newer pipeline version or publishing a new ready index cannot move an active release.
Promotion, rollback, pause, resume and archival use a revision precondition and commit
an event with the state change. Archival is terminal, revokes keys and cancels or
requests cancellation of accepted work. The development Clerk mode remains loopback
only; local-owner mode requires a separate switch before it can issue customer keys.

Customer keys have 256 random bits, a public lookup prefix and a versioned HMAC-SHA-256
hash with a server-only pepper. The plaintext is returned once on issuance/rotation.
Rotation preserves a credential-family ID; rate and idempotency accounting use that
family so overlap cannot reset limits. Management command receipts store a hash of an
optional `Idempotency-Key`, the request hash and only safe metadata. Replaying key
issuance returns `key_secret_already_issued`, never the secret.

Customer admission uses a read-committed PostgreSQL transaction and advisory lock to
validate the key, active release, client-family idempotency, rate/queue ceilings and
conservative organization and deployment daily/monthly reservations together. A row's
unique `(deployment_id, client_id, idempotency_key)` constraint is the final duplicate
barrier. Approved price ceilings are operator configured; an unpriced model fails
closed. Since the embedding adapter does not report total query cost, a successful run
still retains its full worst-case reservation. A pre-provider cancellation releases it;
an ambiguous paid call retains it until reconciliation. This is intentionally
conservative and can exhaust admission capacity before actual billing does.

The dispatcher relays durable queued IDs to a dedicated Celery queue. The worker
claims with a fenced token, checkpoints before each possibly paid provider call,
executes the saved release and exact index, and persists bounded evidence, validated
citation excerpts, usage and separate queue/execution timing. It never calls the
playground's FastAPI `BackgroundTasks` path. Redis loss leaves queued rows in
PostgreSQL; duplicate deliveries cannot repeat a terminal run. The dispatcher requeues
only stale pre-provider attempts, marks ambiguous paid attempts unknown, redacts
customer question/answer/evidence after 30 days by default, and prunes expired
command receipts. Release/key/audit/usage metadata currently remains retained; no
automatic historical-data deletion is performed.

The management React feature reads backend role permissions and exposes immutable
release history, exact version/index IDs, publication and traffic controls, limits,
one-time key copy, and operational run summaries. The customer API refuses browser
Origin requests and stays bound to loopback in Compose. A separate loopback metrics
endpoint reports bounded-label queue, stale, unknown-outcome and reserved-spend gauges.
Internet exposure remains subject to independent production Clerk, KMS/Vault,
authenticated TLS ingress and AWS infrastructure gates.

## Private website widget boundary (2026-09-28)

The [website chatbot widget plan](website-chatbot-widget-plan.md) is implemented locally as a separate
lightweight `widget/` app, a versioned public loader and an isolated iframe. Its
public deployment ID selects one active answer deployment but grants no question
access. A customer's authenticated website backend keeps the deployment key and
exchanges it for a five-minute opaque token bound to one deployment, site origin
and pseudonymous visitor session. The loader obtains the token from a first-party
customer endpoint and passes it to the iframe via an exact-origin, nonce-checked
message; the browser retains it only in memory. Browser routes reuse
the deployed answer job, status and citation serializers while adding per-visitor
run ownership. Exact allowed origins, CORS and frame CSP narrow exposure but do
not authenticate a visitor. Migration 0035 adds exact-origin widget settings,
hashed token and visitor-binding records, and run caller ownership. Token exchange
requires the server key without browser Origin; widget question routes require the
short-lived token and exact iframe Origin. The existing key routes still reject Origin.
The same durable admission and worker pin the release and index and serialize results.
The local feature is not approval for public ingress.

The embedded iframe uses a neutral, customer-facing chat surface independent of the dark
Studio workspace. It keeps only the current browser session's visible turns in memory;
each question is a separate deployed-answer run with no conversation context. Citation
markers link to the bounded evidence already returned by the shared result serializer.
The loader sends the customer page's viewport mode through the checked handshake and
on resize, because the narrow iframe viewport alone cannot distinguish a desktop
panel from a mobile page. Desktop uses a nonmodal region; mobile uses a full-screen
dialog. If framing never completes, the loader shows a generic setup message on the
customer page without exposing a token or deployment key.

## Public visitor widget boundary (2026-09-29)

Migration 0036 adds an opt-in `widget_public_enabled` deployment flag and one internal
`public_widget` accounting key per deployment. Its secret is never issued; customer key
listing, verification, rotation and revocation exclude it. The iframe verifies its
parent origin against saved deployment origins, then obtains a five-minute token from
the Studio browser route. The loader needs only a deployment ID in public mode. A
random per-frame visitor ID scopes run reads; the token and ID remain in frame memory.
Public token issuance has a deployment-wide cap, while existing visitor, key, deployment,
organization, queue and spending admission still applies to questions. Disabling the
public flag invalidates issued public tokens on their next request. Exact origins and
CORS narrow browser embedding; nonbrowser clients can spoof Origin, so the durable
rate and budget ceilings are the abuse boundary. This remains loopback-only.

## Ingestion throughput and fairness

Decided 2026-10-02 after a scaling review. PostgreSQL remains the job store and every worker step keeps its execution token, so none of these changes weakens fencing or publication.

- **Worker hand-off.** An embedding task embeds one bounded batch (16 chunks), then sends the next batch itself instead of waiting for the next five-second dispatcher pass. It records `dispatched_at` before sending; if the broker rejects the send, it clears `dispatched_at` so the dispatcher sends it on its next pass. Processing and ingestion coordination schedule transient retries the same way, as delayed messages. The dispatcher's role for these jobs is first delivery and recovery.
- **Throttling is waiting, not failure.** `EmbeddingError.throttled` marks the local Redis request budget and OpenRouter 429 responses. A throttled embedding batch is requeued with a 20-second delay without incrementing `failures`, so many indexes sharing one key wait in line instead of exhausting their three-failure budget. Other transient failures still consume it (retry after 15 s × failures).
- **Two worker pools.** Celery routes `preview.sources`, `experiments.step` and remote-source (website, S3, Notion, Confluence) ingestion coordination to the `long` queue, served by the `long-worker` service. Parsing, embedding and Existing Files coordination stay on the default `celery` queue served by `worker`. A one-hour crawl therefore cannot occupy every worker that short steps need. Deployed answers keep their own queue.
- **Per-organization cap.** For processing runs, index builds, ingestion runs and source previews, the dispatcher counts each organization's running or recently sent jobs and sends at most `DISPATCH_ORG_CONCURRENCY` (default 4) per job type, taking each organization's oldest job in turn. Local mode (no organization) is one group. With a single dispatcher the cap is exact; two concurrent dispatchers could briefly exceed it.
- **Child memory limit.** A forked worker child already reports about 260 MB of shared imports, so the previous 256 MB `worker_max_memory_per_child` replaced the child after every task (0.5–6 s each). The limit is now 400 MB; the Compose memory limit remains the hard bound.

Measured with `tests/test_indexing_throughput.py` (opt-in, deterministic provider double, includes database time and the five-second dispatcher interval): 2,000 chunks went from 125 dispatcher passes and about 185 chunks/minute to one pass and about 8,600 chunks/minute; database time per batch went from about 176 ms to 72 ms. In the isolated Celery/Redis e2e stack, 1,000 cached chunks indexed at about 3,160 chunks/minute, and 1,500 new chunks completed at the default 60 requests/minute budget (about 1,000 chunks/minute) with three throttled waits and zero failures. Real throughput is bounded by `EMBEDDING_REQUESTS_PER_MINUTE` × batch size and provider latency.

Not addressed: uploaded files stay on the shared `document_data` volume, so workers must run on the API host until storage moves to an object store. Exact vector search has no approximate index (the dimensionless `vector` column would need one per dimension). No sustained multi-user load test has been run.

## Ingestion recovery, cancellation and publication fencing

Decided 2026-10-02 after an ingestion architecture review.

- **Recovery is measured from the last checkpoint.** The dispatcher recovers a `running` ingestion run when `updated_at` is older than 180 seconds. Every claim and committed checkpoint refreshes `updated_at`; `started_at` remains the run's first start for display. Previously recovery was timed from first start, so any long Existing Files run could lose a coordinator pass and every S3, Notion or Confluence discovery longer than three minutes was recovered while still fetching, repeating its provider calls and failing after three recoveries.
- **Remote discovery has a longer window.** Website, S3, Notion and Confluence runs in the `discovering` stage get 3,700 seconds, longer than the 3,670-second hard limit of `ingestion.coordinate`, so a live discovery task is never recovered while it can still commit. Trade-off: if the worker really dies during discovery, recovery takes up to about an hour. A per-page heartbeat from connectors would let this window shrink; it is not implemented.
- **Publication is fenced on the parent run.** The indexing worker's final batch locks the parent ingestion run before the index row, the same order cancellation and coordination use. If the run is no longer queued or running, the index becomes `cancelled` and the knowledge set's ready pointer is unchanged. Cancellation (`POST .../ingestion-runs/{id}/cancel`) uses a read-committed session, locks the run, and returns 409 when the run's index already succeeded instead of reporting an unpublished cancellation. Remaining gap: if the coordinator's final pass fails after the index is published, the run can still end `failed` with a live index.
- **Cancellation preserves item evidence.** Only `processing`/`ready` run items (and `ready` website items) become `cancelled`; `failed`, `excluded` and `succeeded` outcomes are kept.
- **Duplicate classification runs once.** Existing Files duplicate decisions are computed when the run's index is created, not on every coordinator poll while the index embeds.
- **Embedding configuration must match the run.** Index creation for an ingestion run compares the current embedding configuration with the one recorded in the run snapshot and fails the run (409 message) if it changed, so a run never reports a configuration its index did not use.
- **Website fetch timeout covers the whole response.** `request_timeout_seconds` now bounds the complete request, including the body read, so a server that trickles bytes cannot hold a worker beyond it. Server-owned Website limits superseded the saved `concurrency` field; see the next section.

## Website scope versus server-owned fetch limits

Decided 2026-10-02 ([Website source node plan](ingestion/nodes/website-source-node-plan.md), Stage A).

- **The node holds scope; the server holds limits.** A Website node saves discovery mode, URL(s), maximum pages (1–1000), crawl depth (0–10), include/exclude path prefixes, allowed origins and crawl speed (0.1–5 requests per second). Request timeout, per-page and total byte budgets, redirect limit, user agent and robots.txt handling are `WEBSITE_*` server settings. The strict schema rejects the removed fields, so a saved node cannot weaken them. Settings that do not apply to the selected mode stay saved and are ignored by the connector.
- **One resolver.** `resolve_website_fetch_policy` (in `app.connectors.website`) is the only code that combines node scope with server settings. It derives the total byte budget as `min(pages × per-page limit, cap)` and the deadline as `(pages + robots/sitemap requests) / speed × 1.5 + request timeout`, clamped to `WEBSITE_DEADLINE_MIN_SECONDS`–`WEBSITE_DEADLINE_MAX_SECONDS`. A scope that cannot finish within the maximum at the chosen speed is rejected when saved, previewed or run (422), instead of failing mid-crawl. The maximum is capped at 3,600 seconds because the preview and coordination task time limits and the dispatcher's 3,700-second discovery window assume discovery ends by then. Previously one user-set "preview deadline" also bounded runs, so a valid 1,000-page configuration could not finish, and raising pages without raising the byte budget failed mid-run.
- **The effective policy is recorded.** Run creation stores `snapshot["fetch_policies"]` keyed by source node ID; the worker passes exactly that policy to the connector on every delivery, retry and recovery and never re-resolves it, so a server-setting change does not alter a started run. Previews store the same object in `source_previews.fetch_policies` (migration `0040`). Both API reads return it and the editor shows it as "Fetch limits used".
- **Fixed user agent, robots.txt always respected.** The connector uses the server user agent for every request and for robots.txt evaluation, so no node setting can change what robots.txt permits.
- **`concurrency` removed.** It was validated and saved but never read. Bounded parallel fetching replaced it in Stage C (`WEBSITE_FETCH_CONCURRENCY`, below).
- **Sitemaps, retries and JavaScript shells (Stage B).** A `<sitemapindex>` is followed one level deep to at most 50 nested sitemaps, each fetched from an allowed origin within the per-page byte limit and counted against the total budget; each nested sitemap is recorded with the distinct status `sitemap` (migration `0041`), which counts with excluded items. Gzip sitemaps (`.gz`, a gzip content type, or `Content-Encoding: gzip`, which only sitemap requests accept) are decompressed up to the per-page limit before the existing DOCTYPE/ENTITY rejection. A sitemap `<lastmod>` no later than the stored revision's fetch time reuses that revision without a request. HTTP 429/502/503/504 and request timeouts or connection failures are retried up to `WEBSITE_RETRY_ATTEMPTS` (3) with exponential backoff and jitter, honoring `Retry-After` up to `WEBSITE_RETRY_MAX_DELAY_SECONDS` and never past the deadline; robots.txt retries any 5xx and, if it still fails, fails that origin's pages without more requests. robots.txt `Crawl-delay` can only slow the crawl. Every preview and run item records its request `attempts`. A failure that ends sitemap discovery is raised as not retryable, so worker retries do not repeat the connector's. Pages with under 200 characters of visible text get a `likely_client_rendered` warning (preview finding, run item `warnings`); no headless browser is used. Retry settings are part of the recorded policy (`policy_version` 2); a version 1 policy reads with no retries, so a run started before the change keeps its behavior.
- **Page-level crawl checkpoints (Stage C).** A Website refresh crawls into `website_crawl_frontier` (migration `0042`): one row per discovered URL with its depth, status (`queued`, `fetched`, `excluded`, `failed`, `duplicate`, `sitemap`), attempts and reason. Each page's decision, its encrypted raw body (the same envelope as documents) and the links it adds commit in one transaction after the run row is locked and the execution token checked, so a stale or duplicate worker cannot write. `ingestion_runs.crawl_state` keeps per-source transferred bytes and elapsed time, so the byte budget and deadline continue across recovery instead of resetting. A recovered run reloads the queued rows and refetches only pages whose fetch had not committed. Processing then turns each fetched page into a source revision in its own fenced commit and deletes the crawl copy; repeated-site-chrome fingerprints are computed once over all fetched pages before processing and recorded, because cleaning one page depends on every page. The run assembles items and the index from the frontier as before; previews use the same discovery code with an in-memory store. `discovered_count` and `processed_count` update per page, and the run strip shows them while discovering. The dispatcher deletes stored crawl bodies of runs that ended before processing them.
- **Bounded parallel fetching.** `WEBSITE_FETCH_CONCURRENCY` (default 4, maximum 8) fetch threads per source, recorded in the policy (`policy_version` 3; older policies fetch one page at a time). A shared per-origin limiter spaces request starts by the crawl speed (or a slower `Crawl-delay`), so concurrency never raises the rate to a site. The byte budget is reserved atomically per request. Threads only fetch and parse; scope decisions, claiming and every database write stay on the coordinating thread, and only the worker holding the run's execution token can commit, so frontier claiming needs no row-level `SKIP LOCKED`. Trade-off: the stale-discovery recovery window stays at 3,700 seconds; per-page commits refresh `updated_at`, but a large `Crawl-delay` could still exceed a shorter window.
- **Duplicate content (Stage D).** `utm_*`, `ref`, `fbclid` and `gclid` query parameters are removed before URLs are compared; the original URL is kept in the item reason and as the preview item's external ID. A `<link rel="canonical">` is followed only when it points inside the allowed origins and path scope: the page is recorded as a duplicate that names its canonical URL and the canonical URL is queued; otherwise it is ignored and the reason says why. A fetched page whose normalized visible text (scripts and styles removed, whitespace collapsed) hashes the same as an included page in the same run is recorded as `duplicate` naming the retained URL, without a revision. Pages with under 200 characters of text are not compared, so near-empty pages are not merged. The existing processed-text duplicate policy still applies afterwards. The JavaScript-shell warning now also requires a `<script>` element, after a live preview flagged the short static page at example.com.

- **Discovery limits and socket reads (fixes from manual testing, 2026-10-03).** Discovery records out-of-scope links (other origins, paths outside the filters, too deep) only until `max_pages × 4` URLs are recorded and then drops them silently; in-scope URLs may use the same number again, so a total of at most `max_pages × 8` (8,000) URLs per source. Previously one shared limit let navigation links to other sites and sections fill it before the pages being crawled were reached. Each page's parser reads up to 4,000 links. A `rel="canonical"` target is admitted before the page's links, so it keeps the declaring page's depth. `StdlibTransport` stops reading when the response has closed itself: with `Connection: close`, `http.client` closes the socket once `Content-Length` bytes arrive, and touching it again raised `Bad file descriptor`, which failed every page on some servers (for example docs.python.org behind Fastly).
- **Review fixes (2026-10-03).** Non-HTTP links (`mailto:`, `tel:`, `javascript:`) are ignored instead of failing the run, and an invalid or over-long link (over 2,000 bytes) is excluded once with a reason; frontier keys never exceed that bound, inside PostgreSQL's btree entry limit. The byte budget counts bytes atomically as each response arrives instead of reserving the per-page maximum for every parallel request, which refused pages long before the budget was used. A `rel="canonical"` naming the URL requested before a redirect is the page itself; a page becomes a duplicate only while its canonical target is queued or indexed, so two pages naming each other index one of them; canonical targets bypass the discovery limits and are fetched first. Every redirect hop is rate-limited per origin and checked against that origin's robots.txt. The limiter never sleeps past the deadline, and queued pages fail at once when it passes. A date-only sitemap `<lastmod>` means the end of that day. `strip_tracking` keeps other parameters byte for byte. Path filters apply only to crawl and sitemap modes. A response shorter than its `Content-Length` is a retryable failure. Results are decided in queue order, so the kept copy of identical pages is deterministic. `Retry-After` is waited up to `WEBSITE_RETRY_MAX_DELAY_SECONDS`. Unchanged pages (304 or sitemap `lastmod`) are not stored again; processing reads their prior revision. Page files of a failed commit are deleted, and released bodies are deleted in two phases so a crash leaves a row the dispatcher sweep still finds. A page whose canonical target is still queued is marked duplicate but its result is held; the target is fetched next, and if it ends failed or excluded the page is re-recorded with its body (`commit(..., reinstate=True)`), so a canonical pointing at a broken page never loses content. An unchanged page whose final URL differs from the queued one (a new redirect) is stored, because its prior is keyed by the queued URL. A relative sitemap `<loc>` is excluded once with a reason. Trade-offs: `Crawl-delay` is honored without a cap (the deadline bounds it); a recovered run reloads its queue in discovery order, so a canonical target loses its priority; the byte limit bounds counted bytes, and bytes of failed or discarded responses are not counted, so real transfer can exceed it by up to concurrency × per-page limit; no index was added for the body sweep, whose cost grows only with unpruned frontier rows.

## Multi-source ingestion pipelines

Decided 2026-10-05 ([multi-source ingestion plan](multi-source-ingestion-plan.md)).

- **Layout is explicit.** A pipeline will state `index_layout` (`merged` or `per_source`) instead of the backend inferring intent from graph wiring. Merged pipelines share one processing chain; per-source pipelines get one chain, knowledge set and child run per source, grouped by a run group rather than a `parent_run_id`, because a run's constraints assume it publishes exactly one index.
- **Website first, keyed by source node.** Only Website sources may be combined in this release (at most 5, enforced when a version is saved; existing versions keep running). Run items, frontier rows, snapshot members and index membership are already keyed by source node ID, so other connector kinds can join without another membership model.
- **Merged correctness (slice 1).** Repeated site chrome is fingerprinted per source node (`crawl_state.__processing__.fingerprints` is a dict keyed by source node; older runs' shared list is still read), so one site's navigation never changes how another site's pages are cleaned. An index holds one revision per source item (`uq_index_source_item`), so a page reached by two sources is indexed once: the later copy is recorded as a `duplicate` run item naming the kept source, and the kept snapshot member's `provenance.also_found` lists every other source node and URL where the page, or a duplicate of it, was found. Prior revisions stay keyed by location because the prior index holds at most one row per URL.
- **Layout field and editor (slice 3).** `index_layout` is an optional schema-2 field defaulting to `merged` rather than a schema 3, so saved versions and the editor's schema checks are unchanged; slice 5 adds `per_source`. The editor adds Website sources beside the first (IDs `source-2`…, each with its own edge into Extract), names them Website 1…N, validates each, fixes the source type while there are several, and mirrors the server's five-source and 2,500-page limits. Server field errors are keyed by node ID so each source shows only its own.
- **Refresh one source (slice 4).** `RefreshSourceInput.source_node_ids` limits a merged Website run to selected sources; it needs a ready index, records the selection in pipeline order (all sources means a full refresh), and the worker skips the others, carrying their prior pages forward with source outcome `skipped`, which is not a warning.
- **Sources panel and shared stages (editor only).** Website pipelines on schema 2 are edited as sources plus one shared set of stages (`frontend/src/features/ingestion-pipelines/sourcesView.ts`, plan in `docs/ingestion-sources-panel-plan.md`). The saved per-source format is unchanged: every branch keeps a complete chain. The editor derives each stage's shared settings as the configuration most branches use (ties go to the earliest source); a branch that differs, or that the user marked customized in this session, is shown as customized. Shared edits write to every non-customized branch; adding a source and switching back to one combined index copy the shared settings rather than the first branch's. Trade-off: no customization flag is persisted, so two of three sources that happen to share a custom value would become the shared settings; storing an explicit override list would need a schema change and was not required.
- **Concurrent site crawls (slice 6).** A run's Website sources are grouped into lanes: sources whose allowed origins overlap share a lane and crawl one after another, so each origin keeps the single per-origin rate limiter of one crawl. Lanes crawl at the same time on up to `WEBSITE_RUN_SOURCE_CONCURRENCY` threads (default 3, maximum 5); with one lane, or a setting of 1, sources crawl in turn exactly as before. `ingestion_execution.start_nodes` marks every concurrent source running without the ordering side effect of `transition`, which would mark an earlier source finished while it is still crawling. Each crawl writes through its own fenced `RunCrawlStore`; every write locks the run row and merges only its own source's `crawl_state` entry, and each crawl holds at most one database connection at a time, so the peak stays within the engine's pool of 5 without overflow. If a lane loses the execution token or raises a failure that is not an isolated whole-site failure, a shared stop event makes the other lanes refuse further page commits; their committed pages remain for recovery, and the error is raised once every lane has stopped. Page fetch threads per source (`WEBSITE_FETCH_CONCURRENCY`) are unchanged, so a run can fetch up to 3 × 4 pages at once across different sites.
- **One index per source (slice 5).** Schema-2 `index_layout: per_source` is validated by `_per_source_chains`: 1–5 Website sources, each with its own Source → Extract → Clean → Chunk → Embed → Publish chain, unique index names and IDs; schema-2 limits rose to 30 nodes and 25 edges. `IngestionExecution.branches()` returns each chain as an ordinary single-chain merged execution, so a branch run is a normal `IngestionRun` (its snapshot holds the branch) and every worker, fencing, recovery, cancellation and publication path is reused. `ingestion_run_groups` (migration `0044`) records one start; runs carry `group_id` and `branch_source_node_id`. `start_group` creates every branch run in one transaction with `start_run(commit=False)` and rolls back with a 409 naming the busy index if any branch's knowledge set already has an active run. Group status is derived on read (`partial` when branches ended differently) and runs are listed in source order. The single-run endpoint returns 409 for per-source versions; previews take one branch; schedules and the dispatcher call `start_scheduled`, which starts a group and records its first branch run as the schedule's last run. Branch runs that publish never affect each other.
- **Partial failure carries forward (slice 2).** Only runs that crawl two or more sources isolate failures; a single-source run still fails on any failed page, as before. A source fails when its crawl raises a non-retryable `ConnectorFailure` (recorded through `RunCrawlStore.mark_failed` in that source's `crawl_state`, so recovery does not retry it; retryable failures still retry the whole run) or when every page it reached failed. A failed source's frontier pages are not processed; its pages in the prior ready index are carried forward as `carried_forward` run items (migration `0043`) and are never recorded as removed. A failed page in a working source carries its prior copy forward when there is one and is otherwise reported failed. A carried page whose processing hash differs from the run's settings (`website_ingestion.website_processing_identity`) is reprocessed from its stored artifact, with chrome fingerprints measured over that source's carried pages; otherwise the prior revision is reused without reading it. If every source fails, the run fails and the previous index stays ready. Per-source outcomes are written to `crawl_state.__outcomes__` in the fenced assembly commit and returned as `source_outcomes`; `completion` is derived on read (`with_warnings` when a source failed or any page failed), so no run column or status changed. `finish_remote` keeps failed items failed and counts them. Snapshots count carried pages in `carried_forward_count`. Trade-off: publishing with failed pages deliberately differs from the single-source rule recorded on 2026-10-03; the owner chose it for multi-source pipelines on 2026-10-05.

## Studio shell and guided pipeline setup (spec 0003, 2026-10-06)

[Spec 0003](specs/0003-studio-shell-guided-setup/index.md) changes the Studio's look and adds a second way to create a Website ingestion pipeline. It is frontend only; no API, schema or worker changed.

- **Shell.** `ShellSidebar` and `ShellTopBar` replace the spec 0002 sidebar and header. The document still scrolls as a whole, so sticky elements, scroll restoration and the Playground viewport layout keep working; the editor height variables subtract the new 74px of shell chrome (`--shell-chrome`). Breadcrumb parent links carry hidden "(breadcrumb)" text so their accessible names never collide with the sidebar's.
- **Runs in progress.** The API cannot filter runs by status, so the top bar counts queued and running runs among the project's 20 most recent (`GET /projects/{id}/ingestion-runs?limit=20`, newest first), polling one request at a time every 10 seconds while the tab is visible. Older runs that are still active are not counted; the tooltip says so. An exact count would need a status filter on the endpoint.
- **Quick jump.** There is no server search; the top bar's search navigates among the workspace pages, the projects already loaded for the switcher and the first page of the current project's answer and ingestion pipelines.
- **Guided setup.** `guidedModel.ts` edits an ordinary schema 2 Website draft with the sources-panel helpers (`addSharedWebsiteSource`, `setSharedIndexLayout`, `sharedTargets`, `resetToShared`, `removeSource`), so Save and publish posts the same `IngestionPipelineDraft` to the same `POST /projects/{id}/pipelines` as the canvas editor and the saved version opens in the editor with no unsaved changes. Merged pipelines start a refresh run; per-source pipelines start a run group, as the editor does. Website settings for a URL are derived the way the editor's source settings derive them (crawl from the address, or sitemap for an `.xml` address; origin and include prefix from the URL). Chunk size edits keep the default draft's hard maximum ratio (4/3 of the target) and keep overlap below the target; other settings are left for the editor.
- **Draft persistence.** The guided draft (configuration and, after saving, the pipeline, version and run ids; never fetched content) is kept in `sessionStorage` under `ingestion-guided:v1:<project>`, so it survives a reload in that tab and is cleared by Discard draft. Close keeps it.
- **Previews.** Each site can be previewed on its own branch (`branchExecution`) through the existing preview endpoint; preview results are not stored with the draft.
