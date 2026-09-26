---
verified_against: "OpenAPI SHA-256 1237e6ca1816bbbde889c9a991668b9540326c4e26a77c5b9fbc2ba053206d1c (2026-09-26)"
title: Schema models
slug: /api/schema-models/
---

Inspect generated model fields and bounds before submitting a request. Start the [local API](../start/install.md), then use `curl --fail http://127.0.0.1:8000/openapi.json -o /tmp/rag-quality-studio-openapi.json` to compare the running contract with this [checked schema](/openapi.json). Expected result: the same component names and constraints. If the server differs, use its live schema and review the application version before sending a write.

This page is generated from FastAPI/Pydantic; project authorization, provider cost and workflow order need the [API overview](./overview.md), [patterns](./patterns.md), and [task guides](../start/index.md). A schema field does not imply a live external integration has been verified.

## Answer

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |

## Body_preview_api_projects__project_id__datasets_preview_post

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `file` | string (binary) | yes | — |

## Body_upload_api_projects__project_id__datasets_post

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `file` | string (binary) | yes | — |
| `name` | string | yes | — |
| `content_hash` | string | yes | — |
| `dataset_id` | string (uuid) or null | no | — |

## Body_upload_api_projects__project_id__documents_post

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `files` | array of string (binary) | yes | — |

## CharacterChunkNodeV2

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `algorithm` | string | no | default=character_window |
| `unit` | string | no | default=characters |
| `size` | integer | yes | minimum=100.0, maximum=10000.0 |
| `overlap` | integer | yes | minimum=0.0, maximum=9999.0 |
| `config_version` | string | no | default=character-window-v1 |

## ChunkBlockSpanList

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`ChunkBlockSpanRead`](#chunkblockspanread) | yes | — |
| `total` | integer | yes | — |

## ChunkBlockSpanRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `run_id` | string (uuid) | yes | — |
| `chunk_ordinal` | integer | yes | — |
| `span_ordinal` | integer | yes | — |
| `derivation_id` | string (uuid) | yes | — |
| `derivation_kind` | string | yes | — |
| `block_ordinal` | integer | yes | — |
| `block_start_char` | integer | yes | — |
| `block_end_char` | integer | yes | — |
| `chunk_start_char` | integer | yes | — |
| `chunk_end_char` | integer | yes | — |

## ChunkDistributionRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `minimum` | integer or null | yes | — |
| `median` | number or null | yes | — |
| `p95` | integer or null | yes | — |
| `maximum` | integer or null | yes | — |
| `indexed_count` | integer | yes | — |
| `stored_count` | integer | yes | — |
| `parent_count` | integer | yes | — |
| `oversize_finding_count` | integer | yes | — |

## ChunkInspectionPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`ChunkInspectionRead`](#chunkinspectionread) | yes | — |
| `summary` | [`ChunkDistributionRead`](#chunkdistributionread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## ChunkInspectionRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `run_id` | string (uuid) | yes | — |
| `ordinal` | integer | yes | — |
| `page_number` | integer or null | yes | — |
| `start_char` | integer | yes | — |
| `end_char` | integer | yes | — |
| `evidence_text` | string | yes | — |
| `embedding_text` | string | yes | — |
| `embedding_prefix` | string | yes | — |
| `token_count` | integer or null | yes | — |
| `embedding_token_count` | integer or null | yes | — |
| `chunk_role` | string: leaf, parent, child | yes | — |
| `parent_ordinal` | integer or null | yes | — |
| `section_path` | array of string | no | — |
| `findings` | array of object | no | — |
| `spans` | array of [`ChunkBlockSpanRead`](#chunkblockspanread) | no | — |

## ChunkPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`ChunkRead`](#chunkread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## ChunkRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `ordinal` | integer | yes | — |
| `page_number` | integer or null | yes | — |
| `start_char` | integer | yes | — |
| `end_char` | integer | yes | — |
| `text` | string | yes | — |

## ChunkingProfileCapability

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string: character_window, section_token, parent_child | yes | — |
| `name` | string | yes | — |
| `description` | string | yes | — |
| `recommended` | boolean | yes | — |
| `settings` | object | yes | — |

## CleanNodeV2

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `normalize_whitespace` | boolean | no | default=True |
| `repeated_boilerplate` | array of string | no | maxItems=50 |
| `minimum_text_chars` | integer | no | minimum=1.0, maximum=100000.0, default=1 |
| `maximum_text_chars` | integer | no | minimum=1.0, maximum=2000000.0, default=2000000 |
| `exact_content_deduplication` | boolean | no | default=True |
| `profile` | string: standard-v1, structure-aware-v1 | no | default=standard-v1 |
| `config_version` | string: deterministic-clean-v1, structure-clean-v1 | no | default=deterministic-clean-v1 |
| `steps` | array of [`PreserveStructureTransform`](#preservestructuretransform) or [`UnicodeNormalizeTransform`](#unicodenormalizetransform) or [`RemoveControlCharactersTransform`](#removecontrolcharacterstransform) or [`ReflowPdfLinesTransform`](#reflowpdflinestransform) or [`DehyphenateTransform`](#dehyphenatetransform) or [`RemoveRepeatedHeadersFootersTransform`](#removerepeatedheadersfooterstransform) or [`RemoveEmptyBlocksTransform`](#removeemptyblockstransform) or [`RemoveLiteralBoilerplateTransform`](#removeliteralboilerplatetransform) or [`WebsiteSelectorsTransform`](#websiteselectorstransform) or [`WebsiteMainContentTransform`](#websitemaincontenttransform) or [`ValidateUsefulContentTransform`](#validateusefulcontenttransform) | no | maxItems=20 |
| `duplicate_policy` | [`DuplicatePolicyV1`](#duplicatepolicyv1) | no | — |
| `sensitive_data_policy` | [`SensitiveDataPolicyV1`](#sensitivedatapolicyv1) | no | — |

## CleaningDiffPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`CleaningDiffRead`](#cleaningdiffread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## CleaningDiffRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `block_id` | string | yes | — |
| `block_type` | string | yes | — |
| `page_number` | integer or null | yes | — |
| `before_text` | string | yes | — |
| `after_text` | string or null | yes | — |
| `action` | string: unchanged, rewritten, removed | yes | — |
| `transforms` | array of string | yes | — |
| `reasons` | array of string | yes | — |

## CleaningProfileCapability

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | — |
| `name` | string | yes | — |
| `config_version` | string | yes | — |
| `steps` | array of [`PreserveStructureTransform`](#preservestructuretransform) or [`UnicodeNormalizeTransform`](#unicodenormalizetransform) or [`RemoveControlCharactersTransform`](#removecontrolcharacterstransform) or [`ReflowPdfLinesTransform`](#reflowpdflinestransform) or [`DehyphenateTransform`](#dehyphenatetransform) or [`RemoveRepeatedHeadersFootersTransform`](#removerepeatedheadersfooterstransform) or [`RemoveEmptyBlocksTransform`](#removeemptyblockstransform) or [`RemoveLiteralBoilerplateTransform`](#removeliteralboilerplatetransform) or [`WebsiteSelectorsTransform`](#websiteselectorstransform) or [`WebsiteMainContentTransform`](#websitemaincontenttransform) or [`ValidateUsefulContentTransform`](#validateusefulcontenttransform) | yes | — |

## ConfluenceConfig

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `connection_id` | string (uuid) | yes | — |
| `selection` | [`ConfluenceSiteSelection`](#confluencesiteselection) or [`ConfluenceSpaceSelection`](#confluencespaceselection) or [`ConfluencePageSelection`](#confluencepageselection) | yes | — |
| `title_prefixes` | array of string | no | maxItems=50 |
| `exclude_title_prefixes` | array of string | no | maxItems=50 |
| `label_ids` | array of string | no | maxItems=50 |
| `max_pages` | integer | no | minimum=1.0, maximum=5000.0, default=500 |
| `max_api_pages` | integer | no | minimum=1.0, maximum=500.0, default=100 |
| `max_response_bytes` | integer | no | minimum=1024.0, maximum=10485760.0, default=2097152 |
| `max_text_chars` | integer | no | minimum=100.0, maximum=2000000.0, default=2000000 |
| `request_timeout_seconds` | number | no | minimum=1.0, maximum=60.0, default=30 |

## ConfluenceCredentials

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `site_url` | string (uri) | yes | minLength=1, maxLength=2083 |
| `email` | string (password) | yes | minLength=3, maxLength=320 |
| `api_token` | string (password) | yes | minLength=1, maxLength=4096 |

## ConfluenceIngestionRunItemRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `source_kind` | string | no | default=confluence |
| `ordinal` | integer | yes | — |
| `source_node_id` | string | yes | — |
| `source_item_id` | string (uuid) or null | yes | — |
| `source_revision_id` | string (uuid) or null | yes | — |
| `processing_run_id` | string (uuid) or null | no | — |
| `canonical_location` | string or null | yes | — |
| `display_name` | string | yes | — |
| `media_type` | string or null | yes | — |
| `outcome` | string: new, changed, unchanged, removed, excluded, duplicate, failed | yes | — |
| `status` | string: ready, succeeded, failed, cancelled | yes | — |
| `reason` | string | yes | — |
| `chunk_count` | integer | yes | — |
| `error` | string or null | yes | — |
| `processing_versions` | object or null | no | — |
| `duplicate_decision` | object or null | no | — |
| `updated_at` | string (date-time) | yes | — |

## ConfluencePageSelection

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `mode` | string | yes | — |
| `page_ids` | array of string | yes | minItems=1, maxItems=1000 |

## ConfluenceSiteSelection

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `mode` | string | yes | — |

## ConfluenceSpaceSelection

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `mode` | string | yes | — |
| `space_ids` | array of string | yes | minItems=1, maxItems=100 |

## ContentBlockPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`ContentBlockRead`](#contentblockread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## ContentBlockRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `derivation_id` | string (uuid) | yes | — |
| `ordinal` | integer | yes | — |
| `block_id` | string | yes | — |
| `block_type` | string | yes | — |
| `text` | string | yes | — |
| `page_number` | integer or null | yes | — |
| `bounding_box` | object or null | yes | — |
| `heading_path` | array of string | yes | — |
| `source_span` | object | yes | — |
| `attributes` | object | yes | — |

## ContentDerivationList

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`ContentDerivationRead`](#contentderivationread) | yes | — |
| `total` | integer | yes | — |

## ContentDerivationRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `document_id` | string (uuid) | yes | — |
| `processing_run_id` | string (uuid) | yes | — |
| `kind` | string: extracted, cleaned | yes | — |
| `schema_version` | integer | yes | — |
| `engine_version` | string | yes | — |
| `configuration_hash` | string | yes | — |
| `input_hash` | string | yes | — |
| `output_hash` | string | yes | — |
| `title` | string or null | yes | — |
| `media_type` | string | yes | — |
| `language` | object or null | no | — |
| `pages` | array of object | no | — |
| `measurements` | object | yes | — |
| `findings` | array of object | yes | — |
| `sensitive_findings` | array of object | no | — |
| `sensitive_data_applied` | boolean | no | default=False |
| `protected_text` | boolean | no | default=False |
| `transforms` | array of object | yes | — |
| `created_at` | string (date-time) | yes | — |

## CrawlSelection

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `mode` | string | yes | — |
| `start_url` | string (uri) | yes | minLength=1 |

## DailyCadence

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `local_time` | string (time) | yes | — |
| `timezone` | string | yes | minLength=1, maxLength=100 |

## DatasetRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `dataset_id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `name` | string | yes | — |
| `version` | integer | yes | — |
| `content_hash` | string | yes | — |
| `rows` | array of object | yes | — |
| `created_at` | string (date-time) | yes | — |

## DefaultQualityPolicyV1

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | no | default=default-v1 |
| `thresholds` | [`QualityThresholdsV1`](#qualitythresholdsv1) | no | — |
| `warning_action` | string: publish, fail | yes | — |
| `failed_item_action` | string: fail, exclude | no | default=fail |

## DehyphenateTransform

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `enabled` | boolean | no | default=True |
| `type` | string | yes | — |
| `mode` | string | no | default=conservative |

## DocumentPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`DocumentRead`](#documentread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## DocumentRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `filename` | string | yes | — |
| `media_type` | string | yes | — |
| `content_hash` | string | yes | — |
| `size_bytes` | integer | yes | — |
| `artifact_state` | string: legacy_plaintext, encrypted, deleting, deleted | yes | — |
| `raw_retained_until` | string (date-time) or null | yes | — |
| `raw_deleted_at` | string (date-time) or null | yes | — |
| `created_at` | string (date-time) | yes | — |
| `latest_run` | [`RunRead`](#runread) or null | no | — |

## DuplicatePolicyV1

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | no | default=duplicate-v1 |
| `exact_raw` | boolean | no | default=True |
| `exact_cleaned` | boolean | no | default=True |
| `normalized_sections` | boolean | no | default=True |
| `near_duplicate` | boolean | no | default=False |
| `near_duplicate_method` | string | no | default=simhash64 |
| `near_duplicate_threshold` | number | no | minimum=0.75, maximum=1.0, default=0.92 |
| `pinned_canonical_locations` | array of string | no | maxItems=100 |
| `connector_priority` | array of string: existing_files, website, s3, notion, confluence | no | minItems=5, maxItems=5 |

## Edge

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `source` | string | yes | — |
| `target` | string | yes | — |

## EmbedNode

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `provider` | string | yes | minLength=1, maxLength=80 |
| `model` | string | yes | minLength=1, maxLength=200 |
| `dimensions` | integer | yes | minimum=1.0, maximum=16000.0 |
| `config_version` | string | yes | minLength=1, maxLength=40 |

## EmbeddingConfig

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `provider` | string | yes | — |
| `model` | string | yes | minLength=1, maxLength=200 |
| `dimensions` | integer | yes | minimum=1.0, maximum=16000.0 |
| `endpoint_id` | string | yes | — |
| `revision` | string | no | default=1 |

## Evidence

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `rank` | integer | yes | — |
| `document_id` | string (uuid) | yes | — |
| `filename` | string | yes | — |
| `content_hash` | string | yes | — |
| `run_id` | string (uuid) | yes | — |
| `processing_version` | integer | yes | — |
| `ordinal` | integer | yes | — |
| `matched_chunk_ordinal` | integer | yes | — |
| `matched_text` | string | yes | — |
| `supplied_parent_ordinal` | integer or null | no | — |
| `page_number` | integer or null | yes | — |
| `start_char` | integer | yes | — |
| `end_char` | integer | yes | — |
| `text` | string | yes | — |
| `source_url` | string or null | no | — |
| `section_path` | array of string | no | — |
| `chunk_role` | string: leaf, child | yes | — |
| `token_count` | integer or null | no | — |
| `cosine_distance` | number or null | no | — |
| `lexical_score` | number or null | no | — |
| `fusion_score` | number or null | no | — |
| `vector_rank` | integer or null | no | — |
| `keyword_rank` | integer or null | no | — |

## Execution

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `schema_version` | integer: 1, 2 | yes | — |
| `nodes` | array of [`Question`](#question) or [`Retriever`](#retriever) or [`Prompt`](#prompt) or [`LLM`](#llm) or [`Answer`](#answer) | yes | minItems=5, maxItems=5 |
| `edges` | array of [`Edge`](#edge) | yes | minItems=4, maxItems=4 |

## ExistingFilesConfig

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `document_ids` | array of string (uuid) | yes | minItems=1, maxItems=1000 |
| `optional_document_ids` | array of string (uuid) | no | maxItems=1000 |

## ExistingIndexDestination

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `knowledge_set_id` | string (uuid) | yes | — |

## ExistingIngestionRunItemRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `source_kind` | string | no | default=existing_files |
| `document_id` | string (uuid) | yes | — |
| `filename` | string | yes | — |
| `content_hash` | string | yes | — |
| `media_type` | string | yes | — |
| `source_node_id` | string | yes | — |
| `processing_run_id` | string (uuid) | yes | — |
| `processing_version` | integer | yes | — |
| `processing_created` | boolean | yes | — |
| `is_optional` | boolean | no | default=False |
| `status` | string: processing, ready, succeeded, excluded, failed, cancelled | yes | — |
| `chunk_count` | integer | yes | — |
| `error` | string or null | yes | — |
| `processing_versions` | object or null | no | — |
| `duplicate_decision` | object or null | no | — |
| `updated_at` | string (date-time) | yes | — |

## ExperimentCreate

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `name` | string | yes | minLength=1, maxLength=120 |
| `dataset_version_id` | string (uuid) | yes | — |
| `pipeline_version_ids` | array of string (uuid) | yes | minItems=1, maxItems=2 |
| `metrics` | array of string: faithfulness, response_relevancy, context_recall | yes | minItems=1, maxItems=3 |

## ExperimentRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `dataset_version_id` | string (uuid) | yes | — |
| `name` | string | yes | — |
| `status` | string | yes | — |
| `snapshot` | object | yes | — |
| `progress` | integer | yes | — |
| `total` | integer | yes | — |
| `cancel_requested` | boolean | yes | — |
| `error` | string or null | yes | — |
| `created_at` | string (date-time) | yes | — |

## ExtractNodeV2

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `strategy` | string: native_text, auto, native, layout_aware | no | default=native_text |
| `ocr` | [`OcrSettingsV1`](#ocrsettingsv1) | no | — |
| `tables` | string: preserve, markdown, plain_text | no | default=preserve |
| `quality_policy` | [`DefaultQualityPolicyV1`](#defaultqualitypolicyv1) or [`StrictQualityPolicyV1`](#strictqualitypolicyv1) or [`WarnQualityPolicyV1`](#warnqualitypolicyv1) or string: default-v1, strict-v1, warn-v1 | no | default=default-v1 |
| `language_policy` | [`LanguagePolicyV1`](#languagepolicyv1) | no | — |
| `config_version` | string: native-text-v1, layout-ocr-v1 | no | default=native-text-v1 |

## ExtractionCapabilities

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `schema_version` | integer | yes | — |
| `media_types` | array of string | yes | — |
| `profiles` | array of [`ExtractionProfileCapability`](#extractionprofilecapability) | yes | — |
| `ocr` | [`OcrCapability`](#ocrcapability) | yes | — |
| `table_modes` | array of string: preserve, markdown, plain_text | yes | — |
| `quality_policies` | array of [`QualityPolicyCapability`](#qualitypolicycapability) | yes | — |
| `cleaning_profiles` | array of [`CleaningProfileCapability`](#cleaningprofilecapability) | yes | — |
| `tokenizers` | array of [`TokenizerCapability`](#tokenizercapability) | yes | — |
| `chunking_profiles` | array of [`ChunkingProfileCapability`](#chunkingprofilecapability) | yes | — |

## ExtractionProfileCapability

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string: auto, native, layout_aware | yes | — |
| `available` | boolean | yes | — |
| `reason` | string or null | yes | — |

## HTTPValidationError

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `detail` | array of [`ValidationError`](#validationerror) | no | — |

## HybridSearch

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `top_k` | integer | no | minimum=1.0, maximum=50.0, default=5 |
| `mode` | string | yes | — |
| `max_vector_distance` | number or null | no | — |
| `vector_candidates` | integer | no | minimum=1.0, maximum=200.0, default=50 |
| `keyword_candidates` | integer | no | minimum=1.0, maximum=200.0, default=50 |
| `vector_weight` | number | no | minimum=0.0, maximum=1.0, default=0.5 |

## IndexCreate

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `knowledge_set_id` | string (uuid) or null | no | — |
| `document_ids` | array of string (uuid) or null | no | — |

## IndexPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`IndexRead`](#indexread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## IndexRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `knowledge_set_id` | string (uuid) | yes | — |
| `knowledge_set_name` | string | yes | — |
| `version` | integer | yes | — |
| `embedding_config` | [`EmbeddingConfig`](#embeddingconfig) | yes | — |
| `status` | string: queued, running, succeeded, failed, cancelled | yes | — |
| `chunk_count` | integer | yes | — |
| `embedded_count` | integer | yes | — |
| `attempts` | integer | yes | — |
| `failures` | integer | yes | — |
| `processing_run_count` | integer | yes | — |
| `is_current` | boolean | yes | — |
| `source_snapshot_id` | string (uuid) or null | no | — |
| `source_snapshot_number` | integer or null | no | — |
| `source_snapshot_collected_at` | string (date-time) or null | no | — |
| `ingestion_pipeline_id` | string (uuid) or null | no | — |
| `ingestion_pipeline_name` | string or null | no | — |
| `ingestion_pipeline_version` | integer or null | no | — |
| `chunk_size` | integer or null | no | — |
| `chunk_overlap` | integer or null | no | — |
| `error` | string or null | yes | — |
| `created_at` | string (date-time) | yes | — |

## IndexRecordPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`IndexRecordRead`](#indexrecordread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## IndexRecordRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `run_id` | string (uuid) | yes | — |
| `ordinal` | integer | yes | — |
| `document_id` | string (uuid) | yes | — |
| `filename` | string | yes | — |
| `processing_version` | integer | yes | — |
| `page_number` | integer or null | yes | — |
| `start_char` | integer | yes | — |
| `end_char` | integer | yes | — |
| `text` | string | yes | — |
| `embedding_text` | string | yes | — |
| `token_count` | integer or null | no | — |
| `embedding_token_count` | integer or null | no | — |
| `chunk_role` | string: leaf, child | yes | — |
| `parent_ordinal` | integer or null | no | — |
| `findings` | array of object | no | — |
| `embedding_prefix` | string | no | default= |
| `source_url` | string or null | no | — |
| `section_path` | array of string | no | — |
| `dimensions` | integer | yes | — |
| `embedded` | boolean | yes | — |
| `embedding_norm` | number or null | yes | — |
| `embedding_preview` | array of number | no | — |

## IngestionEdge

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `source` | string | yes | minLength=1, maxLength=80 |
| `target` | string | yes | minLength=1, maxLength=80 |

## IngestionExecution

Type: [`IngestionExecutionV1`](#ingestionexecutionv1) or [`IngestionExecutionV2`](#ingestionexecutionv2).

## IngestionExecutionV1

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `schema_version` | integer | yes | — |
| `nodes` | array of [`SourceNode`](#sourcenode) or [`LegacyExtractNode`](#legacyextractnode) or [`LegacyCleanNode`](#legacycleannode) or [`LegacyChunkNode`](#legacychunknode) or [`EmbedNode`](#embednode) or [`PublishIndexNode`](#publishindexnode) | yes | minItems=6, maxItems=15 |
| `edges` | array of [`IngestionEdge`](#ingestionedge) | yes | minItems=5, maxItems=14 |

## IngestionExecutionV2

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `schema_version` | integer | yes | — |
| `nodes` | array of [`SourceNode`](#sourcenode) or [`ExtractNodeV2`](#extractnodev2) or [`CleanNodeV2`](#cleannodev2) or [`CharacterChunkNodeV2`](#characterchunknodev2) or [`SectionTokenChunkNodeV2`](#sectiontokenchunknodev2) or [`ParentChildChunkNodeV2`](#parentchildchunknodev2) or [`EmbedNode`](#embednode) or [`PublishIndexNode`](#publishindexnode) | yes | minItems=6, maxItems=15 |
| `edges` | array of [`IngestionEdge`](#ingestionedge) | yes | minItems=5, maxItems=14 |

## IngestionLayout

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `positions` | object | yes | — |

## IngestionPipelineSave

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `name` | string | yes | minLength=1, maxLength=120 |
| `execution` | [`IngestionExecution`](#ingestionexecution) | yes | — |
| `layout` | [`IngestionLayout`](#ingestionlayout) | yes | — |

## IngestionPosition

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `x` | number | yes | minimum=-100000.0, maximum=100000.0 |
| `y` | number | yes | minimum=-100000.0, maximum=100000.0 |

## IngestionPreviewRequest

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `execution` | [`IngestionExecution`](#ingestionexecution) | yes | — |

## IngestionRunItemPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`ExistingIngestionRunItemRead`](#existingingestionrunitemread) or [`WebsiteIngestionRunItemRead`](#websiteingestionrunitemread) or [`S3IngestionRunItemRead`](#s3ingestionrunitemread) or [`NotionIngestionRunItemRead`](#notioningestionrunitemread) or [`ConfluenceIngestionRunItemRead`](#confluenceingestionrunitemread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## IngestionRunNodeRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `node_id` | string | yes | — |
| `node_type` | string: source, extract, clean, chunk, embed, publish_index | yes | — |
| `ordinal` | integer | yes | — |
| `status` | string: queued, running, succeeded, failed, cancelled | yes | — |
| `started_at` | string (date-time) or null | yes | — |
| `finished_at` | string (date-time) or null | yes | — |

## IngestionRunPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`IngestionRunRead`](#ingestionrunread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## IngestionRunRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `pipeline_version_id` | string (uuid) | yes | — |
| `knowledge_set_id` | string (uuid) | yes | — |
| `schedule_id` | string (uuid) or null | yes | — |
| `source_snapshot_id` | string (uuid) or null | yes | — |
| `trigger_kind` | string: manual, scheduled | yes | — |
| `knowledge_set_name` | string | yes | — |
| `status` | string: queued, running, succeeded, failed, cancelled | yes | — |
| `stage` | string: discovering, processing, indexing, complete | yes | — |
| `progress` | integer | yes | — |
| `discovered_count` | integer | yes | — |
| `processed_count` | integer | yes | — |
| `failed_count` | integer | yes | — |
| `new_count` | integer | no | default=0 |
| `changed_count` | integer | no | default=0 |
| `unchanged_count` | integer | no | default=0 |
| `removed_count` | integer | no | default=0 |
| `chunk_count` | integer | yes | — |
| `embedded_count` | integer | yes | — |
| `published_count` | integer | yes | — |
| `attempts` | integer | yes | — |
| `failures` | integer | yes | — |
| `node_states` | array of [`IngestionRunNodeRead`](#ingestionrunnoderead) | yes | — |
| `error` | string or null | yes | — |
| `published_index_id` | string (uuid) or null | yes | — |
| `published_index_version` | integer or null | yes | — |
| `created_at` | string (date-time) | yes | — |
| `updated_at` | string (date-time) | yes | — |
| `started_at` | string (date-time) or null | yes | — |
| `finished_at` | string (date-time) or null | yes | — |

## IngestionRunStart

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `source_input` | [`RefreshSourceInput`](#refreshsourceinput) or [`SnapshotSourceInput`](#snapshotsourceinput) or null | no | — |
| `destination` | [`ExistingIndexDestination`](#existingindexdestination) or [`NewIndexDestination`](#newindexdestination) or null | no | — |
| `reuse_stored` | boolean or null | no | — |

## IntervalCadence

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `minutes` | integer | yes | minimum=15.0, maximum=10080.0 |

## KeywordSearch

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `top_k` | integer | no | minimum=1.0, maximum=50.0, default=5 |
| `mode` | string | yes | — |

## KnowledgeSetPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`KnowledgeSetRead`](#knowledgesetread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## KnowledgeSetRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `name` | string | yes | — |
| `current_ready_index_id` | string (uuid) or null | yes | — |
| `created_at` | string (date-time) | yes | — |

## LLM

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `model` | string | yes | minLength=1, maxLength=200 |
| `max_tokens` | integer | yes | minimum=128.0, maximum=8192.0 |
| `temperature` | number | yes | minimum=0.0, maximum=2.0 |

## LanguagePolicyV1

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | no | default=language-v1 |
| `detection_model` | string | no | default=deterministic-script-v1 |
| `allowlist` | array of string | no | maxItems=20 |
| `minimum_confidence` | number | no | minimum=0.0, maximum=1.0, default=0 |
| `disallowed_action` | string: fail, exclude | no | default=fail |
| `mixed_language_action` | string: allow, warn, fail | no | default=warn |

## Layout

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `positions` | object | yes | — |

## LegacyChunkNode

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `algorithm` | string | no | default=character_window |
| `unit` | string | no | default=characters |
| `size` | integer | yes | minimum=100.0, maximum=10000.0 |
| `overlap` | integer | yes | minimum=0.0, maximum=9999.0 |
| `config_version` | string | no | minLength=1, maxLength=40, default=1 |

## LegacyCleanNode

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `normalize_whitespace` | boolean | no | default=True |
| `repeated_boilerplate` | array of string | no | maxItems=50 |
| `minimum_text_chars` | integer | no | minimum=1.0, maximum=100000.0, default=1 |
| `maximum_text_chars` | integer | no | minimum=1.0, maximum=2000000.0, default=2000000 |
| `exact_content_deduplication` | boolean | no | default=True |

## LegacyExtractNode

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `strategy` | string | no | default=media_type_registry |
| `config_version` | string | no | minLength=1, maxLength=40, default=1 |

## NewIndexDestination

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `name` | string | yes | minLength=1, maxLength=120 |

## NotionConfig

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `connection_id` | string (uuid) | yes | — |
| `selection` | [`NotionWorkspaceSelection`](#notionworkspaceselection) or [`NotionPageSelection`](#notionpageselection) or [`NotionDataSourceSelection`](#notiondatasourceselection) | yes | — |
| `max_pages` | integer | no | minimum=1.0, maximum=5000.0, default=500 |
| `max_api_pages` | integer | no | minimum=1.0, maximum=500.0, default=50 |
| `max_blocks_per_page` | integer | no | minimum=1.0, maximum=20000.0, default=5000 |
| `max_block_depth` | integer | no | minimum=0.0, maximum=16.0, default=8 |
| `max_text_chars` | integer | no | minimum=100.0, maximum=2000000.0, default=2000000 |
| `request_timeout_seconds` | number | no | minimum=1.0, maximum=60.0, default=30 |

## NotionCredentials

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `integration_token` | string (password) | yes | minLength=1, maxLength=4096 |

## NotionDataSourceSelection

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `mode` | string | yes | — |
| `data_source_ids` | array of string (uuid) | yes | minItems=1, maxItems=100 |

## NotionIngestionRunItemRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `source_kind` | string | no | default=notion |
| `ordinal` | integer | yes | — |
| `source_node_id` | string | yes | — |
| `source_item_id` | string (uuid) or null | yes | — |
| `source_revision_id` | string (uuid) or null | yes | — |
| `processing_run_id` | string (uuid) or null | no | — |
| `canonical_location` | string or null | yes | — |
| `display_name` | string | yes | — |
| `media_type` | string or null | yes | — |
| `outcome` | string: new, changed, unchanged, removed, excluded, duplicate, failed | yes | — |
| `status` | string: ready, succeeded, failed, cancelled | yes | — |
| `reason` | string | yes | — |
| `chunk_count` | integer | yes | — |
| `error` | string or null | yes | — |
| `processing_versions` | object or null | no | — |
| `duplicate_decision` | object or null | no | — |
| `updated_at` | string (date-time) | yes | — |

## NotionPageSelection

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `mode` | string | yes | — |
| `page_ids` | array of string (uuid) | yes | minItems=1, maxItems=1000 |

## NotionWorkspaceSelection

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `mode` | string | yes | — |

## OcrCapability

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `available` | boolean | yes | — |
| `languages` | array of string | yes | — |
| `reason` | string or null | yes | — |
| `max_pages` | integer | yes | — |
| `max_pixels_per_page` | integer | yes | — |

## OcrSettingsV1

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `mode` | string: off, auto, always | no | default=off |
| `languages` | array of string | no | minItems=1, maxItems=3 |
| `rotate_pages` | boolean | no | default=True |
| `deskew` | boolean | no | default=True |
| `dpi` | integer | no | minimum=150.0, maximum=300.0, default=200 |
| `max_pages` | integer | no | minimum=1.0, maximum=100.0, default=50 |
| `timeout_seconds` | integer | no | minimum=5.0, maximum=60.0, default=30 |

## ParentChildChunkNodeV2

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `algorithm` | string | yes | — |
| `unit` | string | no | default=tokens |
| `tokenizer_version` | string | no | default=utf8-byte-v1 |
| `child_target_tokens` | integer | no | minimum=64.0, maximum=4096.0, default=240 |
| `child_maximum_tokens` | integer | no | minimum=64.0, maximum=8192.0, default=320 |
| `child_overlap_tokens` | integer | no | minimum=0.0, maximum=2048.0, default=40 |
| `parent_target_tokens` | integer | no | minimum=128.0, maximum=16384.0, default=900 |
| `parent_maximum_tokens` | integer | no | minimum=128.0, maximum=32768.0, default=1200 |
| `add_heading_context` | boolean | no | default=True |
| `config_version` | string | no | default=parent-child-v1 |

## PipelinePage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`PipelineRead`](#pipelineread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## PipelineRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `name` | string | yes | — |
| `kind` | string: answer, ingestion | yes | — |
| `created_at` | string (date-time) | yes | — |

## PipelineSave

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | no | default=answer |
| `name` | string | yes | minLength=1, maxLength=120 |
| `execution` | [`Execution`](#execution) | yes | — |
| `layout` | [`Layout`](#layout) | yes | — |

## Position

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `x` | number | yes | minimum=-100000.0, maximum=100000.0 |
| `y` | number | yes | minimum=-100000.0, maximum=100000.0 |

## PreserveStructureTransform

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `enabled` | boolean | no | default=True |
| `type` | string | yes | — |
| `block_types` | array of string: table, list_item, code, quote, footnote | no | minItems=1, maxItems=5 |

## PreviewRequest

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `question` | string | yes | minLength=1, maxLength=8000 |
| `execution` | [`Execution`](#execution) | yes | — |
| `base_pipeline_id` | string (uuid) or null | no | — |
| `base_version_id` | string (uuid) or null | no | — |

## ProcessingConfig

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `chunk_size` | integer | no | maximum=100000.0, exclusiveMinimum=0.0, default=1000 |
| `overlap` | integer | no | minimum=0.0, default=200 |

## ProjectCreate

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `name` | string | yes | minLength=1, maxLength=120 |
| `description` | string | no | maxLength=2000, default= |

## ProjectPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`ProjectRead`](#projectread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## ProjectRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `name` | string | yes | — |
| `description` | string | yes | — |
| `created_at` | string (date-time) | yes | — |

## Prompt

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `template` | string | yes | minLength=1, maxLength=8000 |

## PublishIndexNode

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `knowledge_set_name` | string | yes | minLength=1, maxLength=120 |
| `knowledge_set_id` | string (uuid) or null | no | — |

## QualityPolicyCapability

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string: default-v1, strict-v1, warn-v1 | yes | — |
| `name` | string | yes | — |
| `description` | string | yes | — |
| `settings` | [`DefaultQualityPolicyV1`](#defaultqualitypolicyv1) or [`StrictQualityPolicyV1`](#strictqualitypolicyv1) or [`WarnQualityPolicyV1`](#warnqualitypolicyv1) | yes | — |

## QualityThresholdsV1

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `maximum_empty_page_ratio` | number | no | minimum=0.0, maximum=1.0, default=0.2 |
| `maximum_replacement_character_ratio` | number | no | minimum=0.0, maximum=1.0, default=0.01 |
| `maximum_control_character_ratio` | number | no | minimum=0.0, maximum=1.0, default=0.001 |
| `minimum_ocr_confidence` | number | no | minimum=0.0, maximum=100.0, default=50 |
| `fail_on_suspicious_reading_order` | boolean | no | default=False |
| `fail_on_malformed_tables` | boolean | no | default=True |

## QueryPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`QueryRead`](#queryread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## QueryRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `index_id` | string (uuid) | yes | — |
| `pipeline_version_id` | string (uuid) or null | yes | — |
| `index_version` | integer | yes | — |
| `question` | string | yes | — |
| `answer` | string or null | yes | — |
| `status` | string: running, succeeded, insufficient_evidence, failed | yes | — |
| `error` | string or null | yes | — |
| `snapshot` | object | yes | — |
| `created_at` | string (date-time) | yes | — |

## QueryRequest

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `retrieval` | [`VectorSearch`](#vectorsearch) or [`KeywordSearch`](#keywordsearch) or [`HybridSearch`](#hybridsearch) | no | — |
| `index_id` | string (uuid) | yes | — |
| `question` | string | yes | minLength=1, maxLength=8000 |

## Question

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |

## ReflowPdfLinesTransform

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `enabled` | boolean | no | default=True |
| `type` | string | yes | — |
| `block_types` | array of string: paragraph, unknown | no | minItems=1, maxItems=2 |

## RefreshSourceInput

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |

## RemoveControlCharactersTransform

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `enabled` | boolean | no | default=True |
| `type` | string | yes | — |

## RemoveEmptyBlocksTransform

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `enabled` | boolean | no | default=True |
| `type` | string | yes | — |
| `minimum_characters` | integer | no | minimum=1.0, maximum=100.0, default=1 |

## RemoveLiteralBoilerplateTransform

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `enabled` | boolean | no | default=True |
| `type` | string | yes | — |
| `values` | array of string | yes | minItems=1, maxItems=50 |
| `block_types` | array of string: title, heading, paragraph, list_item, table, code, quote, image_caption, footnote, unknown | no | minItems=1, maxItems=10 |

## RemoveRepeatedHeadersFootersTransform

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `enabled` | boolean | no | default=True |
| `type` | string | yes | — |
| `minimum_page_ratio` | number | no | minimum=0.5, maximum=1.0, default=0.6 |
| `minimum_pages` | integer | no | minimum=3.0, maximum=100.0, default=3 |
| `margin_ratio` | number | no | maximum=0.25, exclusiveMinimum=0.0, default=0.12 |

## RetrievalRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `index_id` | string (uuid) | yes | — |
| `index_version` | integer | yes | — |
| `embedding_config` | [`EmbeddingConfig`](#embeddingconfig) | yes | — |
| `items` | array of [`Evidence`](#evidence) | yes | — |
| `retrieval` | [`VectorSearch`](#vectorsearch) or [`KeywordSearch`](#keywordsearch) or [`HybridSearch`](#hybridsearch) | yes | — |
| `diagnostics` | object | yes | — |
| `score_semantics` | string | no | default=Cosine distance: lower is closer; this is not confidence. |

## RetrievalRequest

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `retrieval` | [`VectorSearch`](#vectorsearch) or [`KeywordSearch`](#keywordsearch) or [`HybridSearch`](#hybridsearch) | no | — |
| `index_id` | string (uuid) | yes | — |
| `query` | string | yes | minLength=1, maxLength=8000 |

## Retriever

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `index_id` | string (uuid) | yes | — |
| `top_k` | integer or null | no | — |
| `retrieval` | [`VectorSearch`](#vectorsearch) or [`KeywordSearch`](#keywordsearch) or [`HybridSearch`](#hybridsearch) or null | no | — |

## RunPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`RunRead`](#runread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## RunRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `document_id` | string (uuid) | yes | — |
| `version` | integer | yes | — |
| `chunk_size` | integer | yes | — |
| `overlap` | integer | yes | — |
| `config_version` | string | yes | — |
| `parser_version` | string | yes | — |
| `processing_config` | object or null | yes | — |
| `processing_config_hash` | string or null | yes | — |
| `output_hash` | string or null | yes | — |
| `status` | string: queued, running, succeeded, failed, cancelled | yes | — |
| `attempts` | integer | yes | — |
| `progress` | integer | yes | — |
| `chunk_count` | integer | yes | — |
| `error` | string or null | yes | — |
| `created_at` | string (date-time) | yes | — |
| `started_at` | string (date-time) or null | yes | — |
| `finished_at` | string (date-time) or null | yes | — |

## RunRequest

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `question` | string | yes | minLength=1, maxLength=8000 |

## S3Config

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `connection_id` | string (uuid) | yes | — |
| `region` | string | yes | minLength=3, maxLength=32, pattern=^[a-z0-9-]+$ |
| `bucket` | string | yes | minLength=3, maxLength=63, pattern=^[a-z0-9][a-z0-9.-]*[a-z0-9]$ |
| `prefix` | string | no | maxLength=1024, default= |
| `expected_bucket_owner` | string or null | no | — |
| `allowed_file_types` | array of string: txt, pdf, md, html, docx, pptx, csv, tsv, xlsx | no | minItems=1, maxItems=9 |
| `max_objects` | integer | no | minimum=1.0, maximum=5000.0, default=1000 |
| `max_pages` | integer | no | minimum=1.0, maximum=100.0, default=10 |
| `max_object_bytes` | integer | no | minimum=1024.0, maximum=20971520.0, default=20971520 |
| `max_total_bytes` | integer | no | minimum=1024.0, maximum=104857600.0, default=104857600 |
| `request_timeout_seconds` | number | no | minimum=1.0, maximum=60.0, default=30 |

## S3Credentials

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `access_key_id` | string (password) | yes | minLength=1, maxLength=256 |
| `secret_access_key` | string (password) | yes | minLength=1, maxLength=4096 |
| `session_token` | string (password) or null | no | — |

## S3IngestionRunItemRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `source_kind` | string | no | default=s3 |
| `ordinal` | integer | yes | — |
| `source_node_id` | string | yes | — |
| `source_item_id` | string (uuid) or null | yes | — |
| `source_revision_id` | string (uuid) or null | yes | — |
| `processing_run_id` | string (uuid) or null | no | — |
| `canonical_location` | string or null | yes | — |
| `display_name` | string | yes | — |
| `media_type` | string or null | yes | — |
| `outcome` | string: new, changed, unchanged, removed, excluded, duplicate, failed | yes | — |
| `status` | string: ready, succeeded, failed, cancelled | yes | — |
| `reason` | string | yes | — |
| `chunk_count` | integer | yes | — |
| `error` | string or null | yes | — |
| `processing_versions` | object or null | no | — |
| `duplicate_decision` | object or null | no | — |
| `updated_at` | string (date-time) | yes | — |

## ScheduleCreate

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `name` | string | yes | minLength=1, maxLength=120 |
| `pipeline_id` | string (uuid) | yes | — |
| `pipeline_version_id` | string (uuid) | yes | — |
| `cadence` | [`IntervalCadence`](#intervalcadence) or [`DailyCadence`](#dailycadence) | yes | — |
| `enabled` | boolean | no | default=False |

## SchedulePage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`ScheduleRead`](#scheduleread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## ScheduleRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `pipeline_id` | string (uuid) | yes | — |
| `pipeline_version_id` | string (uuid) | yes | — |
| `pipeline_version` | integer | yes | — |
| `name` | string | yes | — |
| `status` | string: paused, enabled | yes | — |
| `cadence` | [`IntervalCadence`](#intervalcadence) or [`DailyCadence`](#dailycadence) | yes | — |
| `next_run_at` | string (date-time) or null | yes | — |
| `last_run_id` | string (uuid) or null | yes | — |
| `last_triggered_at` | string (date-time) or null | yes | — |
| `last_outcome` | string: queued, running, succeeded, failed, cancelled, skipped or null | yes | — |
| `last_error` | string or null | yes | — |
| `created_at` | string (date-time) | yes | — |
| `updated_at` | string (date-time) | yes | — |

## ScheduleUpdate

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `name` | string | yes | minLength=1, maxLength=120 |
| `cadence` | [`IntervalCadence`](#intervalcadence) or [`DailyCadence`](#dailycadence) | yes | — |
| `enabled` | boolean | yes | — |

## SectionTokenChunkNodeV2

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `algorithm` | string | yes | — |
| `unit` | string | no | default=tokens |
| `tokenizer_version` | string | no | default=utf8-byte-v1 |
| `target_tokens` | integer | no | minimum=64.0, maximum=8192.0, default=600 |
| `maximum_tokens` | integer | no | minimum=64.0, maximum=16384.0, default=800 |
| `overlap_tokens` | integer | no | minimum=0.0, maximum=4096.0, default=80 |
| `add_heading_context` | boolean | no | default=True |
| `config_version` | string | no | default=section-token-v1 |

## SensitiveDataPolicyV1

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | no | default=sensitive-data-v1 |
| `enabled` | boolean | no | default=False |
| `detector_version` | string | no | default=deterministic-patterns-v1 |
| `rules` | array of [`SensitiveDataRuleV1`](#sensitivedatarulev1) | no | minItems=1, maxItems=6 |
| `government_id_formats` | array of string: us_ssn, in_aadhaar | no | minItems=1, maxItems=2 |

## SensitiveDataRuleV1

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `entity_class` | string: email, phone, ip_address, government_id, payment_card, api_secret | yes | — |
| `action` | string: redact, drop_document | no | default=redact |

## SingleUrlSelection

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `mode` | string | yes | — |
| `url` | string (uri) | yes | minLength=1 |

## SitemapSelection

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `mode` | string | yes | — |
| `sitemap_url` | string (uri) | yes | minLength=1 |

## SnapshotSourceInput

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `source_snapshot_id` | string (uuid) | yes | — |

## SourceConnectionCreate

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `name` | string | yes | minLength=1, maxLength=120 |
| `credentials` | [`S3Credentials`](#s3credentials) or [`NotionCredentials`](#notioncredentials) or [`ConfluenceCredentials`](#confluencecredentials) | yes | — |

## SourceConnectionPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`SourceConnectionRead`](#sourceconnectionread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## SourceConnectionRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `name` | string | yes | — |
| `kind` | string: s3, notion, confluence | yes | — |
| `status` | string: untested, valid, invalid, unavailable | yes | — |
| `redacted_summary` | array of string | yes | — |
| `last_error` | string or null | yes | — |
| `last_tested_at` | string (date-time) or null | yes | — |
| `rotated_at` | string (date-time) or null | yes | — |
| `created_at` | string (date-time) | yes | — |
| `updated_at` | string (date-time) | yes | — |

## SourceConnectionRotate

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `credentials` | [`S3Credentials`](#s3credentials) or [`NotionCredentials`](#notioncredentials) or [`ConfluenceCredentials`](#confluencecredentials) | yes | — |

## SourceConnectionSettings

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `enabled` | boolean | yes | — |
| `local_only` | boolean | no | default=True |
| `kinds` | array of string: s3, notion, confluence | no | — |

## SourceNode

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `type` | string | yes | — |
| `config` | [`ExistingFilesConfig`](#existingfilesconfig) or [`WebsiteConfig`](#websiteconfig) or [`S3Config`](#s3config) or [`NotionConfig`](#notionconfig) or [`ConfluenceConfig`](#confluenceconfig) | yes | — |

## SourcePreviewItemPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`SourcePreviewItemRead`](#sourcepreviewitemread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## SourcePreviewItemRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `ordinal` | integer | yes | — |
| `source_node_id` | string | yes | — |
| `external_id` | string or null | yes | — |
| `display_name` | string | yes | — |
| `canonical_location` | string or null | yes | — |
| `provider_revision` | string or null | yes | — |
| `media_type` | string or null | yes | — |
| `status` | string: included, excluded, duplicate, failed | yes | — |
| `reason` | string | yes | — |
| `size_bytes` | integer or null | yes | — |
| `depth` | integer or null | yes | — |
| `error_code` | string or null | yes | — |
| `quality_decision` | string: pass, warn, exclude, fail or null | yes | — |
| `processing_status` | string: pending, succeeded, failed, skipped | yes | — |
| `fetch_mode` | string: network, cached-artifact | yes | — |
| `processing_config_hash` | string or null | yes | — |
| `findings` | array of object | yes | — |
| `metrics` | object | yes | — |
| `stage_timings` | object | yes | — |
| `cost_basis` | object | yes | — |
| `duplicate_decision` | object or null | no | — |

## SourcePreviewRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `status` | string: queued, running, succeeded, failed, cancelled, expired | yes | — |
| `progress` | integer | yes | — |
| `discovered_count` | integer | yes | — |
| `included_count` | integer | yes | — |
| `excluded_count` | integer | yes | — |
| `duplicate_count` | integer | yes | — |
| `failed_count` | integer | yes | — |
| `pass_count` | integer | yes | — |
| `warn_count` | integer | yes | — |
| `exclude_count` | integer | yes | — |
| `quality_fail_count` | integer | yes | — |
| `known_compute_ms` | integer | yes | — |
| `configuration_hash` | string | yes | — |
| `fetch_mode` | string: network, cached-artifact, mixed | yes | — |
| `cost_basis` | object | yes | — |
| `attempts` | integer | yes | — |
| `failures` | integer | yes | — |
| `error` | string or null | yes | — |
| `created_at` | string (date-time) | yes | — |
| `updated_at` | string (date-time) | yes | — |
| `started_at` | string (date-time) or null | yes | — |
| `finished_at` | string (date-time) or null | yes | — |
| `expires_at` | string (date-time) | yes | — |
| `protected_content` | boolean | no | default=False |

## SourcePreviewRepresentationPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`SourcePreviewRepresentationRead`](#sourcepreviewrepresentationread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## SourcePreviewRepresentationRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `stage` | string: raw, extracted, cleaned, diff, chunks | yes | — |
| `ordinal` | integer | yes | — |
| `block_type` | string | yes | — |
| `text` | string | yes | — |
| `metadata` | object | yes | — |

## SourceSnapshotIndexPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`SourceSnapshotIndexRead`](#sourcesnapshotindexread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## SourceSnapshotIndexRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `knowledge_set_id` | string (uuid) | yes | — |
| `knowledge_set_name` | string | yes | — |
| `version` | integer | yes | — |
| `status` | string: queued, running, succeeded, failed, cancelled | yes | — |
| `chunk_count` | integer | yes | — |
| `embedded_count` | integer | yes | — |
| `is_current` | boolean | yes | — |
| `ingestion_pipeline_id` | string (uuid) or null | yes | — |
| `ingestion_pipeline_version_id` | string (uuid) or null | yes | — |
| `ingestion_pipeline_name` | string or null | yes | — |
| `ingestion_pipeline_version` | integer or null | yes | — |
| `created_at` | string (date-time) | yes | — |

## SourceSnapshotMemberPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`SourceSnapshotMemberRead`](#sourcesnapshotmemberread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## SourceSnapshotMemberRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `ordinal` | integer | yes | — |
| `source_node_id` | string | yes | — |
| `source_item_id` | string (uuid) | yes | — |
| `source_revision_id` | string (uuid) | yes | — |
| `inclusion_state` | string | yes | — |
| `canonical_location` | string | yes | — |
| `media_type` | string | yes | — |
| `size_bytes` | integer | yes | — |
| `fetched_at` | string (date-time) | yes | — |
| `provider_revision` | string or null | yes | — |
| `provenance` | object | no | — |

## SourceSnapshotPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`SourceSnapshotRead`](#sourcesnapshotread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## SourceSnapshotRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `source_kind` | string: website, s3, notion, confluence | yes | — |
| `source_config_hash` | string | yes | — |
| `source_identity` | object | yes | — |
| `connector_version` | string | yes | — |
| `snapshot_number` | integer | yes | — |
| `status` | string: collecting, ready, failed, cancelled | yes | — |
| `discovered_count` | integer | yes | — |
| `included_count` | integer | yes | — |
| `excluded_count` | integer | yes | — |
| `duplicate_count` | integer | yes | — |
| `failed_count` | integer | yes | — |
| `new_count` | integer | yes | — |
| `changed_count` | integer | yes | — |
| `unchanged_count` | integer | yes | — |
| `removed_count` | integer | yes | — |
| `total_bytes` | integer | yes | — |
| `creating_ingestion_run_id` | string (uuid) | yes | — |
| `downstream_index_count` | integer | no | default=0 |
| `error` | string or null | yes | — |
| `created_at` | string (date-time) | yes | — |
| `collected_at` | string (date-time) or null | yes | — |

## StrictQualityPolicyV1

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | no | default=strict-v1 |
| `thresholds` | [`QualityThresholdsV1`](#qualitythresholdsv1) | no | — |
| `warning_action` | string: publish, fail | yes | — |
| `failed_item_action` | string: fail, exclude | no | default=fail |

## TokenizerCapability

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | — |
| `version` | string | yes | — |
| `unit` | string | yes | — |

## UnicodeNormalizeTransform

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `enabled` | boolean | no | default=True |
| `type` | string | yes | — |
| `form` | string: NFC, NFKC | no | default=NFC |

## UrlListSelection

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `mode` | string | yes | — |
| `urls` | array of string (uri) | yes | minItems=1, maxItems=1000 |

## ValidateUsefulContentTransform

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `enabled` | boolean | no | default=True |
| `type` | string | yes | — |
| `minimum_characters` | integer | no | minimum=1.0, maximum=100000.0, default=1 |
| `maximum_characters` | integer | no | minimum=1.0, maximum=2000000.0, default=2000000 |

## ValidationError

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `loc` | array of string or integer | yes | — |
| `msg` | string | yes | — |
| `type` | string | yes | — |

## VectorSearch

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `top_k` | integer | no | minimum=1.0, maximum=50.0, default=5 |
| `mode` | string | no | default=vector |
| `max_vector_distance` | number or null | no | — |

## VersionPage

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `items` | array of [`VersionRead`](#versionread) | yes | — |
| `total` | integer | yes | — |
| `limit` | integer | yes | — |
| `offset` | integer | yes | — |

## VersionRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes | — |
| `pipeline_id` | string (uuid) | yes | — |
| `project_id` | string (uuid) | yes | — |
| `version` | integer | yes | — |
| `name` | string | yes | — |
| `execution` | [`Execution`](#execution) or [`IngestionExecution`](#ingestionexecution) | yes | — |
| `layout` | [`Layout`](#layout) or [`IngestionLayout`](#ingestionlayout) | yes | — |
| `created_at` | string (date-time) | yes | — |

## WarnQualityPolicyV1

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | no | default=warn-v1 |
| `thresholds` | [`QualityThresholdsV1`](#qualitythresholdsv1) | no | — |
| `warning_action` | string: publish, fail | yes | — |
| `failed_item_action` | string: fail, exclude | no | default=exclude |

## WebsiteConfig

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `kind` | string | yes | — |
| `selection` | [`SingleUrlSelection`](#singleurlselection) or [`UrlListSelection`](#urllistselection) or [`CrawlSelection`](#crawlselection) or [`SitemapSelection`](#sitemapselection) | yes | — |
| `allowed_origins` | array of string (uri) | yes | minItems=1, maxItems=20 |
| `include_path_prefixes` | array of string | no | maxItems=50 |
| `exclude_path_prefixes` | array of string | no | maxItems=50 |
| `max_pages` | integer | yes | minimum=1.0, maximum=1000.0 |
| `max_depth` | integer | yes | minimum=0.0, maximum=10.0 |
| `max_response_bytes` | integer | yes | minimum=1024.0, maximum=10485760.0 |
| `max_total_bytes` | integer | yes | minimum=1024.0, maximum=104857600.0 |
| `request_timeout_seconds` | number | yes | minimum=1.0, maximum=60.0 |
| `deadline_seconds` | number | yes | minimum=1.0, maximum=3600.0 |
| `concurrency` | integer | yes | minimum=1.0, maximum=16.0 |
| `requests_per_second` | number | yes | maximum=20.0, exclusiveMinimum=0.0 |
| `redirect_limit` | integer | yes | minimum=0.0, maximum=10.0 |
| `user_agent` | string | yes | minLength=1, maxLength=200 |
| `respect_robots` | boolean | no | default=True |

## WebsiteIngestionRunItemRead

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `source_kind` | string | no | default=website |
| `ordinal` | integer | yes | — |
| `source_node_id` | string | yes | — |
| `source_item_id` | string (uuid) or null | yes | — |
| `source_revision_id` | string (uuid) or null | yes | — |
| `processing_run_id` | string (uuid) or null | no | — |
| `canonical_location` | string or null | yes | — |
| `display_name` | string | yes | — |
| `media_type` | string or null | yes | — |
| `outcome` | string: new, changed, unchanged, removed, excluded, duplicate, failed | yes | — |
| `status` | string: ready, succeeded, failed, cancelled | yes | — |
| `reason` | string | yes | — |
| `chunk_count` | integer | yes | — |
| `error` | string or null | yes | — |
| `processing_versions` | object or null | no | — |
| `duplicate_decision` | object or null | no | — |
| `updated_at` | string (date-time) | yes | — |

## WebsiteMainContentTransform

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `enabled` | boolean | no | default=True |
| `type` | string | yes | — |
| `remove_semantic_chrome` | boolean | no | default=True |
| `remove_cookie_banners` | boolean | no | default=True |
| `remove_repeated_site_chrome` | boolean | no | default=True |
| `minimum_page_ratio` | number | no | minimum=0.5, maximum=1.0, default=0.6 |

## WebsiteSelectorsTransform

| Field | Type | Required | Bounds/default |
| --- | --- | --- | --- |
| `id` | string | yes | minLength=1, maxLength=80, pattern=^[a-zA-Z0-9_-]+$ |
| `enabled` | boolean | no | default=True |
| `type` | string | yes | — |
| `include` | array of string | no | maxItems=20 |
| `exclude` | array of string | no | maxItems=20 |
