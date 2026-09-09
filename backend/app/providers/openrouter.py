"""OpenRouter embeddings REST adapter; retries belong to the durable indexing worker."""

import json
import httpx
from app.core.config import settings
from app.providers.rate_limit import reserve_request
from app.providers.embeddings import EmbeddingConfig, EmbeddingError, validate_vectors


class OpenRouterEmbeddings:
    def __init__(self, config: EmbeddingConfig, transport=None):
        self.config = config
        self.transport = transport

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Conservative UTF-8 byte limit bounds tokens without truncating source text.
        if (
            not texts
            or len(texts) > 16
            or any(not t.strip() or len(t.encode("utf-8")) > 8191 for t in texts)
        ):
            raise EmbeddingError(
                "Embedding input must be nonempty and at most 8,191 UTF-8 bytes per chunk/query. Reprocess oversized chunks with a smaller chunk size."
            )
        reserve_request()
        try:
            with httpx.Client(
                timeout=httpx.Timeout(40, connect=5),
                transport=self.transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                with client.stream(
                    "POST",
                    settings.embedding_base_url.rstrip("/") + "/embeddings",
                    headers={
                        "Authorization": "Bearer "
                        + settings.openrouter_api_key.get_secret_value()
                    },
                    json={
                        "model": self.config.model,
                        "dimensions": self.config.dimensions,
                        "encoding_format": "float",
                        "input": texts,
                    },
                ) as response:
                    if response.status_code in (401, 403):
                        raise EmbeddingError(
                            "OpenRouter rejected the credentials. Check server-side OPENROUTER_API_KEY and model access."
                        )
                    if response.status_code == 402:
                        raise EmbeddingError(
                            "OpenRouter has insufficient credits. Add credits to the configured account and retry."
                        )
                    if (
                        response.status_code in (408, 429)
                        or response.status_code >= 500
                    ):
                        raise EmbeddingError(
                            "OpenRouter rate limit or temporary service failure. Indexing retries are bounded; retrieval can be retried.",
                            transient=True,
                        )
                    if response.status_code != 200:
                        raise EmbeddingError(
                            "OpenRouter rejected the embedding request. Check model settings and chunk size."
                        )
                    body = bytearray()
                    for block in response.iter_bytes():
                        body.extend(block)
                        if len(body) > 4_000_000:
                            raise EmbeddingError(
                                "Embedding provider response exceeds the size limit."
                            )
            payload = json.loads(body)
            # OpenRouter may return the upstream OpenAI name without its namespace.
            # Accept only the exact alias of the requested, supported model.
            accepted_models = {self.config.model}
            if self.config.model in {
                "openai/text-embedding-3-small",
                "openai/text-embedding-3-large",
            }:
                accepted_models.add(self.config.model.removeprefix("openai/"))
            if payload.get("model") not in accepted_models:
                raise EmbeddingError("Embedding provider returned a different model.")
            data = payload["data"]
            if (
                not isinstance(data, list)
                or len(data) != len(texts)
                or any(type(item.get("index")) is not int for item in data)
            ):
                raise ValueError()
            if sorted(item["index"] for item in data) != list(range(len(texts))):
                raise ValueError()
            vectors = [
                item["embedding"]
                for item in sorted(data, key=lambda item: item["index"])
            ]
            return validate_vectors(vectors, len(texts), self.config.dimensions)
        except httpx.HTTPError:
            raise EmbeddingError(
                "OpenRouter connection unavailable or timed out.", transient=True
            ) from None
        except (ValueError, KeyError, TypeError, AttributeError):
            raise EmbeddingError(
                "OpenRouter returned a malformed embedding response."
            ) from None
