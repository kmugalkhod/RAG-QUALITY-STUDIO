"""Strict, versioned ingestion graph configuration.

This module defines persisted configuration only. Execution, knowledge sets and
connector transports are introduced by later ingestion phases.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


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


SourceConfig = Annotated[
    ExistingFilesConfig | WebsiteConfig, Field(discriminator="kind")
]


class NodeBase(Strict):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


class SourceNode(NodeBase):
    type: Literal["source"]
    config: SourceConfig


class ExtractNode(NodeBase):
    type: Literal["extract"]
    strategy: Literal["media_type_registry"] = "media_type_registry"
    config_version: str = Field(default="1", min_length=1, max_length=40)


class CleanNode(NodeBase):
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


class ChunkNode(NodeBase):
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


IngestionNode = Annotated[
    SourceNode | ExtractNode | CleanNode | ChunkNode | EmbedNode | PublishIndexNode,
    Field(discriminator="type"),
]


class IngestionEdge(Strict):
    source: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=80)


class IngestionExecution(Strict):
    schema_version: Literal[1]
    nodes: list[IngestionNode] = Field(min_length=6, max_length=15)
    edges: list[IngestionEdge] = Field(min_length=5, max_length=14)

    @model_validator(mode="after")
    def supported_graph(self):
        node_ids = [node.id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("Every ingestion node ID must be unique.")
        sources = [node for node in self.nodes if node.type == "source"]
        if not 1 <= len(sources) <= 10:
            raise ValueError("Require between one and ten source nodes.")
        required = ["extract", "clean", "chunk", "embed", "publish_index"]
        by_type = {
            kind: [node for node in self.nodes if node.type == kind]
            for kind in required
        }
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
        actual = {(edge.source, edge.target) for edge in self.edges}
        if len(actual) != len(self.edges) or actual != expected:
            raise ValueError(
                "Connect every source to Extract, followed by Clean → Chunk → Embed → Publish index only."
            )
        return self


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
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: int
    discovered_count: int
    included_count: int
    excluded_count: int
    duplicate_count: int
    failed_count: int
    attempts: int
    failures: int
    error: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SourcePreviewItemRead(Strict):
    ordinal: int
    source_node_id: str
    external_id: str | None
    display_name: str
    canonical_location: str | None
    media_type: str | None
    status: Literal["included", "excluded", "duplicate", "failed"]
    reason: str
    size_bytes: int | None
    depth: int | None
    error_code: str | None


class SourcePreviewItemPage(Strict):
    items: list[SourcePreviewItemRead]
    total: int
    limit: int
    offset: int


class IngestionRunRead(Strict):
    id: UUID
    project_id: UUID
    pipeline_version_id: UUID
    knowledge_set_id: UUID
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
    error: str | None
    published_index_id: UUID | None
    published_index_version: int | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


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
    updated_at: datetime


class WebsiteIngestionRunItemRead(Strict):
    source_kind: Literal["website"] = "website"
    ordinal: int
    source_node_id: str
    source_item_id: UUID | None
    source_revision_id: UUID | None
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
    updated_at: datetime


IngestionRunItemRead = Annotated[
    ExistingIngestionRunItemRead | WebsiteIngestionRunItemRead,
    Field(discriminator="source_kind"),
]


class IngestionRunItemPage(Strict):
    items: list[IngestionRunItemRead]
    total: int
    limit: int
    offset: int
