from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
import re
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_TEMPLATE = "Answer the question concisely using the retrieved context.\nQuestion: {question}\nRetrieved context: {context}"
ORDER = ["question", "retriever", "prompt", "llm", "answer"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NodeBase(Strict):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


class Question(NodeBase):
    type: Literal["question"]


class Retriever(NodeBase):
    type: Literal["retriever"]
    index_id: UUID
    top_k: int = Field(strict=True, ge=1, le=50)


class Prompt(NodeBase):
    type: Literal["prompt"]
    template: str = Field(min_length=1, max_length=8000)

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
    Question | Retriever | Prompt | LLM | Answer, Field(discriminator="type")
]


class Edge(Strict):
    source: str
    target: str


class Execution(Strict):
    schema_version: Literal[1]
    nodes: list[Node] = Field(min_length=5, max_length=5)
    edges: list[Edge] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def supported_graph(self):
        by_type = {n.type: n.id for n in self.nodes}
        if set(by_type) != set(ORDER) or len({n.id for n in self.nodes}) != 5:
            raise ValueError(
                "Require exactly one of each node with unique IDs: Question, Retriever, Prompt, LLM, Answer."
            )
        expected = {(by_type[a], by_type[b]) for a, b in zip(ORDER, ORDER[1:])}
        if {(e.source, e.target) for e in self.edges} != expected:
            raise ValueError(
                "Connect Question → Retriever → Prompt → LLM → Answer only. Cycles, branches and disconnected nodes are unsupported."
            )
        return self


class Position(Strict):
    x: float = Field(ge=-100000, le=100000, allow_inf_nan=False)
    y: float = Field(ge=-100000, le=100000, allow_inf_nan=False)


class Layout(Strict):
    positions: dict[str, Position] = Field(max_length=5)


class PipelineSave(Strict):
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
    execution: Execution
    layout: Layout
    created_at: datetime


class PipelineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    name: str
    created_at: datetime


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
