"""Provider contract. Live operation must never fall back to synthetic vectors."""

import math
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class EmbeddingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: str
    model: str = Field(min_length=1, max_length=200)
    dimensions: int = Field(strict=True, ge=1, le=16000)
    endpoint_id: str  # Fingerprint, never credentials or the private endpoint URL.
    revision: str = "1"


class EmbeddingError(Exception):
    def __init__(self, message: str, *, transient: bool = False):
        super().__init__(message)
        self.transient = transient


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def validate_vectors(vectors, count: int, dimensions: int) -> list[list[float]]:
    if not isinstance(vectors, list) or len(vectors) != count:
        raise EmbeddingError("Embedding provider returned an invalid vector count.")
    result = []
    for vector in vectors:
        if (
            not isinstance(vector, list)
            or len(vector) != dimensions
            or any(
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or not math.isfinite(v)
                or abs(v) > 3.4e38
                for v in vector
            )
            or not any(abs(v) >= 1.17549435e-38 for v in vector)
        ):
            raise EmbeddingError(
                "Embedding provider returned invalid dimensions or non-finite/zero vectors."
            )
        result.append([float(v) for v in vector])
    return result


def configured() -> EmbeddingConfig:
    from hashlib import sha256
    from app.core.config import settings

    if settings.embedding_provider != "openrouter":
        raise EmbeddingError(
            "Unsupported embedding provider. Set EMBEDDING_PROVIDER=openrouter."
        )
    if not settings.openrouter_api_key.get_secret_value().strip():
        raise EmbeddingError(
            "Set OPENROUTER_API_KEY in the server environment, then restart the backend and worker."
        )
    if settings.embedding_base_url.rstrip("/") != "https://openrouter.ai/api/v1":
        raise EmbeddingError(
            "This adapter supports https://openrouter.ai/api/v1. Configure EMBEDDING_BASE_URL accordingly."
        )
    if settings.embedding_model not in {
        "openai/text-embedding-3-small",
        "openai/text-embedding-3-large",
    }:
        raise EmbeddingError("Configure a supported OpenRouter text-embedding-3 model.")
    maximum = (
        1536 if settings.embedding_model == "openai/text-embedding-3-small" else 3072
    )
    if settings.embedding_dimensions > maximum:
        raise EmbeddingError(
            "EMBEDDING_DIMENSIONS exceeds the configured model's dimensions."
        )
    return EmbeddingConfig(
        provider="openrouter",
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        endpoint_id=sha256(
            settings.embedding_base_url.rstrip("/").encode()
        ).hexdigest(),
        revision=settings.embedding_revision,
    )


def provider_for(config: EmbeddingConfig) -> EmbeddingProvider:
    if configured() != config:
        raise EmbeddingError(
            "The saved index uses a different embedding configuration. Restore that server configuration or create a new index."
        )
    from app.providers.openrouter import OpenRouterEmbeddings

    return OpenRouterEmbeddings(config)
