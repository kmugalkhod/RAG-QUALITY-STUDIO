# Robust ingestion release baseline

Measured on 2026-09-25 against synthetic, reviewed fixtures in the pinned backend
container. This report combines the extraction and cleaning baselines with the complete
schema-v2 chunking, duplicate/language, sensitive-data, additional-format and publication
tests. It is a release gate for this corpus, not a claim about arbitrary documents.

| Gate | Measured result | Threshold |
| --- | ---: | ---: |
| Native normalized character preservation | 100.000% | at least 99.5% |
| OCR character error rate | 0.570% median; 1.141% p95 | at most 5%; at most 12% |
| Reviewed reading-order precedence | 100.000% | at least 95% |
| Simple table cell/header association | 100.000% | at least 95% |
| Boilerplate precision / recall | 100% / 100% (22 labelled removals) | at least 99% / 90% |
| Reviewed useful/protected retention | 100% (16/16 blocks) | no reviewed body deletion |
| Chunk hard-limit compliance | 100%; forced protected splits carry findings | 100% or explicit finding |
| Exact chunk source-span checks | 100% for reviewed section/parent-child cases | 100% |
| Deterministic rerun | 100% matching outputs/hashes excluding measured duration | 100% |
| Publication integrity | 100% across failure/cancel/stale/duplicate-delivery tests | 100% atomic |

The corpus includes native, scanned, mixed and rotated PDFs; two-column order; a simple
table; repeated headers/footers, footnotes and Website chrome; protected code/list/table/
quote blocks; Unicode and multilingual content; exact/near duplicates; language policy;
synthetic sensitive values; malformed/encrypted/resource-limit failures; and every
released Markdown, HTML, DOCX, PPTX, CSV, TSV and XLSX adapter. The all-format integration
gate performs upload → asynchronous preview → schema-v2 processing → embedding/index
publication → grounded answer/evidence with deterministic provider doubles.

Observed extraction time in the local ARM64 container was about 9 ms native, 237 ms
ordinary OCR, 578 ms rotated OCR and 12 ms layout/table in the Phase 2 measurement.
These are diagnostic samples, not throughput guarantees. Monetary OCR/parser cost is
local and recorded as no known provider charge; embedding/generation cost remains unknown
unless the configured provider returns it. PostgreSQL and artifact-storage growth are
reported with [operations.sql](operations.sql), because host filesystem/database overhead
is deployment-specific.

No universal retrieval winner is claimed. Section-token is the new-draft default because
the reviewed structural corpus proves hard bounds, faithful spans and heading-context
separation; character-window remains compatibility behavior and parent/child remains an
explicit alternative. A production recommendation between them requires a larger,
human-labelled downstream question set on the deployment's own source distribution.
Failures and skips remain visible in the test/report output and are never removed from an
aggregate denominator.

Reproduce on a clean isolated stack:

```sh
docker compose -p rag-studio-tests -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -p rag-studio-tests -f compose.test.yaml down
```

Then run frontend lint, strict type checking, Vitest and the production build, followed by
Agent Browser journeys at `http://127.0.0.1:5273`. Use only synthetic data and deterministic
provider doubles for the release gate.

## Final release verification

The 2026-09-25 final gate passed with 346 backend tests and 4 opt-in live-provider tests
skipped, 121 frontend tests, Ruff/Prettier/lint/type/lock checks and a production frontend
build. Agent Browser completed encrypted upload, processing, sensitive preview, atomic
publication and redacted answer-evidence inspection. The tested synthetic email and phone
never appeared in the browser DOM; evidence rendered `[EMAIL]` and `[PHONE]`. Layouts at
1440, 720 and 390 CSS pixels had no horizontal document overflow and produced no browser
errors or application console errors.
