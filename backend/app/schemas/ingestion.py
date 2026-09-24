"""Strict, versioned ingestion graph configuration.

This module defines persisted configuration only. Execution, knowledge sets and
connector transports are introduced by later ingestion phases.
"""

import ipaddress
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    model_validator,
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExistingFilesConfig(Strict):
    kind: Literal["existing_files"]
    document_ids: list[UUID] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_documents(self):
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("Existing-files document IDs must be unique.")
        return self


class SingleUrlSelection(Strict):
    mode: Literal["single_url"]
    url: AnyHttpUrl


class UrlListSelection(Strict):
    mode: Literal["url_list"]
    urls: list[AnyHttpUrl] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_urls(self):
        if len({str(url) for url in self.urls}) != len(self.urls):
            raise ValueError("Website URL list entries must be unique.")
        return self


class CrawlSelection(Strict):
    mode: Literal["crawl"]
    start_url: AnyHttpUrl


class SitemapSelection(Strict):
    mode: Literal["sitemap"]
    sitemap_url: AnyHttpUrl


WebsiteSelection = Annotated[
    SingleUrlSelection | UrlListSelection | CrawlSelection | SitemapSelection,
    Field(discriminator="mode"),
]


class WebsiteConfig(Strict):
    kind: Literal["website"]
    selection: WebsiteSelection
    allowed_origins: list[AnyHttpUrl] = Field(min_length=1, max_length=20)
    include_path_prefixes: list[str] = Field(default_factory=list, max_length=50)
    exclude_path_prefixes: list[str] = Field(default_factory=list, max_length=50)
    max_pages: int = Field(strict=True, ge=1, le=1000)
    max_depth: int = Field(strict=True, ge=0, le=10)
    max_response_bytes: int = Field(strict=True, ge=1024, le=10 * 1024 * 1024)
    max_total_bytes: int = Field(strict=True, ge=1024, le=100 * 1024 * 1024)
    request_timeout_seconds: float = Field(ge=1, le=60, allow_inf_nan=False)
    deadline_seconds: float = Field(ge=1, le=3600, allow_inf_nan=False)
    concurrency: int = Field(strict=True, ge=1, le=16)
    requests_per_second: float = Field(gt=0, le=20, allow_inf_nan=False)
    redirect_limit: int = Field(strict=True, ge=0, le=10)
    user_agent: str = Field(min_length=1, max_length=200)
    respect_robots: bool = True

    @model_validator(mode="after")
    def bounded_paths_and_bytes(self):
        urls = list(self.allowed_origins)
        selection = self.selection
        if selection.mode == "single_url":
            urls.append(selection.url)
        elif selection.mode == "url_list":
            urls.extend(selection.urls)
        elif selection.mode == "crawl":
            urls.append(selection.start_url)
        else:
            urls.append(selection.sitemap_url)
        if any(url.username is not None or url.password is not None for url in urls):
            raise ValueError("Website URLs cannot contain credentials.")
        if len({str(url) for url in self.allowed_origins}) != len(self.allowed_origins):
            raise ValueError("Allowed website origins must be unique.")
        if any(
            origin.path not in (None, "/")
            or origin.query is not None
            or origin.fragment is not None
            for origin in self.allowed_origins
        ):
            raise ValueError(
                "Allowed origins must contain only scheme, host and optional port."
            )
        prefixes = self.include_path_prefixes + self.exclude_path_prefixes
        if any(
            not value.startswith("/") or len(value) > 500 or "\\" in value
            for value in prefixes
        ):
            raise ValueError(
                "Website path prefixes must start with '/', be at most 500 characters and use URL separators."
            )
        if self.max_total_bytes < self.max_response_bytes:
            raise ValueError(
                "Website total byte limit must be at least the per-response limit."
            )
        if self.deadline_seconds < self.request_timeout_seconds:
            raise ValueError(
                "Website deadline must be at least the per-request timeout."
            )
        return self


class S3Config(Strict):
    kind: Literal["s3"]
    connection_id: UUID
    region: str = Field(min_length=3, max_length=32, pattern=r"^[a-z0-9-]+$")
    bucket: str = Field(
        min_length=3,
        max_length=63,
        pattern=r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$",
    )
    prefix: str = Field(default="", max_length=1024)
    expected_bucket_owner: str | None = Field(default=None, pattern=r"^[0-9]{12}$")
    allowed_file_types: list[Literal["txt", "pdf"]] = Field(
        default_factory=lambda: ["txt", "pdf"], min_length=1, max_length=2
    )
    max_objects: int = Field(default=1000, strict=True, ge=1, le=5000)
    max_pages: int = Field(default=10, strict=True, ge=1, le=100)
    max_object_bytes: int = Field(
        default=20 * 1024 * 1024, strict=True, ge=1024, le=20 * 1024 * 1024
    )
    max_total_bytes: int = Field(
        default=100 * 1024 * 1024,
        strict=True,
        ge=1024,
        le=100 * 1024 * 1024,
    )
    request_timeout_seconds: float = Field(default=30, ge=1, le=60, allow_inf_nan=False)

    @model_validator(mode="after")
    def safe_selection(self):
        if len(set(self.allowed_file_types)) != len(self.allowed_file_types):
            raise ValueError("S3 allowed file types must be unique.")
        if self.max_total_bytes < self.max_object_bytes:
            raise ValueError(
                "S3 total byte limit must be at least the per-object limit."
            )
        if "\x00" in self.prefix:
            raise ValueError("S3 prefixes cannot contain null characters.")
        try:
            ipaddress.ip_address(self.bucket)
        except ValueError:
            pass
        else:
            raise ValueError("S3 bucket names cannot use an IP-address format.")
        if ".-" in self.bucket or "-." in self.bucket:
            raise ValueError("S3 bucket names contain an invalid label boundary.")
        if (
            self.bucket.startswith(("xn--", "sthree-", "amzn_s3_demo_"))
            or ".." in self.bucket
        ):
            raise ValueError("S3 bucket name is reserved or malformed.")
        return self


class NotionWorkspaceSelection(Strict):
    mode: Literal["workspace"]


class NotionPageSelection(Strict):
    mode: Literal["pages"]
    page_ids: list[UUID] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_pages(self):
        if len(set(self.page_ids)) != len(self.page_ids):
            raise ValueError("Notion page IDs must be unique.")
        return self


class NotionDataSourceSelection(Strict):
    mode: Literal["data_sources"]
    data_source_ids: list[UUID] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_data_sources(self):
        if len(set(self.data_source_ids)) != len(self.data_source_ids):
            raise ValueError("Notion data source IDs must be unique.")
        return self


NotionSelection = Annotated[
    NotionWorkspaceSelection | NotionPageSelection | NotionDataSourceSelection,
    Field(discriminator="mode"),
]


class NotionConfig(Strict):
    kind: Literal["notion"]
    connection_id: UUID
    selection: NotionSelection
    max_pages: int = Field(default=500, strict=True, ge=1, le=5000)
    max_api_pages: int = Field(default=50, strict=True, ge=1, le=500)
    max_blocks_per_page: int = Field(default=5000, strict=True, ge=1, le=20000)
    max_block_depth: int = Field(default=8, strict=True, ge=0, le=16)
    max_text_chars: int = Field(default=2_000_000, strict=True, ge=100, le=2_000_000)
    request_timeout_seconds: float = Field(default=30, ge=1, le=60, allow_inf_nan=False)

    @model_validator(mode="after")
    def bounded_explicit_selection(self):
        if (
            self.selection.mode == "pages"
            and len(self.selection.page_ids) > self.max_pages
        ):
            raise ValueError("Notion page selection cannot exceed the page limit.")
        return self


class ConfluenceSiteSelection(Strict):
    mode: Literal["site"]


class ConfluenceSpaceSelection(Strict):
    mode: Literal["spaces"]
    space_ids: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_spaces(self):
        if len(set(self.space_ids)) != len(self.space_ids):
            raise ValueError("Confluence space IDs must be unique.")
        if any(not value.isdigit() or len(value) > 40 for value in self.space_ids):
            raise ValueError("Confluence space IDs must be numeric provider IDs.")
        return self


class ConfluencePageSelection(Strict):
    mode: Literal["pages"]
    page_ids: list[str] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_pages(self):
        if len(set(self.page_ids)) != len(self.page_ids):
            raise ValueError("Confluence page IDs must be unique.")
        if any(not value.isdigit() or len(value) > 40 for value in self.page_ids):
            raise ValueError("Confluence page IDs must be numeric provider IDs.")
        return self


ConfluenceSelection = Annotated[
    ConfluenceSiteSelection | ConfluenceSpaceSelection | ConfluencePageSelection,
    Field(discriminator="mode"),
]


class ConfluenceConfig(Strict):
    kind: Literal["confluence"]
    connection_id: UUID
    selection: ConfluenceSelection
    title_prefixes: list[str] = Field(default_factory=list, max_length=50)
    exclude_title_prefixes: list[str] = Field(default_factory=list, max_length=50)
    label_ids: list[str] = Field(default_factory=list, max_length=50)
    max_pages: int = Field(default=500, strict=True, ge=1, le=5000)
    max_api_pages: int = Field(default=100, strict=True, ge=1, le=500)
    max_response_bytes: int = Field(
        default=2 * 1024 * 1024, strict=True, ge=1024, le=10 * 1024 * 1024
    )
    max_text_chars: int = Field(default=2_000_000, strict=True, ge=100, le=2_000_000)
    request_timeout_seconds: float = Field(default=30, ge=1, le=60, allow_inf_nan=False)

    @model_validator(mode="after")
    def bounded_selection(self):
        values = self.title_prefixes + self.exclude_title_prefixes
        if any(not value.strip() or len(value) > 200 for value in values):
            raise ValueError(
                "Confluence title prefixes must contain 1 to 200 characters."
            )
        if len(set(self.label_ids)) != len(self.label_ids) or any(
            not value.isdigit() or len(value) > 40 for value in self.label_ids
        ):
            raise ValueError(
                "Confluence label IDs must be unique numeric provider IDs."
            )
        if (
            self.selection.mode == "pages"
            and len(self.selection.page_ids) > self.max_pages
        ):
            raise ValueError("Confluence page selection cannot exceed the page limit.")
        return self


SourceConfig = Annotated[
    ExistingFilesConfig | WebsiteConfig | S3Config | NotionConfig | ConfluenceConfig,
    Field(discriminator="kind"),
]


class NodeBase(Strict):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


class SourceNode(NodeBase):
    type: Literal["source"]
    config: SourceConfig


class LegacyExtractNode(NodeBase):
    type: Literal["extract"]
    strategy: Literal["media_type_registry"] = "media_type_registry"
    config_version: str = Field(default="1", min_length=1, max_length=40)


class LegacyCleanNode(NodeBase):
    type: Literal["clean"]
    normalize_whitespace: bool = True
    repeated_boilerplate: list[str] = Field(default_factory=list, max_length=50)
    minimum_text_chars: int = Field(default=1, strict=True, ge=1, le=100000)
    maximum_text_chars: int = Field(default=2_000_000, strict=True, ge=1, le=2_000_000)
    exact_content_deduplication: bool = True

    @model_validator(mode="after")
    def text_limits(self):
        if self.minimum_text_chars > self.maximum_text_chars:
            raise ValueError("Minimum text size cannot exceed maximum text size.")
        if any(not value or len(value) > 500 for value in self.repeated_boilerplate):
            raise ValueError("Boilerplate values must contain 1 to 500 characters.")
        return self


class LegacyChunkNode(NodeBase):
    type: Literal["chunk"]
    algorithm: Literal["character_window"] = "character_window"
    unit: Literal["characters"] = "characters"
    size: int = Field(strict=True, ge=100, le=10000)
    overlap: int = Field(strict=True, ge=0, le=9999)
    config_version: str = Field(default="1", min_length=1, max_length=40)

    @model_validator(mode="after")
    def overlap_smaller_than_size(self):
        if self.overlap >= self.size:
            raise ValueError("Chunk overlap must be smaller than chunk size.")
        return self


class EmbedNode(NodeBase):
    type: Literal["embed"]
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=200)
    dimensions: int = Field(strict=True, ge=1, le=16000)
    config_version: str = Field(min_length=1, max_length=40)


class PublishIndexNode(NodeBase):
    type: Literal["publish_index"]
    knowledge_set_name: str = Field(min_length=1, max_length=120)
    knowledge_set_id: UUID | None = None

    @model_validator(mode="after")
    def clean_name(self):
        self.knowledge_set_name = self.knowledge_set_name.strip()
        if not self.knowledge_set_name:
            raise ValueError("Knowledge set name is required.")
        return self


LegacyIngestionNode = Annotated[
    SourceNode
    | LegacyExtractNode
    | LegacyCleanNode
    | LegacyChunkNode
    | EmbedNode
    | PublishIndexNode,
    Field(discriminator="type"),
]


class OcrSettingsV1(Strict):
    mode: Literal["off", "auto", "always"] = "off"
    languages: list[str] = Field(
        default_factory=lambda: ["eng"], min_length=1, max_length=3
    )
    rotate_pages: bool = True
    deskew: bool = True
    dpi: int = Field(default=200, strict=True, ge=150, le=300)
    max_pages: int = Field(default=50, strict=True, ge=1, le=100)
    timeout_seconds: int = Field(default=30, strict=True, ge=5, le=60)

    @model_validator(mode="after")
    def safe_languages(self):
        if len(set(self.languages)) != len(self.languages):
            raise ValueError("OCR languages must be unique.")
        if any(
            not value
            or len(value) > 16
            or not value.replace("_", "").replace("-", "").isalnum()
            for value in self.languages
        ):
            raise ValueError(
                "OCR languages must use bounded language-pack identifiers."
            )
        return self


class LanguagePolicyV1(Strict):
    id: Literal["language-v1"] = "language-v1"
    detection_model: Literal["deterministic-script-v1"] = "deterministic-script-v1"
    allowlist: list[str] = Field(default_factory=list, max_length=20)
    minimum_confidence: float = Field(default=0, ge=0, le=1)
    disallowed_action: Literal["fail", "exclude"] = "fail"
    mixed_language_action: Literal["allow", "warn", "fail"] = "warn"

    @model_validator(mode="after")
    def safe_allowlist(self):
        normalized = [value.strip().lower() for value in self.allowlist]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Language allowlist values must be unique.")
        if any(
            len(value) not in range(2, 16) or not value.replace("-", "").isalnum()
            for value in normalized
        ):
            raise ValueError("Language allowlist values must be bounded language tags.")
        self.allowlist = normalized
        return self


class DuplicatePolicyV1(Strict):
    id: Literal["duplicate-v1"] = "duplicate-v1"
    exact_raw: bool = True
    exact_cleaned: bool = True
    normalized_sections: bool = True
    near_duplicate: bool = False
    near_duplicate_method: Literal["simhash64"] = "simhash64"
    near_duplicate_threshold: float = Field(default=0.92, ge=0.75, le=1)
    pinned_canonical_locations: list[str] = Field(default_factory=list, max_length=100)
    connector_priority: list[
        Literal["existing_files", "website", "s3", "notion", "confluence"]
    ] = Field(
        default_factory=lambda: [
            "existing_files",
            "website",
            "s3",
            "notion",
            "confluence",
        ],
        min_length=5,
        max_length=5,
    )

    @model_validator(mode="after")
    def deterministic_priority(self):
        if len(set(self.connector_priority)) != 5:
            raise ValueError(
                "Connector priority must include each supported source once."
            )
        if len(set(self.pinned_canonical_locations)) != len(
            self.pinned_canonical_locations
        ):
            raise ValueError("Pinned canonical locations must be unique.")
        if any(
            not value or len(value) > 4000 for value in self.pinned_canonical_locations
        ):
            raise ValueError(
                "Pinned canonical locations must contain 1 to 4000 characters."
            )
        return self


class QualityThresholdsV1(Strict):
    maximum_empty_page_ratio: float = Field(default=0.20, ge=0, le=1)
    maximum_replacement_character_ratio: float = Field(default=0.01, ge=0, le=1)
    maximum_control_character_ratio: float = Field(default=0.001, ge=0, le=1)
    minimum_ocr_confidence: float = Field(default=50, ge=0, le=100)
    fail_on_suspicious_reading_order: bool = False
    fail_on_malformed_tables: bool = True


class DefaultQualityPolicyV1(Strict):
    id: Literal["default-v1"] = "default-v1"
    thresholds: QualityThresholdsV1 = Field(default_factory=QualityThresholdsV1)
    warning_action: Literal["publish", "fail"]
    failed_item_action: Literal["fail", "exclude"] = "fail"


class StrictQualityPolicyV1(Strict):
    id: Literal["strict-v1"] = "strict-v1"
    thresholds: QualityThresholdsV1 = Field(
        default_factory=lambda: QualityThresholdsV1(
            maximum_empty_page_ratio=0,
            maximum_replacement_character_ratio=0.001,
            maximum_control_character_ratio=0,
            minimum_ocr_confidence=70,
            fail_on_suspicious_reading_order=True,
            fail_on_malformed_tables=True,
        )
    )
    warning_action: Literal["publish", "fail"]
    failed_item_action: Literal["fail", "exclude"] = "fail"


class WarnQualityPolicyV1(Strict):
    id: Literal["warn-v1"] = "warn-v1"
    thresholds: QualityThresholdsV1 = Field(default_factory=QualityThresholdsV1)
    warning_action: Literal["publish", "fail"]
    failed_item_action: Literal["fail", "exclude"] = "exclude"


QualityPolicyV1 = Annotated[
    DefaultQualityPolicyV1 | StrictQualityPolicyV1 | WarnQualityPolicyV1,
    Field(discriminator="id"),
]
LegacyQualityPolicy = Literal["default-v1", "strict-v1", "warn-v1"]


class ExtractNodeV2(NodeBase):
    type: Literal["extract"]
    strategy: Literal["native_text", "auto", "native", "layout_aware"] = "native_text"
    ocr: "OcrSettingsV1" = Field(default_factory=lambda: OcrSettingsV1())
    tables: Literal["preserve", "markdown", "plain_text"] = "preserve"
    # String profiles are read-only compatibility inputs for saved Phase 2-4 versions.
    # New drafts persist a typed policy with an explicit warning publication action.
    quality_policy: QualityPolicyV1 | LegacyQualityPolicy = "default-v1"
    language_policy: LanguagePolicyV1 = Field(default_factory=LanguagePolicyV1)
    config_version: Literal["native-text-v1", "layout-ocr-v1"] = "native-text-v1"

    @model_validator(mode="after")
    def versioned_settings(self):
        if self.config_version == "native-text-v1":
            if self.strategy != "native_text" or self.ocr.mode != "off":
                raise ValueError(
                    "Legacy native-text-v1 extraction supports only native text with OCR off."
                )
        elif self.strategy == "native_text":
            raise ValueError(
                "layout-ocr-v1 extraction requires Auto, Native or Layout-aware strategy."
            )
        return self


class CleaningTransformBase(Strict):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    enabled: bool = True


class PreserveStructureTransform(CleaningTransformBase):
    type: Literal["preserve_structure"]
    block_types: list[Literal["table", "list_item", "code", "quote", "footnote"]] = (
        Field(
            default_factory=lambda: ["table", "list_item", "code", "quote", "footnote"],
            min_length=1,
            max_length=5,
        )
    )

    @model_validator(mode="after")
    def unique_types(self):
        if len(set(self.block_types)) != len(self.block_types):
            raise ValueError("Protected block types must be unique.")
        return self


class UnicodeNormalizeTransform(CleaningTransformBase):
    type: Literal["unicode_normalize"]
    form: Literal["NFC", "NFKC"] = "NFC"


class RemoveControlCharactersTransform(CleaningTransformBase):
    type: Literal["remove_control_characters"]


class ReflowPdfLinesTransform(CleaningTransformBase):
    type: Literal["reflow_pdf_lines"]
    block_types: list[Literal["paragraph", "unknown"]] = Field(
        default_factory=lambda: ["paragraph", "unknown"],
        min_length=1,
        max_length=2,
    )


class DehyphenateTransform(CleaningTransformBase):
    type: Literal["dehyphenate"]
    mode: Literal["conservative"] = "conservative"


class RemoveRepeatedHeadersFootersTransform(CleaningTransformBase):
    type: Literal["remove_repeated_headers_footers"]
    minimum_page_ratio: float = Field(default=0.6, ge=0.5, le=1)
    minimum_pages: int = Field(default=3, strict=True, ge=3, le=100)
    margin_ratio: float = Field(default=0.12, gt=0, le=0.25)


class RemoveEmptyBlocksTransform(CleaningTransformBase):
    type: Literal["remove_empty_blocks"]
    minimum_characters: int = Field(default=1, strict=True, ge=1, le=100)


class RemoveLiteralBoilerplateTransform(CleaningTransformBase):
    type: Literal["remove_literal_boilerplate"]
    values: list[str] = Field(min_length=1, max_length=50)
    block_types: list[
        Literal[
            "title",
            "heading",
            "paragraph",
            "list_item",
            "table",
            "code",
            "quote",
            "image_caption",
            "footnote",
            "unknown",
        ]
    ] = Field(
        default_factory=lambda: ["paragraph", "unknown"], min_length=1, max_length=10
    )

    @model_validator(mode="after")
    def safe_literals(self):
        if len(set(self.values)) != len(self.values) or any(
            not value.strip() or len(value) > 500 for value in self.values
        ):
            raise ValueError(
                "Literal boilerplate values must be unique and contain 1 to 500 visible characters."
            )
        if len(set(self.block_types)) != len(self.block_types):
            raise ValueError("Literal boilerplate block types must be unique.")
        return self


_SAFE_SELECTOR = r"^(?:[a-z][a-z0-9-]*|\.[a-zA-Z0-9_-]+|#[a-zA-Z0-9_-]+|\[role=(?:main|navigation|banner|contentinfo|complementary|dialog|form)\])$"


class WebsiteSelectorsTransform(CleaningTransformBase):
    type: Literal["website_selectors"]
    include: list[str] = Field(default_factory=list, max_length=20)
    exclude: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def safe_selectors(self):
        import re

        values = self.include + self.exclude
        if not values:
            raise ValueError(
                "Website selectors require at least one include or exclude selector."
            )
        if len(set(values)) != len(values) or any(
            len(value) > 80 or re.fullmatch(_SAFE_SELECTOR, value) is None
            for value in values
        ):
            raise ValueError(
                "Website selectors support only a bounded tag, .class, #id or approved [role=value] selector."
            )
        return self


class WebsiteMainContentTransform(CleaningTransformBase):
    type: Literal["website_main_content"]
    remove_semantic_chrome: bool = True
    remove_cookie_banners: bool = True
    remove_repeated_site_chrome: bool = True
    minimum_page_ratio: float = Field(default=0.6, ge=0.5, le=1)


class ValidateUsefulContentTransform(CleaningTransformBase):
    type: Literal["validate_useful_content"]
    minimum_characters: int = Field(default=1, strict=True, ge=1, le=100_000)
    maximum_characters: int = Field(default=2_000_000, strict=True, ge=1, le=2_000_000)

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.minimum_characters > self.maximum_characters:
            raise ValueError("Minimum useful content cannot exceed the maximum.")
        return self


CleaningTransform = Annotated[
    PreserveStructureTransform
    | UnicodeNormalizeTransform
    | RemoveControlCharactersTransform
    | ReflowPdfLinesTransform
    | DehyphenateTransform
    | RemoveRepeatedHeadersFootersTransform
    | RemoveEmptyBlocksTransform
    | RemoveLiteralBoilerplateTransform
    | WebsiteSelectorsTransform
    | WebsiteMainContentTransform
    | ValidateUsefulContentTransform,
    Field(discriminator="type"),
]


class CleanNodeV2(LegacyCleanNode):
    profile: Literal["standard-v1", "structure-aware-v1"] = "standard-v1"
    config_version: Literal["deterministic-clean-v1", "structure-clean-v1"] = (
        "deterministic-clean-v1"
    )
    steps: list[CleaningTransform] = Field(
        default_factory=list, max_length=20, exclude_if=lambda value: not value
    )
    duplicate_policy: DuplicatePolicyV1 = Field(default_factory=DuplicatePolicyV1)

    @model_validator(mode="after")
    def valid_profile_and_order(self):
        if any(not value.strip() for value in self.repeated_boilerplate):
            raise ValueError("Boilerplate values cannot contain only whitespace.")
        if self.profile == "standard-v1":
            if self.config_version != "deterministic-clean-v1" or self.steps:
                raise ValueError(
                    "standard-v1 requires deterministic-clean-v1 and no ordered transforms."
                )
            return self
        if self.config_version != "structure-clean-v1":
            raise ValueError(
                "structure-aware-v1 requires the structure-clean-v1 engine."
            )
        if not self.steps:
            raise ValueError(
                "Structure-aware cleaning requires at least one transform."
            )
        ids = [step.id for step in self.steps]
        types = [step.type for step in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("Cleaning transform IDs must be unique.")
        if len(set(types)) != len(types):
            raise ValueError("Each cleaning transform type may appear only once.")
        enabled = [step.type for step in self.steps if step.enabled]

        def before(left: str, right: str):
            if (
                left in enabled
                and right in enabled
                and enabled.index(left) > enabled.index(right)
            ):
                raise ValueError(f"{left} must run before {right}.")

        for later in (
            "remove_control_characters",
            "reflow_pdf_lines",
            "dehyphenate",
            "remove_literal_boilerplate",
        ):
            before("unicode_normalize", later)
        before("preserve_structure", "reflow_pdf_lines")
        before("preserve_structure", "dehyphenate")
        before("preserve_structure", "remove_literal_boilerplate")
        before("preserve_structure", "remove_empty_blocks")
        before("reflow_pdf_lines", "dehyphenate")
        before("remove_repeated_headers_footers", "remove_empty_blocks")
        before("website_selectors", "website_main_content")
        if (
            "validate_useful_content" in enabled
            and enabled[-1] != "validate_useful_content"
        ):
            raise ValueError(
                "validate_useful_content must be the last enabled transform."
            )
        return self


class CharacterChunkNodeV2(NodeBase):
    type: Literal["chunk"]
    algorithm: Literal["character_window"] = "character_window"
    unit: Literal["characters"] = "characters"
    size: int = Field(strict=True, ge=100, le=10000)
    overlap: int = Field(strict=True, ge=0, le=9999)
    config_version: Literal["character-window-v1"] = "character-window-v1"

    @model_validator(mode="after")
    def overlap_smaller_than_size(self):
        if self.overlap >= self.size:
            raise ValueError("Chunk overlap must be smaller than chunk size.")
        return self


class SectionTokenChunkNodeV2(NodeBase):
    type: Literal["chunk"]
    algorithm: Literal["section_token"]
    unit: Literal["tokens"] = "tokens"
    tokenizer_version: Literal["utf8-byte-v1"] = "utf8-byte-v1"
    target_tokens: int = Field(default=600, strict=True, ge=64, le=8192)
    maximum_tokens: int = Field(default=800, strict=True, ge=64, le=16384)
    overlap_tokens: int = Field(default=80, strict=True, ge=0, le=4096)
    add_heading_context: bool = True
    config_version: Literal["section-token-v1"] = "section-token-v1"

    @property
    def size(self):
        return self.maximum_tokens

    @property
    def overlap(self):
        return self.overlap_tokens

    @model_validator(mode="after")
    def token_bounds(self):
        if self.target_tokens > self.maximum_tokens:
            raise ValueError("Target tokens cannot exceed the hard maximum.")
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("Token overlap must be smaller than the target.")
        return self


class ParentChildChunkNodeV2(NodeBase):
    type: Literal["chunk"]
    algorithm: Literal["parent_child"]
    unit: Literal["tokens"] = "tokens"
    tokenizer_version: Literal["utf8-byte-v1"] = "utf8-byte-v1"
    child_target_tokens: int = Field(default=240, strict=True, ge=64, le=4096)
    child_maximum_tokens: int = Field(default=320, strict=True, ge=64, le=8192)
    child_overlap_tokens: int = Field(default=40, strict=True, ge=0, le=2048)
    parent_target_tokens: int = Field(default=900, strict=True, ge=128, le=16384)
    parent_maximum_tokens: int = Field(default=1200, strict=True, ge=128, le=32768)
    add_heading_context: bool = True
    config_version: Literal["parent-child-v1"] = "parent-child-v1"

    @property
    def size(self):
        return self.child_maximum_tokens

    @property
    def overlap(self):
        return self.child_overlap_tokens

    @model_validator(mode="after")
    def token_bounds(self):
        if self.child_target_tokens > self.child_maximum_tokens:
            raise ValueError("Child target tokens cannot exceed the child maximum.")
        if self.child_overlap_tokens >= self.child_target_tokens:
            raise ValueError("Child overlap must be smaller than the child target.")
        if self.parent_target_tokens > self.parent_maximum_tokens:
            raise ValueError("Parent target tokens cannot exceed the parent maximum.")
        if self.child_maximum_tokens > self.parent_maximum_tokens:
            raise ValueError("Child maximum tokens cannot exceed the parent maximum.")
        return self


ChunkNodeV2 = CharacterChunkNodeV2 | SectionTokenChunkNodeV2 | ParentChildChunkNodeV2


IngestionNodeV2 = (
    SourceNode
    | ExtractNodeV2
    | CleanNodeV2
    | ChunkNodeV2
    | EmbedNode
    | PublishIndexNode
)


class IngestionEdge(Strict):
    source: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=80)


def _validate_supported_graph(nodes, edges):
    node_ids = [node.id for node in nodes]
    if len(set(node_ids)) != len(node_ids):
        raise ValueError("Every ingestion node ID must be unique.")
    sources = [node for node in nodes if node.type == "source"]
    if not 1 <= len(sources) <= 10:
        raise ValueError("Require between one and ten source nodes.")
    required = ["extract", "clean", "chunk", "embed", "publish_index"]
    by_type = {kind: [node for node in nodes if node.type == kind] for kind in required}
    if any(len(by_type[kind]) != 1 for kind in required):
        raise ValueError(
            "Require exactly one Extract, Clean, Chunk, Embed and Publish index node."
        )
    extract = by_type["extract"][0].id
    clean = by_type["clean"][0].id
    chunk = by_type["chunk"][0].id
    embed = by_type["embed"][0].id
    publish = by_type["publish_index"][0].id
    expected = {(node.id, extract) for node in sources}
    expected.update(
        {(extract, clean), (clean, chunk), (chunk, embed), (embed, publish)}
    )
    actual = {(edge.source, edge.target) for edge in edges}
    if len(actual) != len(edges) or actual != expected:
        raise ValueError(
            "Connect every source to Extract, followed by Clean → Chunk → Embed → Publish index only."
        )


class IngestionExecutionV1(Strict):
    schema_version: Literal[1]
    nodes: list[LegacyIngestionNode] = Field(min_length=6, max_length=15)
    edges: list[IngestionEdge] = Field(min_length=5, max_length=14)

    @model_validator(mode="after")
    def supported_graph(self):
        _validate_supported_graph(self.nodes, self.edges)
        return self


class IngestionExecutionV2(Strict):
    schema_version: Literal[2]
    nodes: list[IngestionNodeV2] = Field(min_length=6, max_length=15)
    edges: list[IngestionEdge] = Field(min_length=5, max_length=14)

    @model_validator(mode="after")
    def supported_graph(self):
        _validate_supported_graph(self.nodes, self.edges)
        return self


class IngestionExecution(
    RootModel[
        Annotated[
            IngestionExecutionV1 | IngestionExecutionV2,
            Field(discriminator="schema_version"),
        ]
    ]
):
    @property
    def schema_version(self):
        return self.root.schema_version

    @property
    def nodes(self):
        return self.root.nodes

    @property
    def edges(self):
        return self.root.edges


# Public legacy aliases remain stable for callers and schema-v1 regression tests.
ExtractNode = LegacyExtractNode
CleanNode = LegacyCleanNode
ChunkNode = LegacyChunkNode


class IngestionPosition(Strict):
    x: float = Field(ge=-100000, le=100000, allow_inf_nan=False)
    y: float = Field(ge=-100000, le=100000, allow_inf_nan=False)


class IngestionLayout(Strict):
    positions: dict[str, IngestionPosition] = Field(min_length=6, max_length=15)


class IngestionPipelineSave(Strict):
    kind: Literal["ingestion"]
    name: str = Field(min_length=1, max_length=120)
    execution: IngestionExecution
    layout: IngestionLayout

    @model_validator(mode="after")
    def layout_ids(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Pipeline name is required.")
        if set(self.layout.positions) != {node.id for node in self.execution.nodes}:
            raise ValueError("Layout must contain exactly the execution node IDs.")
        return self


class IngestionPreviewRequest(Strict):
    execution: IngestionExecution


class IngestionPreviewItem(Strict):
    source_node_id: str
    document_id: UUID
    filename: str
    media_type: str
    content_hash: str
    size_bytes: int
    included: bool
    reason: str
    processing_run_id: UUID | None = None
    processing_version: int | None = None
    chunk_count: int = 0


class IngestionPreviewRead(Strict):
    items: list[IngestionPreviewItem]
    discovered_count: int
    included_count: int
    excluded_count: int


class SourcePreviewRead(Strict):
    id: UUID
    project_id: UUID
    status: Literal["queued", "running", "succeeded", "failed", "cancelled", "expired"]
    progress: int
    discovered_count: int
    included_count: int
    excluded_count: int
    duplicate_count: int
    failed_count: int
    pass_count: int
    warn_count: int
    exclude_count: int
    quality_fail_count: int
    known_compute_ms: int
    configuration_hash: str
    fetch_mode: Literal["network", "cached-artifact", "mixed"]
    cost_basis: dict[str, Any]
    attempts: int
    failures: int
    error: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    expires_at: datetime


class SourcePreviewItemRead(Strict):
    ordinal: int
    source_node_id: str
    external_id: str | None
    display_name: str
    canonical_location: str | None
    provider_revision: str | None
    media_type: str | None
    status: Literal["included", "excluded", "duplicate", "failed"]
    reason: str
    size_bytes: int | None
    depth: int | None
    error_code: str | None
    quality_decision: Literal["pass", "warn", "exclude", "fail"] | None
    processing_status: Literal["pending", "succeeded", "failed", "skipped"]
    fetch_mode: Literal["network", "cached-artifact"]
    processing_config_hash: str | None
    findings: list[dict[str, Any]]
    metrics: dict[str, Any]
    stage_timings: dict[str, int]
    cost_basis: dict[str, Any]
    duplicate_decision: dict[str, Any] | None = None


class SourcePreviewItemPage(Strict):
    items: list[SourcePreviewItemRead]
    total: int
    limit: int
    offset: int


class SourcePreviewRepresentationRead(Strict):
    stage: Literal["raw", "extracted", "cleaned", "diff", "chunks"]
    ordinal: int
    block_type: str
    text: str
    metadata: dict[str, Any]


class SourcePreviewRepresentationPage(Strict):
    items: list[SourcePreviewRepresentationRead]
    total: int
    limit: int
    offset: int


class IngestionRunNodeRead(Strict):
    node_id: str
    node_type: Literal["source", "extract", "clean", "chunk", "embed", "publish_index"]
    ordinal: int
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    started_at: datetime | None
    finished_at: datetime | None


class IngestionRunRead(Strict):
    id: UUID
    project_id: UUID
    pipeline_version_id: UUID
    knowledge_set_id: UUID
    schedule_id: UUID | None
    source_snapshot_id: UUID | None
    trigger_kind: Literal["manual", "scheduled"]
    knowledge_set_name: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    stage: Literal["discovering", "processing", "indexing", "complete"]
    progress: int
    discovered_count: int
    processed_count: int
    failed_count: int
    new_count: int = 0
    changed_count: int = 0
    unchanged_count: int = 0
    removed_count: int = 0
    chunk_count: int
    embedded_count: int
    published_count: int
    attempts: int
    failures: int
    node_states: list[IngestionRunNodeRead]
    error: str | None
    published_index_id: UUID | None
    published_index_version: int | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RefreshSourceInput(Strict):
    kind: Literal["refresh"]


class SnapshotSourceInput(Strict):
    kind: Literal["snapshot"]
    source_snapshot_id: UUID


IngestionSourceInput = Annotated[
    RefreshSourceInput | SnapshotSourceInput,
    Field(discriminator="kind"),
]


class ExistingIndexDestination(Strict):
    kind: Literal["existing"]
    knowledge_set_id: UUID


class NewIndexDestination(Strict):
    kind: Literal["new"]
    name: str = Field(min_length=1, max_length=120)


IngestionDestination = Annotated[
    ExistingIndexDestination | NewIndexDestination,
    Field(discriminator="kind"),
]


class IngestionRunStart(Strict):
    source_input: IngestionSourceInput | None = None
    destination: IngestionDestination | None = None
    # Temporary compatibility adapter for the pre-snapshot frontend.
    reuse_stored: bool | None = None

    @model_validator(mode="after")
    def compatible_source_input(self):
        if self.source_input is not None and self.reuse_stored is not None:
            raise ValueError("Use source_input or reuse_stored, not both.")
        return self


class IngestionRunPage(Strict):
    items: list[IngestionRunRead]
    total: int
    limit: int
    offset: int


class ExistingIngestionRunItemRead(Strict):
    source_kind: Literal["existing_files"] = "existing_files"
    document_id: UUID
    filename: str
    content_hash: str
    media_type: str
    source_node_id: str
    processing_run_id: UUID
    processing_version: int
    processing_created: bool
    status: Literal["processing", "ready", "succeeded", "failed", "cancelled"]
    chunk_count: int
    error: str | None
    processing_versions: dict[str, str] | None = None
    duplicate_decision: dict | None = None
    updated_at: datetime


class WebsiteIngestionRunItemRead(Strict):
    source_kind: Literal["website"] = "website"
    ordinal: int
    source_node_id: str
    source_item_id: UUID | None
    source_revision_id: UUID | None
    processing_run_id: UUID | None = None
    canonical_location: str | None
    display_name: str
    media_type: str | None
    outcome: Literal[
        "new", "changed", "unchanged", "removed", "excluded", "duplicate", "failed"
    ]
    status: Literal["ready", "succeeded", "failed", "cancelled"]
    reason: str
    chunk_count: int
    error: str | None
    processing_versions: dict[str, str] | None = None
    duplicate_decision: dict | None = None
    updated_at: datetime


class S3IngestionRunItemRead(Strict):
    source_kind: Literal["s3"] = "s3"
    ordinal: int
    source_node_id: str
    source_item_id: UUID | None
    source_revision_id: UUID | None
    processing_run_id: UUID | None = None
    canonical_location: str | None
    display_name: str
    media_type: str | None
    outcome: Literal[
        "new", "changed", "unchanged", "removed", "excluded", "duplicate", "failed"
    ]
    status: Literal["ready", "succeeded", "failed", "cancelled"]
    reason: str
    chunk_count: int
    error: str | None
    processing_versions: dict[str, str] | None = None
    duplicate_decision: dict | None = None
    updated_at: datetime


class NotionIngestionRunItemRead(S3IngestionRunItemRead):
    source_kind: Literal["notion"] = "notion"


class ConfluenceIngestionRunItemRead(S3IngestionRunItemRead):
    source_kind: Literal["confluence"] = "confluence"


IngestionRunItemRead = Annotated[
    ExistingIngestionRunItemRead
    | WebsiteIngestionRunItemRead
    | S3IngestionRunItemRead
    | NotionIngestionRunItemRead
    | ConfluenceIngestionRunItemRead,
    Field(discriminator="source_kind"),
]


class IngestionRunItemPage(Strict):
    items: list[IngestionRunItemRead]
    total: int
    limit: int
    offset: int
