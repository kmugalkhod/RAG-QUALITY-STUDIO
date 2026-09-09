# Application architecture

The React workspace calls same-origin `/api` endpoints. Vite proxies requests during development; nginx serves the production build and proxies requests in Compose. Tailwind provides theme tokens; the local shadcn-style Button uses Radix Slot and class-variance-authority. Forms use native labeled controls.

FastAPI routes delegate project operations to a service using a request-scoped synchronous SQLAlchemy session. Synchronous routes run in FastAPI's thread pool. Pydantic validates and trims inputs; PostgreSQL constraints also protect stored lengths. Project IDs are UUIDs, timestamps are database-generated timezone-aware values. Listing uses bounded offset pagination and a composite timestamp/ID index. Count and rows share a repeatable-read transaction. Duplicate names are allowed because names are labels, not identities.

Alembic owns the schema. A one-shot migration service must complete before the API starts. PostgreSQL uses a persistent named Compose volume. The pgvector-capable image anticipates the repository's database convention, but no vector extension or embeddings are introduced. Document parsing/chunking is described below.

Liveness does not contact storage. Readiness verifies project, document, processing-run and chunk columns are queryable, catching missing migrations as well as database outages. SQLAlchemy failures become generic 503 responses. Database connection/statement timeouts bound failures. CORS is explicit, and all local published ports bind to loopback. Authentication must precede shared access.

Unit tests exercise input and outage behavior. Database tests require a separate empty PostgreSQL database ending in `_test`, run migrations rather than create_all, and roll back test writes. Compose tests use tmpfs, never the development volume. Playwright journeys use the actual API and leave their uniquely named verification records in the separate browser-test stack.

Projects own document uploads and processing history. Project deletion is intentionally absent, so no historical evidence can be cascaded away. Celery workers perform parsing/chunking; no model providers or pipeline engine are included. Authentication, backup/restore procedures and public deployment are later release work.

Official implementation references: [Vite setup](https://vite.dev/guide/), [FastAPI database session dependencies](https://fastapi.tiangolo.com/tutorial/sql-databases/), [shadcn manual installation](https://ui.shadcn.com/docs/installation/manual).

## Milestone 2A: documents and processing

The Knowledge Base is a project-specific hash route (`#/projects/{id}`), so reload and browser navigation preserve project selection without new routing dependencies. Components call a feature API module; no database or parser work runs in React. Documents, processing history and chunks have bounded pagination. Polling uses fresh requests, suppresses stale responses after navigation, and displays saved run settings separately from editable settings. “Processed” means text chunks exist, not indexed or searchable.

### Storage and upload transaction

`documents` records immutable UUID identity, project, original filename, byte size, SHA-256, media type and upload time. Repeated uploads always create separate identities. Browser MIME types are untrusted: the extension and content are checked. TXT is strict UTF-8 (optional leading BOM), nonempty and excludes NUL; PDF must have a PDF signature, then receives full structural/encryption/text validation in the worker. Invalid signed PDFs therefore upload successfully and fail processing explicitly.

An ASGI body limit bounds multipart spooling to the configured file limit plus 64 KiB overhead, including requests without Content-Length. Exactly one multipart `file` field is accepted. The default file limit is 20 MiB (configurable up to 100 MiB); nginx has a 101 MiB transport ceiling. Original names are metadata only. Bytes are streamed to an exclusive generated `.part` name, hashed and fsynced; an atomic rename and directory fsync precede the database commit. API and workers share the named `document_data` volume.

Known failures before commit remove staged/final files and roll back records. An ambiguous commit or process crash can leave an unreferenced file, but must never trigger deletion of a possibly committed file. This favors referential safety over immediate reclamation. With API uploads stopped, operators can compare `documents.storage_name` against files on the volume and inspect old unreferenced files/`.part` files before removing them. No automatic cleanup deletes persistent data. There is no document/project deletion API or cascade; historical runs/chunks remain attached to their source.

### Versioning and deterministic parsing

Every start creates a numbered `processing_runs` row, retaining chunk size, overlap, `characters-v1` and the pinned parser version. Failed/cancelled runs remain immutable history; a user retry is a new version. Only one queued/running run per document is permitted by a PostgreSQL partial unique index. Version allocation is serialized on the document row. All API access reaches documents through the requested project and runs/chunks through that document. Foreign keys preserve ownership chains.

`characters-v1` measures Python Unicode code points, not bytes, graphemes or tokens. TXT drops only an initial UTF-8 BOM; CRLF, whitespace and Unicode content otherwise remain unchanged. PDFs use pypdf's extracted text order; offsets are relative to that extracted page text. Within each nonblank page/source: start at 0, take `[start, min(start + chunk_size, length))`, advance by `chunk_size - overlap`, and stop as soon as a window reaches the end. There is no extra overlap-only trailing chunk, word-boundary adjustment or cross-page window. Blank pages produce no chunks; PDF page numbers remain 1-based and chunk ordinals are 0-based. TXT page is null. Bounds are enforced in schemas and database constraints.

PDFs are parsed with strict pypdf. Encrypted/malformed PDFs fail. Image-only pages in otherwise mixed documents fail as requiring unsupported OCR; entirely nonextractable documents fail with the same explanation. Text extraction order/layout is parser-dependent; detecting nonempty text does not certify extraction completeness. A page with both extractable text and image-contained text may still require human inspection. There is no OCR or semantic chunking.

Processing limits: 2,000 PDF pages, 5,000,000 extracted characters, 50,000 chunks and 10,000,000 total output characters (including overlap). The worker has 110-second soft and 120-second hard task limits, concurrency 2, prefetch 1, child recycling and a Compose memory limit. Large/pathological compressed PDFs may terminate a worker and are handled by bounded stale recovery. These are local-use bounds, not a hardened public parsing sandbox.

### Queue, duplicate delivery, cancellation and recovery

PostgreSQL is the durable queue and sole status authority. The API commits `queued` and returns 202 promptly; it never waits for Redis. A dedicated dispatcher scans every five seconds, sends only run IDs to Celery/Redis, and re-sends unclaimed queued runs no more than every 30 seconds. Redis AOF improves queue persistence but is not necessary for reconstructing accepted jobs. A crash between broker send and recording dispatch time may duplicate a message; a broker outage leaves the durable job queued. Dispatcher transactions lock a bounded batch with `SKIP LOCKED`.

Workers open their own sessions. A short READ COMMITTED row lock claims only queued work, increments the database attempt counter, and assigns a fresh execution token. Running/terminal duplicate deliveries are no-ops. Parsing occurs outside transactions; progress and cancellation are checked between pages. Chunk count/output-size checks bound per-page window generation. Chunks remain in bounded worker memory until a final row-locked transaction verifies the token/status, inserts every chunk and marks success together. Failed/cancelled/recovered attempts cannot expose a partial successful chunk set or publish under an obsolete token.

Cancellation conditionally changes queued/running to cancelled and invalidates the token. It prevents publication immediately; an in-flight parser call may continue until its next page checkpoint or time limit. UI/API explain this distinction. Completion/cancellation are serialized by the row lock; cancelling an already terminal run returns that terminal state.

The dispatcher recovers running attempts older than 180 seconds from start (beyond the worker hard limit): invalidate the token, requeue if fewer than three attempts, otherwise mark failed with an interruption error and finish time. Transient storage/database failures also requeue up to the same three-attempt cap, with at least a 30-second dispatch delay; deterministic parser errors fail immediately. There is no stacked Celery automatic-retry loop. If database access fails while recording an error, stale recovery performs the eventual transition after connectivity returns. Queued work can remain queued while workers/broker are offline; this is visible and cancellable. Keep the dispatcher running (`restart: unless-stopped`); restart it to resume recovery after an outage. Operators should inspect failed runs and adjust inputs/settings before starting new versions.

### Verification boundaries

Shared pytest fixtures require an empty dedicated PostgreSQL database ending in `_test`. API-only tests roll back; worker integration tests commit to that isolated database and delete only their own IDs after each case. Upload storage is pytest's temporary directory. The isolated backend Compose database is tmpfs. `compose.e2e.yaml` runs the complete app with its own database, Redis and document volumes and alternate loopback ports; browser and restart checks never touch development storage. No embeddings, vector extension/index, model calls, question answering, canvas or evaluation are part of 2A.

Implementation references: [Celery task acknowledgement, limits and duplicate delivery](https://docs.celeryq.dev/en/stable/userguide/tasks.html) and [pypdf text extraction and OCR limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

The nginx API proxy resolves the Compose backend service through Docker DNS with a five-second cache, so recreating the API container does not leave the frontend pointed at its old address. See [nginx variable proxy_pass resolution](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass).
