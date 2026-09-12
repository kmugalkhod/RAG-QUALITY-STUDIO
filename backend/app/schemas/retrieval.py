"""Versioned search behavior, shared by every retrieval execution path."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SearchBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    top_k: int = Field(default=5, strict=True, ge=1, le=50)


class VectorSearch(SearchBase):
    mode: Literal["vector"] = "vector"
    max_vector_distance: float | None = Field(
        default=None, ge=0, le=2, strict=True, allow_inf_nan=False
    )


class KeywordSearch(SearchBase):
    mode: Literal["keyword"]


class HybridSearch(SearchBase):
    mode: Literal["hybrid"]
    max_vector_distance: float | None = Field(
        default=None, ge=0, le=2, strict=True, allow_inf_nan=False
    )
    vector_candidates: int = Field(default=50, strict=True, ge=1, le=200)
    keyword_candidates: int = Field(default=50, strict=True, ge=1, le=200)
    vector_weight: float = Field(
        default=0.5, ge=0, le=1, strict=True, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def candidate_bounds(self):
        if min(self.vector_candidates, self.keyword_candidates) < self.top_k:
            raise ValueError("Each candidate count must be at least Top k.")
        return self


RetrievalSettings = Annotated[
    VectorSearch | KeywordSearch | HybridSearch, Field(discriminator="mode")
]


class RetrievalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    retrieval: RetrievalSettings = Field(default_factory=VectorSearch)

    @model_validator(mode="before")
    @classmethod
    def legacy_top_k(cls, value):
        if isinstance(value, dict) and "top_k" in value:
            if "retrieval" in value:
                raise ValueError("Supply retrieval settings or legacy top_k, not both.")
            value = dict(value)
            value["retrieval"] = {"mode": "vector", "top_k": value.pop("top_k")}
        return value

    @property
    def top_k(self):
        return self.retrieval.top_k


def settings_from_node(node: dict) -> dict:
    """Normalize immutable legacy experiment nodes without rewriting them."""
    return node.get("retrieval") or {"mode": "vector", "top_k": node["top_k"]}


def algorithm_snapshot():
    return {
        "version": "retrieval-v2",
        "lexical_config": "simple",
        "lexical_rank": "ts_rank_cd",
        "rrf_constant": 60,
    }
