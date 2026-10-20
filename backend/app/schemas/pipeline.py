from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
import re
from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    model_serializer,
    model_validator,
)

from app.schemas.retrieval import RetrievalSettings, VectorSearch
from app.schemas.ingestion import (
    IngestionExecution,
    IngestionLayout,
    IngestionPipelineSave,
)
from app.schemas.setting_recommendations import SettingsProvenanceV1

DEFAULT_TEMPLATE = "Answer the question concisely using the retrieved context.\nQuestion: {question}\nRetrieved context: {context}"
ORDER = ["question", "retriever", "prompt", "llm", "answer"]
# Schema v3 (spec 0015): the one shape with an optional Rerank node.
RERANK_ORDER = ["question", "retriever", "rerank", "prompt", "llm", "answer"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NodeBase(Strict):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


class Question(NodeBase):
    type: Literal["question"]


class Retriever(NodeBase):
    type: Literal["retriever"]
    index_id: UUID
    top_k: int | None = Field(default=None, strict=True, ge=1, le=50)
    retrieval: RetrievalSettings | None = None

    @property
    def settings(self):
        return self.retrieval or VectorSearch(top_k=self.top_k)

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        return {k: v for k, v in handler(self).items() if v is not None}


class Rerank(NodeBase):
    """Reorders the retrieved candidates with a chat model; keeps the first top_n."""

    type: Literal["rerank"]
    model: str = Field(min_length=1, max_length=200)
    top_n: int = Field(default=5, strict=True, ge=1, le=20)


class Prompt(NodeBase):
    type: Literal["prompt"]
    template: str = Field(min_length=1, max_length=8000)
    # Absent on versions saved before complete-v2; they keep the strict-v1 prompt.
    answer_policy: Literal["strict-v1", "complete-v2"] | None = None

    @property
    def policy(self):
        return self.answer_policy or "strict-v1"

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        return {k: v for k, v in handler(self).items() if v is not None}

    @model_validator(mode="after")
    def safe_template(self):
        remainder = self.template.replace("{question}", "").replace("{context}", "")
        if re.search(r"[{}]", remainder) or any(
            v not in self.template for v in ("{question}", "{context}")
        ):
            raise ValueError(
                "Prompt must contain {question} and {context}; no other braces or expressions are supported."
            )
        return self


class LLM(NodeBase):
    type: Literal["llm"]
    model: str = Field(min_length=1, max_length=200)
    max_tokens: int = Field(strict=True, ge=128, le=8192)
    temperature: float = Field(ge=0, le=2, allow_inf_nan=False)


class Answer(NodeBase):
    type: Literal["answer"]


Node = Annotated[
    Question | Retriever | Rerank | Prompt | LLM | Answer, Field(discriminator="type")
]


class Edge(Strict):
    source: str
    target: str


class Execution(Strict):
    schema_version: Literal[1, 2, 3]
    nodes: list[Node] = Field(min_length=5, max_length=6)
    edges: list[Edge] = Field(min_length=4, max_length=5)

    @model_validator(mode="after")
    def supported_graph(self):
        for node in self.nodes:
            if node.type == "retriever":
                if self.schema_version == 1 and (
                    node.top_k is None or node.retrieval is not None
                ):
                    raise ValueError("Schema v1 requires legacy top_k only.")
                if self.schema_version in (2, 3) and (
                    node.retrieval is None or node.top_k is not None
                ):
                    raise ValueError(
                        f"Schema v{self.schema_version} requires retrieval settings only."
                    )
        order = RERANK_ORDER if self.schema_version == 3 else ORDER
        by_type = {n.type: n.id for n in self.nodes}
        if set(by_type) != set(order) or len({n.id for n in self.nodes}) != len(order):
            if self.schema_version == 3:
                raise ValueError(
                    "Schema v3 requires exactly one of each node with unique IDs: Question, Retriever, Rerank, Prompt, LLM, Answer."
                )
            raise ValueError(
                "Require exactly one of each node with unique IDs: Question, Retriever, Prompt, LLM, Answer."
            )
        expected = {(by_type[a], by_type[b]) for a, b in zip(order, order[1:])}
        if {(e.source, e.target) for e in self.edges} != expected:
            if self.schema_version == 3:
                raise ValueError(
                    "Connect Question → Retriever → Rerank → Prompt → LLM → Answer only. Cycles, branches and disconnected nodes are unsupported."
                )
            raise ValueError(
                "Connect Question → Retriever → Prompt → LLM → Answer only. Cycles, branches and disconnected nodes are unsupported."
            )
        if self.schema_version == 3:
            nodes = {n.type: n for n in self.nodes}
            if nodes["retriever"].settings.top_k < nodes["rerank"].top_n:
                raise ValueError(
                    "Retriever Top k is the number of candidates to rerank; it must be at least the Rerank node's passages kept."
                )
        return self


class Position(Strict):
    x: float = Field(ge=-100000, le=100000, allow_inf_nan=False)
    y: float = Field(ge=-100000, le=100000, allow_inf_nan=False)


class Layout(Strict):
    positions: dict[str, Position] = Field(max_length=6)


class PipelineSave(Strict):
    kind: Literal["answer"] = "answer"
    name: str = Field(min_length=1, max_length=120)
    execution: Execution
    layout: Layout

    @model_validator(mode="after")
    def layout_ids(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Pipeline name is required.")
        if set(self.layout.positions) != {n.id for n in self.execution.nodes}:
            raise ValueError("Layout must contain exactly the execution node IDs.")
        return self


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    pipeline_id: UUID
    project_id: UUID
    version: int
    name: str
    execution: Execution | IngestionExecution
    layout: Layout | IngestionLayout
    # Recommended-settings provenance (spec 0011); None when none was recorded.
    settings_provenance: SettingsProvenanceV1 | None = None
    created_at: datetime


class LatestVersionRead(BaseModel):
    version: int
    created_at: datetime


class LastRunRead(BaseModel):
    """The newest ingestion run of any version of a pipeline (spec 0015 U1)."""

    id: UUID
    pipeline_version: int
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    # For a succeeded run: `with_warnings` when an item or a source failed.
    completion: Literal["complete", "with_warnings"] | None
    created_at: datetime
    finished_at: datetime | None


class PublishedIndexRead(BaseModel):
    """The newest index a pipeline's runs published, and whether it is current."""

    id: UUID
    version: int
    knowledge_set_id: UUID
    knowledge_set_name: str
    is_current: bool


class PipelineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    name: str
    kind: Literal["answer", "ingestion"]
    created_at: datetime
    # List rows only (spec 0015 D8); older clients ignore them.
    latest_version: LatestVersionRead | None = None
    last_run: LastRunRead | None = None
    published_index: PublishedIndexRead | None = None


class PipelinePage(BaseModel):
    items: list[PipelineRead]
    total: int
    limit: int
    offset: int


class VersionPage(BaseModel):
    items: list[VersionRead]
    total: int
    limit: int
    offset: int


class RunRequest(Strict):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=8000)


class PreviewRequest(RunRequest):
    execution: Execution
    base_pipeline_id: UUID | None = None
    base_version_id: UUID | None = None

    @model_validator(mode="after")
    def paired_base(self):
        if (self.base_pipeline_id is None) != (self.base_version_id is None):
            raise ValueError("Provide both base pipeline and version, or neither.")
        return self


def _save_kind(value):
    # Answer saves may omit `kind`, which defaults to "answer".
    if isinstance(value, dict):
        return value.get("kind", "answer")
    return getattr(value, "kind", "answer")


# The kind selects one branch, so a bad value reports one error instead of one
# per pipeline kind (spec 0012 A13).
PipelineSaveRequest = Annotated[
    Annotated[PipelineSave, Tag("answer")]
    | Annotated[IngestionPipelineSave, Tag("ingestion")],
    Discriminator(
        _save_kind,
        custom_error_type="invalid_pipeline_kind",
        custom_error_message="Pipeline kind must be answer or ingestion.",
    ),
]
