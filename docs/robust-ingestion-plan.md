# Robust extraction, cleaning and chunking implementation plan

Status: implementation in progress; Phases 0–6 completed by 2026-09-25; Phase 7A decision gate next
Last updated: 2026-09-24
Related plans: [ingestion pipeline plan](ingestion-pipeline-plan.md),
[source snapshot/index variants plan](source-snapshot-index-variants-plan.md)

## 1. Purpose

This plan evolves the implemented ingestion pipeline from simple parser dispatch,
whitespace cleanup and character windows into a robust, inspectable and reproducible
content-preparation system.

The target system must:

- extract useful structure from native and scanned documents;
- preserve page, section, table, list, code and source provenance;
- apply the same deterministic cleaning semantics to every connector;
- detect low-quality extraction before embedding or publication;
- support exact and near-duplicate decisions with visible reasons;
- produce structure-aware chunks while preserving faithful evidence text;
- let users inspect raw, extracted, cleaned and chunked representations;
- measure ingestion quality with reviewed fixtures and downstream retrieval tests; and
- preserve all existing pipeline versions, source revisions, indexes, queries and
  experiments.

This is an implementation plan, not a claim that these capabilities already exist.
Each phase is an independent delivery boundary. Do not present a later-phase control
in production until its backend path, persistence, failure behavior and tests exist.

## 2. Current implementation and verified gaps

The existing ingestion foundation is valuable and must be retained:

- immutable pipeline versions and validated linear ingestion graphs;
- project-scoped source connections, revisions and source snapshots;
- durable, fenced and cancellable ingestion/indexing jobs;
- explicit source membership and atomic index publication;
- Website, S3, Notion, Confluence and Existing Files sources;
- exact ready-index selection in answer pipelines and experiments; and
- persistent node execution checkpoints.

The following gaps motivate this plan:

1. `ExtractNode` currently supports only `media_type_registry`. It has no OCR,
   layout, table, language or quality policy.
2. uploaded TXT/PDF processing transitions through Extract, Clean and Chunk node
   states, but directly character-chunks parser output. The saved Clean configuration
   is not applied to that path;
3. scanned PDF pages fail instead of using a bounded OCR fallback;
4. PDF extraction preserves page numbers but not blocks, headings, tables, bounding
   boxes or reading-order diagnostics;
5. Website, S3, Notion and Confluence implement similar cleaning/chunking loops
   separately, allowing behavior to drift;
6. several connector cleaners collapse whitespace even when the configuration says
   normalization is disabled;
7. Notion and Confluence window individual segments, which can create isolated short
   chunks rather than coherent section windows;
8. exact extracted-text deduplication is run-local and cannot identify near-duplicate
   mirrors or template variants; and
9. Extract and Clean settings are displayed as facts in the editor instead of being
   editable and previewable.

Phase 0 addresses semantic correctness before adding new engines.

## 3. Product principles

### 3.1 Application-owned contracts

RAG Quality Studio owns the extraction, cleaning, quality and chunk contracts.
Third-party parsers are adapters. Persisted data must not expose a vendor-specific
JSON format as the product contract.

### 3.2 Raw content remains immutable

Keep the exact fetched/uploaded artifact and its hash. Extraction, cleaning and
chunking create versioned derivations. Never overwrite a previous representation or
silently rewrite chunks belonging to a ready index.

### 3.3 Deterministic processing first

Default extraction and cleaning must be reproducible from the raw artifact, versioned
configuration and pinned dependency/runtime versions. LLM transformations are not part
of the initial robust path.

### 3.4 Structure before chunking

Do not flatten a document to one string before recording its semantic and layout
boundaries. Chunkers consume typed blocks and produce explicit source-span mappings.

### 3.5 Quality is a policy, not an invented confidence score

Persist observable measurements and findings. A versioned quality policy maps those
facts to `pass`, `warn`, `exclude` or `fail`. Do not label a composite heuristic as
probability or factual confidence.

### 3.6 One behavior across connectors

After a connector returns a canonical raw artifact or provider-native block stream,
the same extraction/cleaning/chunking contracts apply. Connector modules retain only
discovery, fetching, identity, provider revision and connector-specific provenance.

### 3.7 Inspect before paying

Preview extraction, cleaning, quality findings and chunks before embedding. A preview
must never publish an index or manufacture a successful run.

## 4. Target processing architecture

```text
Source connector
    │
    ▼
Immutable raw artifact + source revision
    │
    ▼
Extractor registry ──► native text / layout-aware / OCR adapter
    │
    ▼
ExtractedDocument (pages + typed blocks + provenance + findings)
    │
    ▼
Ordered deterministic cleaning transforms
    │
    ▼
CleanedDocument (blocks + transform audit + quality measurements)
    │
    ├──► quality policy: pass / warn / exclude / fail
    │
    ▼
Chunk profile (legacy character / section-token / parent-child)
    │
    ▼
Evidence text + embedding text + exact block-span membership
    │
    ▼
Embed and atomically publish immutable index version
```

### 4.1 Canonical extracted-document contract

The Python contract should be strict, versioned and independent of SQLAlchemy and any
extractor package:

```python
class ExtractedDocumentV1:
    schema_version: Literal[1]
    media_type: str
    title: str | None
    language: LanguageResult | None
    pages: list[ExtractedPage]
    blocks: list[ExtractedBlock]
    measurements: ExtractionMeasurements
    findings: list[QualityFinding]

class ExtractedBlock:
    id: str
    ordinal: int
    type: Literal[
        "title", "heading", "paragraph", "list_item", "table",
        "code", "quote", "image_caption", "footnote", "unknown"
    ]
    text: str
    page_number: int | None
    bounding_box: BoundingBox | None
    heading_path: list[str]
    source_span: SourceSpan
    attributes: dict[str, JsonValue]
```

Rules:

- block IDs are deterministic within one derivation;
- ordinals define the chosen reading order;
- coordinates use one documented normalized coordinate system;
- tables also carry bounded structured rows/cells in `attributes`;
- raw provider payloads and arbitrary parser objects are not persisted in
  `attributes`;
- every text block has a source span or an explicit `derived` marker;
- findings contain safe codes and counts, never raw document excerpts; and
- contract validation occurs before persistence.

### 4.2 Cleaned-document contract

A cleaned document retains the same logical block identity where possible. When a
transform joins or splits blocks it records parent block IDs. It contains:

- ordered cleaned blocks;
- extractor and cleaner version/configuration hashes;
- input and output content hashes;
- per-transform counts and duration;
- removed/rewritten spans for bounded preview diffs;
- quality measurements and policy decision; and
- no secrets, credentials or unbounded raw provider metadata.

### 4.3 Chunk contract

Each chunk stores:

- faithful `evidence_text` shown to the answer model and citation inspector;
- optional `embedding_text` containing deterministic title/heading enrichment;
- token and character counts;
- parent chunk ID when parent/child mode is used;
- exact ordered block/span membership;
- page range and heading path derived from those spans;
- chunker name, version, tokenizer and configuration hash; and
- the immutable cleaned derivation ID.

Never display the heading-enriched embedding text as if it were a verbatim citation.

## 5. Versioning and backward compatibility

### 5.1 Pipeline schema v2

Do not change the meaning of already saved schema-v1 pipelines. Introduce ingestion
execution schema v2 for robust settings.

```yaml
schema_version: 2
extract:
  strategy: auto # auto | native | layout_aware
  ocr:
    mode: auto # off | auto | always
    languages: [eng]
    rotate_pages: true
    deskew: true
  tables: preserve # preserve | markdown | plain_text
  quality_policy: default-v1
clean:
  profile: standard-v1
  steps:
    - type: unicode_normalize
      form: NFC
    - type: remove_repeated_headers_footers
      minimum_page_ratio: 0.6
    - type: dehyphenate
      mode: conservative
    - type: reflow_lines
      preserve_blocks: true
  deduplication:
    mode: exact # off | exact | exact_and_near
chunk:
  algorithm: section_token # character_window | section_token | parent_child
  tokenizer: configured-model
  target_tokens: 400
  maximum_tokens: 600
  overlap_tokens: 60
  enrich_embedding_text: true
```

The final Pydantic schema must use discriminated unions instead of optional fields and
condition-heavy validators. Every algorithm/profile gets its own typed configuration.

### 5.2 Existing pipeline behavior

- schema-v1 versions remain readable and executable by a `legacy-v1` executor;
- existing indexes, source revisions and experiments are never reprocessed;
- the UI labels v1 as **Legacy character extraction**;
- **Upgrade as draft** creates an unsaved v2 copy with explicit mapped defaults;
- saving the upgraded draft creates a new immutable pipeline version;
- a run never silently switches extractor, OCR engine, cleaner or tokenizer; and
- removing legacy execution is a separate migration only after all retained versions
  have an approved archival strategy.

### 5.3 Processing identity and cache key

Reusable derivation identity is the hash of:

```text
raw content hash
+ canonical extractor configuration
+ extractor adapter/runtime version
+ canonical cleaner configuration
+ cleaner runtime version
+ canonical chunk configuration
+ tokenizer identity/version
```

Extraction and cleaning should also have separate intermediate hashes so a chunk-only
change can reuse a compatible cleaned derivation. Hash canonical JSON with stable key
ordering and explicit schema versions.

## 6. Persistence and migration design

Use additive Alembic migrations. Do not backfill historical block structure from old
chunks because that relationship cannot be reconstructed reliably.

### 6.1 Proposed records

`content_derivations`

- immutable ID, project ID and document ID;
- optional source-revision ID;
- kind: `extracted` or `cleaned`;
- schema version, status and predecessor derivation ID;
- engine/profile/configuration and runtime versions;
- input/output hashes;
- bounded measurements/findings JSON;
- block count, page count and character count;
- optional structured-artifact storage name;
- creation/completion timestamps.

`content_blocks`

- derivation ID and ordinal;
- deterministic block key and block type;
- text;
- page number and normalized bounding box;
- heading path and bounded typed attributes;
- parent/source block keys and source span;
- indexes on `(derivation_id, ordinal)` and demonstrated inspector filters.

`chunk_block_spans`

- processing-run ID and chunk ordinal;
- cleaned derivation ID and block ordinal;
- ordered span ordinal plus block start/end offsets;
- composite foreign keys preserving project/document/derivation ownership.

Existing `chunks.text` remains the evidence text for compatibility. Add nullable
`embedding_text`, token counts, parent ordinal and derivation ID only when the phase
that consumes them is implemented.

### 6.2 Storage choice

Persist queryable block metadata/text in PostgreSQL for bounded inspection and exact
provenance. Persist large complete structured representations as immutable files on the
existing storage abstraction. Database rows reference their content hash and storage
name. Never store large parser-native object graphs in JSONB.

### 6.3 Integrity rules

- a successful derivation has at least one nonempty block;
- block ordinals are unique and contiguous per derivation;
- every chunk span references the same project/document lineage;
- a processing run cannot combine blocks from different cleaned derivations;
- a quality `fail`/`exclude` decision cannot publish membership;
- warning publication requires the pipeline's saved warning policy;
- cancellation or stale-token recovery cannot expose partial successful derivations;
- derivative storage cleanup follows the same referential-safety rule as raw files; and
- migrations never cascade-delete evidence used by ready indexes or experiments.

## 7. Backend ownership and coding practices

Introduce modules only when their phase is implemented:

```text
backend/app/ingestion_content/
  contracts.py             # application-owned extracted/cleaned/block types
  registry.py              # extractor selection and declared capabilities
  quality.py               # measurements, finding codes and policy evaluation
  extraction/
    base.py
    text.py
    pdf_native.py
    docling.py              # added only with the layout/OCR phase
    html.py
    notion.py
    confluence.py
  cleaning/
    base.py
    engine.py
    transforms.py
  chunking/
    base.py
    character.py
    section_token.py
    parent_child.py
```

These are logical ownership boundaries, not permission to create empty files.

Implementation rules:

- use protocols/abstract interfaces at third-party boundaries, not around every
  function;
- keep Pydantic/domain contracts separate from SQLAlchemy models;
- keep API routes thin and provider/parser calls out of routes;
- make transforms small, ordered, pure functions where possible;
- use a registry mapping validated media type/profile to an adapter; avoid growing
  connector-specific `if/elif` trees;
- use one shared cleaner and chunker across connectors;
- return typed safe errors with stable codes and stage/item context;
- inject clocks, parser adapters and tokenizer adapters in tests;
- log IDs, versions, durations and counts, never raw text or OCR output;
- bound every collection, page, block, image, table, diff and API response;
- do not add generic repositories, event buses, plugin systems or microservices
  without a demonstrated second consumer;
- pin parser/OCR/tokenizer dependencies and record their runtime versions;
- consult official documentation before selecting or upgrading version-sensitive
  extraction dependencies; and
- keep live OCR/provider checks opt-in and separate from default deterministic tests.

## 8. Durable execution behavior

### 8.1 Stage checkpoints

Use the existing ingestion run, item and node checkpoints. Add per-item persisted
substage data rather than inferring it in the browser:

```text
fetch → extract → clean → quality → chunk → embed → publish
```

Quality may remain represented inside the Clean node in the graph initially, but it
must be a separately recorded item checkpoint/finding set. Adding a new canvas node is
a later product decision and is not required for correct execution.

### 8.2 Idempotency and retries

- claim work with the existing database token-fencing pattern;
- checkpoint between pages and bounded block batches;
- reuse a complete compatible derivation by its configuration hash;
- never reuse a partial, failed, cancelled or warning-incompatible derivation;
- retries use the same saved versions and do not silently change engines;
- paid embedding begins only after extraction/cleaning/chunk quality passes;
- an in-flight OCR/parser call may finish after cancellation, but an obsolete token
  cannot commit or publish it;
- provider/parser retry budgets remain single-layered and bounded; and
- stale recovery accurately reports whether reusable intermediate work was retained.

### 8.3 Isolation for untrusted documents

Layout parsing and OCR must not run unbounded inside the API process. Execute them in
the worker with:

- task hard/soft timeouts;
- memory, temporary-disk, page, pixel and decompressed-size limits;
- bounded parallel pages and child-process recycling;
- generated temporary paths outside persistent storage;
- no network access unless an explicitly selected engine requires it;
- cleanup that never deletes a possibly committed persistent artifact;
- sanitized errors and parser logs; and
- dependency/security review for native binaries and model files.

## 9. API and frontend behavior

### 9.1 Capability discovery

Add a read-only server capability endpoint only when more than one real profile exists.
It returns safe supported media types, extractor profiles, OCR languages, table modes,
clean transforms, chunk profiles and configured availability. It never returns paths,
credentials or internal command lines.

### 9.2 Asynchronous preview

Extend the existing persisted preview pattern. Preview runs the exact saved/draft v2
configuration against a bounded item/page sample and stores an expiring result.

Required reads:

- preview summary and status;
- paginated items and per-stage outcome;
- paginated extracted/cleaned blocks;
- one-page/block before/after diff;
- proposed chunks with token/character counts and source spans; and
- quality measurements/findings.

Preview does not embed, create an index or change the current source snapshot. For
remote sources, distinguish a cached-artifact preview from a fetch preview and state
whether network access will occur.

### 9.3 Extract settings UI

Provide labeled controls for:

- extraction strategy: Auto, Native text, Layout-aware;
- OCR policy: Off, Automatic fallback, Always;
- OCR languages from server capability data;
- rotation and deskew;
- table handling; and
- quality policy.

Unavailable engines remain visibly unavailable with a reason. Do not make a missing
OCR dependency look selectable.

### 9.4 Clean settings UI

Use an ordered list of supported typed transforms. Users can enable, disable and
configure rules, but cannot enter Python/shell/SQL. Do not initially accept arbitrary
regular expressions. If bounded selectors or patterns are later added, validate length,
complexity and supported syntax on the server.

### 9.5 Four-stage inspector

The preview/run inspector synchronizes:

1. **Raw** — safe source/page metadata and original rendered page where supported;
2. **Extracted** — block type, reading order, table structure, OCR markers and
   provenance;
3. **Cleaned** — before/after changes attributed to transform IDs; and
4. **Chunks** — boundaries, heading context, token count, embedding enrichment and
   source spans.

The browser receives bounded text and image previews. Raw HTML is never executed, and
untrusted document content is not inserted with unsafe HTML.

### 9.6 Run results

Per item show:

- selected extractor and actual fallback path;
- native/OCR page counts and OCR languages;
- warnings and quality decision;
- input/output characters and removed block/span counts;
- duplicate decision and retained canonical item;
- chunk counts and size distribution;
- stage durations and known compute/provider cost; and
- exact derivation, source revision, pipeline and index links.

## 10. Phased implementation

### Phase 0 — Correctness baseline and shared processing boundary

Goal: make current Extract/Clean behavior truthful and establish one reusable execution
boundary without adding OCR or new chunk algorithms.

Backend work:

- document current v1 behavior in tests before refactoring;
- introduce application-owned extractor, cleaner and chunker interfaces for current
  TXT, PDF, HTML, Notion and Confluence behavior;
- centralize whitespace/boilerplate/minimum/maximum-text handling;
- remove duplicated connector `_clean` implementations;
- ensure `normalize_whitespace=false` has one documented, tested meaning;
- keep v1 execution unchanged for historical versions;
- add the schema-v2 envelope with v1-equivalent native extraction, standard cleaning
  and legacy character chunking;
- make v2 Existing Files actually execute the saved Clean configuration;
- include extractor/cleaner/chunker versions in the processing configuration hash; and
- provide typed stage errors and configuration validation.

Frontend work:

- label v1 pipelines as legacy;
- add **Upgrade as draft** with an explicit mapping summary;
- make the existing v2 Clean fields editable with accessible controls;
- keep unsupported OCR/layout controls absent, not disabled-looking placeholders; and
- display exact engine/profile versions used by completed runs.

Tests:

- connector parity fixtures prove identical input blocks/config produce identical
  cleaning output;
- v1 snapshots before/after refactor are byte-for-byte unchanged;
- v2 uploads apply every saved clean setting;
- cancellation, duplicate delivery, stale recovery and project isolation regressions;
- clean migration plus populated upgrade/downgrade preservation; and
- frontend save/reopen/dirty guard/server-validation tests.

Exit gate:

- no connector owns a separate general-purpose cleaner;
- v1 remains reproducible;
- v2 Extract/Clean/Chunk node states correspond to real executed work; and
- all current ingestion/answer/experiment regressions pass.

### Phase 1 — Canonical document IR and immutable derivations

Goal: persist structured extracted/cleaned content and exact block-to-chunk provenance.

Backend work:

- implement `ExtractedDocumentV1`, block, page, table, source-span, finding and
  measurement contracts;
- add additive derivation/block/span migrations and constraints;
- implement atomic persistence services with bounded batches;
- adapt TXT, native PDF, Website, Notion and Confluence extraction into the IR;
- preserve heading paths already available from Website/Notion/Confluence;
- record explicit `unknown` block types rather than discarding unrecognized content;
- make the legacy character chunker consume cleaned blocks while reproducing v1-equivalent
  evidence text for v2 settings;
- link every new v2 chunk to exact block spans; and
- expose bounded derivation/block reads for inspection.

Frontend work:

- add read-only Extracted and Cleaned inspector tabs for completed v2 runs;
- paginate blocks and show type/page/section/source provenance; and
- clearly label historical v1 runs as having unavailable block lineage.

Tests:

- strict contract round trips and rejection of malformed/unbounded attributes;
- deterministic block IDs/order/hashes;
- project/document/revision/derivation ownership constraints;
- block-span mappings across joined and split blocks;
- atomic failure/cancellation with no partial successful derivation;
- historical v1 indexes and experiments remain readable; and
- large bounded document pagination and query-plan checks.

Exit gate:

- all v2 connectors emit the same canonical contract;
- each v2 chunk traces to raw revision → extracted derivation → cleaned derivation →
  source blocks; and
- changing extraction configuration creates a new immutable derivation.

### Phase 2 — Layout-aware PDF extraction, tables and OCR

Goal: support native, complex-layout, scanned and mixed PDFs with bounded fallbacks.

Dependency decision:

- implement an application-owned layout adapter and initially evaluate Docling as the
  layout/table/OCR engine against the reviewed corpus;
- pin the selected version and model assets only after the corpus gate passes;
- retain `pypdf` as the fast native adapter;
- use OCRmyPDF/Tesseract preprocessing only if the corpus demonstrates a Docling OCR
  rotation/deskew gap worth the extra native dependency; and
- do not expose the candidate engine in production before deterministic packaging,
  limits, licensing and worker isolation are verified.

Backend work:

- detect media type from bytes in addition to declared type/extension;
- implement `native`, `layout_aware` and `auto` extraction profiles;
- calculate native extraction measurements per page;
- in Auto mode, choose layout/OCR fallback from recorded page-level rules;
- support `off`, `auto` and `always` OCR modes;
- add bounded OCR language selection, rotation, deskew, pixels, pages and timeouts;
- preserve headings, lists, columns, captions, footnotes, code and reading order;
- store native/OCR origin and engine confidence when supplied, without relabeling it as
  factual confidence;
- preserve structured tables plus deterministic Markdown/plain-text renderings;
- split/merge adapter output into the application IR and validate it before commit;
- sanitize parser warnings and retain safe finding codes; and
- fail or warn by saved quality policy rather than silently dropping bad pages.

Quality measurements:

- extracted characters and blocks per page;
- empty and OCR page ratios;
- replacement/control character ratio;
- repeated-line ratio;
- suspicious reading-order findings;
- table count and malformed-table findings;
- OCR confidence distribution when available; and
- extraction duration, peak bounded resource category and fallback path.

Frontend work:

- implement Extract controls and configured availability;
- mark blocks/pages as Native, Layout or OCR;
- render safe page thumbnails with selectable block overlays when available;
- show table structure beside its deterministic evidence rendering; and
- expose page-specific warnings and fallback reasons.

Tests:

- reviewed corpus: native PDF, image-only scan, mixed PDF, rotated/deskewed scan,
  two-column layout, repeated headers, lists, code, captions and simple/merged tables;
- password/encryption, malformed PDFs, image/pixel bombs and time/memory limits;
- cancellation between pages and stale-token commit prevention;
- deterministic output for pinned engine/model assets;
- fallback selection rules and `ocr=off` failure behavior; and
- isolated worker/container packaging plus clean install/build.

Exit gate:

- a mixed PDF succeeds with exact page-level native/OCR provenance;
- two-column reading order and reviewed tables meet the corpus thresholds in section 12;
- low-quality pages cannot silently publish; and
- the prior ready index remains current after any parser/OCR failure.

### Phase 3 — Deterministic structure-aware cleaning

Goal: clean noise without flattening semantic structure or hiding transformations.

Implement these typed transforms:

1. Unicode normalization, default NFC; NFKC is opt-in because it can change meaning.
2. Unsupported control-character removal with counts.
3. Conservative PDF line reflow inside compatible paragraph blocks only.
4. Conservative dehyphenation using line position and letter context; retain the
   original mapping.
5. Cross-page repeated header/footer detection using normalized text, position and
   configurable page-frequency threshold.
6. Empty/near-empty block removal.
7. Literal boilerplate removal for backward compatibility, scoped to block types.
8. Website include/exclude selectors using a bounded supported selector subset.
9. Website main-content and repeated-site-chrome handling using semantic DOM signals
   and cross-page fingerprints, including navigation and cookie/banner noise, with
   retained/removal reasons.
10. Preservation rules for tables, lists, code, quotes and footnotes.
11. Minimum/maximum useful-content validation after transforms.

Engine behavior:

- execute transforms in saved order;
- validate incompatible orderings at save time;
- each transform returns cleaned blocks, bounded change records and metrics;
- never mutate the extracted derivation;
- hash the ordered transform configuration;
- preserve block parentage through joins/splits;
- bound diff storage and reconstruct larger diffs on demand from immutable inputs; and
- mark source text as removed, never as nonexistent.

Frontend work:

- ordered accessible transform list with add/remove/reorder/enable controls;
- node/field validation from the server;
- before/after block diff with rule attribution;
- summary counts for removed headers, joined lines, dehyphenated words and retained
  protected blocks; and
- reset to a named server-supported profile without silently saving it.

Tests:

- transform unit tables with positive and negative examples;
- repeated header/footer precision across short and long documents;
- no dehyphenation across block/table/code boundaries;
- Unicode and multilingual preservation;
- transform ordering, hashing and incompatibility validation;
- Website selector security/limits and raw HTML non-execution;
- property invariants: no new unlabelled text, deterministic output and valid spans; and
- connector parity on the same canonical block fixture.

Exit gate:

- every visible change is attributable to a saved transform/version;
- the same transform config has identical semantics across sources; and
- reviewed cleaning precision meets section 12 thresholds.

### Phase 4 — Structure-aware and parent/child chunking

Goal: create retrieval passages from structure rather than arbitrary character cuts.

Algorithms:

- `character_window`: retained for compatibility;
- `section_token`: group compatible blocks under heading paths, split oversized groups
  by tokenizer-aware sentence/paragraph boundaries and enforce hard maximum tokens;
- `parent_child`: embed smaller child passages and return a saved larger parent section
  as evidence; and
- table chunking: keep small tables whole, split large tables by row groups and repeat
  title/header context deterministically.

Rules:

- tokenizers are registered by stable identity/version;
- target, maximum and overlap token bounds are server validated;
- no overlap-only trailing chunk;
- lists, code blocks and table rows are not split unless they exceed the hard maximum;
- title/heading context may be added to `embedding_text` only;
- `evidence_text` remains faithful and citation-safe;
- parent/child retrieval records both matched child and supplied parent;
- chunk spans remain ordered and exact; and
- changing only the chunk profile reuses a compatible cleaned derivation and source
  snapshot while producing a new index version.

Frontend work:

- algorithm-specific settings using discriminated forms;
- chunk preview with evidence text, embedding-only prefix, token counts, block spans,
  page/section and parent/child relationship;
- distribution summary for minimum/median/p95/maximum tokens and oversize findings; and
- explicit index-variant action from the same source snapshot.

Tests:

- tokenizer boundary and hard-limit tests;
- multilingual, long word, code, list and large-table fixtures;
- no lost/duplicated non-overlap source spans;
- embedding/evidence separation and citation correctness;
- parent/child retrieval and historical evidence snapshots;
- compatible derivation reuse with no refetch/re-extract; and
- retrieval regression set comparing character, section-token and parent/child.

Exit gate:

- every chunk is within its hard limit or has an explicit unsplittable-block finding;
- citations use faithful evidence, not enriched embedding text;
- multiple chunk/index variants can be built from one exact source snapshot; and
- measured retrieval quality is reported without automatically claiming a winner.

### Phase 5 — Quality policies, preview and run inspection

Goal: make quality decisions and every processing stage visible before publication.

Backend work:

- implement versioned policy definitions with typed thresholds;
- calculate item/document/run aggregates without hiding failed/excluded samples;
- distinguish `pass`, `warn`, `exclude` and `fail`;
- require an explicit saved warning-publication policy;
- implement expiring asynchronous preview using exact v2 config;
- add bounded block, diff, chunk, finding and metric pagination;
- record known extraction/OCR compute and cost basis; unknown cost is not zero; and
- allow reprocessing from stored immutable artifacts for all connectors, not Website
  only, when connector authorization and artifact retention allow it.

Default policy direction:

- fail on no useful text, corrupt structure, exceeded safety limits or required-page
  failure;
- exclude an optional source item only when the pipeline's source policy permits it;
- warn on bounded low-confidence OCR or suspicious reading order; and
- never infer overall factual correctness from extraction measurements.

Frontend work:

- synchronized Raw/Extracted/Cleaned/Chunks inspector;
- quality summary and page/item findings with remediation text;
- visible cached-artifact versus network-fetch preview mode;
- loading, empty, partial, failure, cancellation, expired-preview and retry states;
- per-item stage timing/cost and exact immutable version identifiers; and
- keyboard/mobile behavior following the existing master/detail workspace.

Tests:

- policy boundary tables and aggregation denominators;
- warning publication versus fail/exclude behavior;
- preview never embeds/publishes or advances current-ready pointers;
- preview expiration/retry/cancellation and stale polling;
- pagination and response-size bounds;
- untrusted HTML/document rendering security; and
- desktop, 200%-equivalent and mobile browser journeys.

Exit gate:

- a user can diagnose extraction and chunking before embedding;
- every published item has a visible quality decision;
- previews cannot alter durable retrieval state; and
- warnings/failures are represented accurately at item and run level.

### Phase 6 — Duplicate detection and language policy

Goal: reduce redundant embeddings and route language-sensitive extraction safely.

Duplicate processing:

- exact raw-content hash;
- exact cleaned-content hash;
- normalized block/section fingerprints;
- optional near-duplicate SimHash or MinHash with a saved threshold;
- comparison only within one project and configured destination/source snapshot;
- deterministic canonical selection using explicit priority: user-pinned source,
  connector priority, earliest stable identity, then lexical identity;
- retained/excluded item IDs, similarity method/value and reason;
- no silent deletion of duplicate source revisions; and
- an override creates a new pipeline/run decision, not mutation of history.

Language processing:

- detect document and page language with model/version and confidence;
- allow an optional language allowlist;
- select installed OCR language packs explicitly;
- support mixed-language warnings;
- never silently translate source text; and
- keep language metadata available to later retrieval filters without adding such a
  filter until measured.

Tests:

- exact copies, small template edits, mirror pages and legitimately similar policies;
- false-positive reviewed cases and stable canonical selection;
- project/destination isolation;
- multilingual and mixed-language fixtures;
- unavailable OCR language pack validation; and
- refresh behavior when the former canonical item is removed.

Exit gate:

- every excluded duplicate has an inspectable retained counterpart and reproducible
  decision; and
- language settings affect only documented extraction/OCR behavior.

### Phase 7 — Sensitive-data policy and additional formats

Goal: add separately approved controls after the core pipeline is measured and stable.

#### Phase 7A — Sensitive-data transforms

Before implementation, confirm threat model, authorization, retention and encryption.

- typed redact/drop rules by supported entity class;
- deterministic pattern detectors first, optional pinned NER adapter later;
- record entity type/count/location without returning the original sensitive value;
- protect raw artifacts and full diff access with server authorization;
- make irreversible redaction explicit for embedding/evidence output;
- never claim complete PII detection; and
- test false positives/negatives with synthetic data only.

#### Phase 7B — Additional document formats

Add one complete adapter at a time based on demonstrated user demand:

1. Markdown and HTML files;
2. DOCX;
3. PPTX;
4. CSV/TSV;
5. XLSX; then
6. other formats through an evaluated Apache Tika adapter if broad coverage justifies
   operating a Java parser boundary.

Each adapter must provide byte-level media detection, limits, structured IR mapping,
fixtures, provenance, preview, failure behavior and worker packaging. Do not advertise
format support based only on library capability.

Exit gate:

- each released policy/format passes the same end-to-end source → preview → run →
  index → answer/evidence workflow and security gates as existing sources.

### Phase 8 — Ingestion quality evaluation and operational hardening

Goal: prove quality, performance and recoverability before recommending profiles.

Golden corpus:

- reviewed native PDF;
- scan, rotated scan and mixed PDF;
- two-column PDF;
- simple and merged-cell tables;
- repeated headers/footers and footnotes;
- code, lists, multilingual and Unicode content;
- noisy Website pages;
- nested Notion and Confluence pages;
- exact and near duplicates; and
- malformed, encrypted and resource-limit fixtures.

Evaluation outputs:

- per-document expected blocks/order/tables/text spans;
- OCR ground truth for a bounded subset;
- expected removed/retained cleaning spans;
- reviewed chunk boundaries or boundary constraints;
- downstream question set with relevant source spans;
- per-profile latency, peak resource band, storage and known cost; and
- failures/skips reported alongside aggregates.

Operations:

- backup/restore of raw and derived artifacts plus relational metadata;
- retention/deletion design that protects historical indexes/experiments;
- storage-growth and reprocessing-cost dashboards or documented queries;
- worker capacity, OCR model installation and health diagnostics;
- stale derivation recovery and orphan inspection procedure;
- dependency/model upgrade procedure using golden-corpus comparison;
- rollback procedure that leaves v1 and previous v2 indexes queryable; and
- authorization tests before any shared deployment.

Exit gate:

- all section 12 release thresholds pass on a clean isolated stack;
- upgrade and rollback preserve populated historical data;
- critical browser journeys pass at canonical `http://127.0.0.1:5273`;
- documentation matches verified behavior and remaining limitations; and
- recommended profiles are based only on measured experiments under stated criteria.

## 11. Security and privacy requirements

- Treat files, HTML, OCR text, metadata, tables and parser warnings as untrusted.
- Never execute macros, embedded scripts, document actions, shell text or instructions
  found in content.
- Keep Website SSRF/DNS/redirect/origin limits unchanged.
- Detect actual media type and reject mismatches outside supported policy.
- Bound archive/decompression recursion before adding packaged formats.
- Bound PDF pages, images, pixels, object counts, characters, blocks, tables, cells,
  OCR time, memory and temporary storage.
- Do not log raw source text, OCR output, diffs, PII or credentials.
- Sanitize third-party exceptions into application error codes.
- Keep parser/OCR processes off the public network by default.
- Do not return raw local paths, commands or model locations through APIs.
- Require authentication/project authorization before shared access to raw previews,
  diffs or sensitive-data findings.
- Review licenses and redistribution terms for parser binaries and OCR/model assets.
- Run dependency and container security scans as release checks when the repository
  introduces that tooling; do not bypass failures to ship the feature.

## 12. Quality, performance and release thresholds

Finalize numeric thresholds from the initial golden-corpus baseline before Phase 2
implementation. The following are starting acceptance targets, not claims:

| Measure                       |                                                    Initial target | Aggregation and caveat                                             |
| ----------------------------- | ----------------------------------------------------------------: | ------------------------------------------------------------------ |
| Native text preservation      |                            ≥ 99.5% reviewed normalized characters | On supported native PDFs/TXT; normalization differences documented |
| OCR character error rate      |                                         ≤ 5% median and ≤ 12% p95 | Only pages with reviewed OCR ground truth; language reported       |
| Reading-order correctness     |                             ≥ 95% reviewed block precedence pairs | Corpus-specific; report failures, not only aggregate               |
| Table cell/header association |                                              ≥ 95% reviewed cells | Simple/declared supported tables; merged-cell limits stated        |
| Boilerplate removal precision |                                                             ≥ 99% | Body-text deletion is more costly than missed boilerplate          |
| Boilerplate removal recall    |                                                             ≥ 90% | Report by document template                                        |
| Chunk hard-limit compliance   |                             100% or explicit unsplittable finding | Never silently exceed model input assumptions                      |
| Source-span coverage          |                                       100% of evidence characters | Generated embedding prefixes excluded and labeled                  |
| Deterministic rerun           |                                              100% matching hashes | Same artifact/config/runtime/model assets                          |
| Retrieval quality             | No statistically/materially worse reviewed recall@k than baseline | Same source snapshot and questions; report sample size             |
| Publication integrity         |                                                       100% atomic | Failed/cancelled runs never replace current ready index            |

Also record p50/p95 extraction time, OCR time, memory band, output size and storage
growth by document class. Performance limits must cause explicit safe failures rather
than partial success.

## 13. Test strategy

### 13.1 Unit tests

- strict schema validation and canonical hashing;
- extractor selection and capability negotiation;
- quality measurements and policy decisions;
- every cleaning transform and negative preservation case;
- each chunk algorithm and tokenizer boundary;
- duplicate fingerprint/canonical selection; and
- safe error mapping/redaction.

### 13.2 Integration tests

- real PostgreSQL/pgvector and Alembic migrations;
- raw artifact → derivation → blocks → chunks → index provenance;
- exact project/source/document ownership constraints;
- worker duplicate delivery, cancellation, retries and stale fencing;
- compatible derivation/index reuse;
- atomic publication and previous-ready preservation;
- storage staging/cleanup and ambiguous-commit safety; and
- historical v1 pipeline/query/experiment reads.

### 13.3 Golden extraction tests

- commit small legally safe synthetic/reviewed fixtures;
- store expected semantic blocks/spans separately from parser output;
- compare structured results, not only a large text snapshot;
- allow explicit versioned expectation updates with a review report;
- fail default CI on unapproved quality regressions; and
- keep large/model-dependent OCR checks in a deterministic container job.

### 13.4 Frontend tests

- algorithm-specific form state and server error mapping;
- v1 upgrade-draft behavior and immutable version selection;
- preview status, expiry, cancellation and retry;
- paginated synchronized inspectors and safe rendering;
- loading/empty/partial/failure/warning states;
- dirty navigation and project switching; and
- mobile/keyboard/accessibility behavior.

### 13.5 Browser journeys

1. Upgrade a v1 Existing Files pipeline as a v2 draft, preview cleaning, save, run and
   inspect exact block/chunk lineage.
2. Ingest a mixed PDF with Auto OCR, inspect native/OCR pages and publish a ready
   index.
3. Preview a two-column/table PDF, adjust settings, verify the preview does not publish,
   then run and retrieve cited evidence.
4. Build character and section-token variants from one source snapshot without
   refetching; compare them on the same reviewed questions.
5. Trigger low-quality fail, warning publication, cancellation during OCR and stale
   recovery; verify the previous ready index remains current.
6. Detect a near duplicate, inspect the retained counterpart, rerun with an explicit
   policy change and preserve both histories.
7. Verify Website/Notion/Confluence hierarchy and cleaning parity.
8. Re-run existing answer, Playground and experiment regressions against historical
   v1 and new v2 indexes.

## 14. Observability and cost

Persist bounded metrics keyed by project/run/item/derivation IDs:

- queue, extraction, cleaning, chunking, embedding and publication duration;
- pages/blocks/tables/characters before and after cleaning;
- native/OCR/fallback page counts;
- warning/failure codes;
- chunks and token-size distribution;
- cache/derivation/embedding reuse counts;
- known local compute estimates and external provider costs with pricing basis; and
- unknown cost as unknown, never zero.

Logs remain text-free and use correlation IDs. Metrics must not include filenames or
canonical locations when those may contain personal data.

## 15. Rollout and rollback

### Rollout order

1. Deploy additive migrations.
2. Deploy backend/worker support for both v1 and v2.
3. Verify v1 regression and clean v2 smoke tests.
4. Deploy frontend v2 creation/upgrade/inspection.
5. Keep new extractor profiles feature-disabled until worker dependencies and corpus
   gates pass.
6. Enable per development project, then for explicitly selected local projects.
7. Observe failure/resource metrics before widening availability.

### Rollback

- frontend rollback hides v2 authoring but must not delete v2 records;
- backend rollback is supported only to a version that can read or safely ignore the
  additive v2 records;
- never downgrade by rewriting a v2 pipeline as v1;
- previous ready indexes remain selected and queryable;
- interrupted v2 runs are fenced/cancelled by the compatible dispatcher; and
- destructive removal of derivations/blocks is not part of routine rollback.

## 16. Risks and mitigations

| Risk                                               | Mitigation                                                                                               |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Layout/OCR dependency is large or nondeterministic | Isolated pinned adapter, fixed model assets, golden corpus and resource limits                           |
| Automatic cleanup removes useful text              | Conservative defaults, high precision gate, before/after audit and warning rollout                       |
| IR/persistence grows rapidly                       | Bounded blocks/attributes, paginated reads, artifact storage for full representations and retention plan |
| Old pipelines change behavior                      | Separate v1 executor and explicit upgrade-as-draft                                                       |
| OCR makes ingestion slow/expensive                 | Native-first Auto policy, page-level fallback, cache by content/config and visible cost/time             |
| Near-dedup hides legitimate sources                | Opt-in threshold, project scope, explicit canonical item and reversible future run policy                |
| Enriched text contaminates citations               | Separate embedding/evidence fields and citation tests                                                    |
| Connector behavior drifts                          | One canonical cleaner/chunker plus parity fixtures                                                       |
| Parser exploit or resource bomb                    | Worker isolation, strict bounds, no network by default and security review                               |
| Quality score is mistaken for truth                | Expose measurements/findings and policy outcome, never “confidence” or certification                     |

## 17. Explicit non-goals for the core phases

- Arbitrary DAG execution or user-supplied code.
- Arbitrary regex replacement in the initial cleaner.
- JavaScript/browser-rendered Website crawling.
- Automatic source translation.
- Image caption generation or general vision understanding.
- Audio/video transcription.
- LLM rewriting, summarization or metadata generation.
- Claiming OCR/extraction quality guarantees outside the reviewed corpus.
- Automatically switching saved answer pipelines to a new index.
- Silent best-effort publication with failed required sources.
- Deleting raw or historical artifacts without an approved retention/deletion design.

## 18. Later LLM enrichment boundary

If measured deterministic extraction leaves a demonstrated need, LLM enrichment can be
planned separately. It must:

- operate after faithful extraction and before optional embedding enrichment;
- never replace stored original/evidence text;
- label every generated field;
- snapshot model, provider, prompt, parameters and response metadata;
- use untrusted-content prompt boundaries;
- be cancellable, rate-limited, costed and retry-bounded;
- support unavailable/failed outputs without inventing values; and
- be evaluated against a human-reviewed set before release.

## 19. Phase completion checklist

Every phase must finish with:

- implemented UI/API/persistence/worker path for only that phase;
- strict validation and safe errors;
- migrations checked on clean and populated databases when applicable;
- relevant backend Ruff format/lint and PostgreSQL tests;
- frontend formatting, lint, strict typecheck, Vitest and production build;
- affected deterministic browser journeys on `http://127.0.0.1:5273`;
- security/resource-bound tests for new parsers or transforms;
- actual results and limitations recorded in `docs/implementation-plan.md`;
- implemented architectural decisions recorded in `docs/architecture.md`;
- operational/deployment changes recorded in the relevant docs; and
- a handoff that names the next phase without beginning it.

## 20. Recommended first implementation slice

Implement Phase 0 only. It corrects current semantic gaps, creates the shared boundary
needed by every later feature and carries the lowest dependency risk. Do not introduce
Docling/OCR, new persistence tables or semantic chunking until Phase 0 parity and v1
reproducibility pass.

Suggested implementation prompt:

```text
Implement Phase 0 only from docs/robust-ingestion-plan.md.

Read AGENTS.md, the existing ingestion plan, architecture and current implementation;
inspect Git status and preserve unrelated work. Freeze schema-v1 behavior with tests,
introduce the shared current-behavior extractor/cleaner/chunker boundary, remove
connector-specific general cleaning duplication, make schema-v2 Existing Files execute
its saved clean configuration, add strict v2 validation and an explicit frontend
upgrade-as-draft flow. Do not add OCR, Docling, new derivation tables, semantic
chunking, near-duplicate detection or PII processing.

Verify v1 output compatibility, v2 connector cleaning parity, cancellation/recovery,
project isolation, migrations, frontend checks and affected deterministic browser
journeys. Record actual results in docs/implementation-plan.md and implemented
decisions in docs/architecture.md, report the Phase 1 handoff and stop.
```

## 21. Primary implementation references

Re-check the current official documentation and pin compatible versions when the
relevant phase begins:

- [pypdf text extraction and OCR limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
- [Docling CLI extraction, OCR and table options](https://docling-project.github.io/docling/reference/cli/)
- [OCRmyPDF processing modes and advanced options](https://ocrmypdf.readthedocs.io/en/stable/advanced.html)
- [Apache Tika documentation and parser boundary](https://tika.apache.org/docs/)
- [Celery task acknowledgement and retry behavior](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
