"""Spec 0012 C6 and D7: larger embedding batches and a fair request budget."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.index import IndexChunk, IndexVersion
from app.providers import embeddings
from app.providers.rate_limit import request_share, reserve_request
from app.workers import indexing
from app.workers.indexing import process_index
from test_documents import documents_api, upload  # noqa: F401
from test_existing_files_ingestion import (  # noqa: F401
    ingestion_api,
    ingestion_draft,
)
from test_publish_destinations import _run_to_completion


@pytest.fixture
def api(ingestion_api):  # noqa: F811
    return ingestion_api


def test_indexing_leaves_a_quarter_of_the_request_budget_for_queries(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(
        "app.providers.rate_limit.Redis.from_url", lambda *a, **kw: connection
    )
    monkeypatch.setattr(settings, "embedding_requests_per_minute", 60)
    connection.eval.side_effect = [45, 46, 46, 60, 61]
    with request_share(indexing.INDEXING_REQUEST_SHARE):
        reserve_request()  # the 45th request this minute
        with pytest.raises(embeddings.EmbeddingError, match="budget") as refused:
            reserve_request()
    assert refused.value.throttled
    reserve_request()  # a query may still use requests 46 to 60
    reserve_request()
    with pytest.raises(embeddings.EmbeddingError, match="budget"):
        reserve_request()


def test_identical_texts_in_a_batch_are_embedded_once(api, monkeypatch):
    client, engine, project_id, _, config, provider = api
    # Two files with the same text give identical passages in one batch.
    text = b"Lanterns light the archive. Maps cover the harbour hall. " * 4
    first = upload(client, project_id, text, "one.txt")
    second = upload(client, project_id, text, "two.txt")
    payload = ingestion_draft(
        [first["id"], second["id"]], config, name="Twins", schema_version=2
    )
    clean = next(n for n in payload["execution"]["nodes"] if n["type"] == "clean")
    # Keep both files: duplicate detection would otherwise index only one.
    clean["duplicate_policy"] = {
        "exact_raw": False,
        "exact_cleaned": False,
        "normalized_sections": False,
    }
    version = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    run = _run_to_completion(client, engine, project_id, version)
    assert run["status"] == "succeeded"
    with Session(engine) as session:
        index = session.get(IndexVersion, run["published_index_id"])
        members = session.scalars(
            select(IndexChunk).where(IndexChunk.index_id == index.id)
        ).all()
    sent = [value for call in provider.calls for value in call]
    assert len(members) == 2 * len(set(sent))
    assert len(sent) == len(set(sent))
    assert all(member.embedding is not None for member in members)
    assert index.embedded_count == index.chunk_count == len(members)
    # Nothing left to embed: another delivery is a no-op.
    process_index(index.id, engine)
