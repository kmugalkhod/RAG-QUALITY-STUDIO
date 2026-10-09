"""Provider-reported embedding usage and cost (spec 0007, slice 6)."""

from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from sqlalchemy.orm import Session

from app.models.index import IndexVersion
from app.providers import embeddings
from app.providers.embeddings import EmbeddingUsage
from app.providers.openrouter import OpenRouterEmbeddings
from app.workers.indexing import process_index
from app.workers.processing import process
from test_documents import documents_api, start  # noqa: F401
from test_indexes import create, embedding_config, index_api, prepared  # noqa: F401


def _adapter(config, usage):
    payload = {
        "model": config.model,
        "data": [{"index": 0, "embedding": [1, 0, 0]}],
    }
    if usage is not None:
        payload["usage"] = usage
    return OpenRouterEmbeddings(
        config,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )


@pytest.mark.parametrize(
    "usage,expected",
    [
        ({"prompt_tokens": 7, "total_tokens": 7, "cost": 0.00014}, (7, 0.00014)),
        ({"prompt_tokens": 7, "total_tokens": 7}, (7, None)),
        ({"total_tokens": -1, "cost": "free"}, (None, None)),
        (None, (None, None)),
    ],
)
def test_adapter_returns_reported_usage(embedding_config, usage, expected):  # noqa: F811
    vectors, reported = _adapter(embedding_config, usage).embed_with_usage(["a"])
    assert vectors == [[1, 0, 0]]
    assert reported == EmbeddingUsage(*expected)


class UsageDouble:
    def __init__(self, usage):
        self.usage = usage
        self.calls = []

    def embed_with_usage(self, texts):
        self.calls.append(texts)
        return [[1.0, 0.0, 0.0] for _ in texts], self.usage


def _usage(engine, index_id):
    with Session(engine) as session:
        index = session.get(IndexVersion, UUID(index_id))
        return index.embedding_tokens, index.embedding_cost_usd


def test_index_adds_reported_usage_and_reuse_adds_nothing(index_api, monkeypatch):  # noqa: F811
    client, engine, p, _, _ = index_api
    provider = UsageDouble(EmbeddingUsage(12, 0.0003))
    monkeypatch.setattr(embeddings, "provider_for", lambda _: provider)
    doc, _ = prepared(client, engine, p)
    first = create(client, p)
    process_index(UUID(first["id"]), engine)
    assert provider.calls
    assert _usage(engine, first["id"]) == (12, Decimal("0.0003"))

    # Same text and config: every vector is reused, so no provider call and zero usage.
    again = start(client, p, doc["id"])
    process(UUID(again["id"]), engine)
    provider.calls.clear()
    second = create(client, p)
    process_index(UUID(second["id"]), engine)
    assert provider.calls == []
    assert _usage(engine, second["id"]) == (0, Decimal("0"))


def test_unreported_usage_stays_unknown(index_api, monkeypatch):  # noqa: F811
    client, engine, p, _, _ = index_api
    provider = UsageDouble(EmbeddingUsage(5, None))
    monkeypatch.setattr(embeddings, "provider_for", lambda _: provider)
    prepared(client, engine, p)
    index = create(client, p)
    process_index(UUID(index["id"]), engine)
    # Tokens were reported, cost was not: cost is unknown, never zero.
    assert _usage(engine, index["id"]) == (5, None)
