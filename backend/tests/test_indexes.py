import json
from datetime import timedelta
from uuid import UUID, uuid4
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select, update, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.index import IndexChunk, IndexVersion, KnowledgeSet
from app.providers import embeddings
from app.providers.openrouter import OpenRouterEmbeddings
from app.workers.indexing import process_index
from app.workers.dispatcher import dispatch_indexes_once
from app.workers.processing import now, process
from test_documents import documents_api, upload, start  # noqa: F401


@pytest.fixture
def embedding_config(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("test-only-secret"))
    monkeypatch.setattr(settings, "embedding_dimensions", 3)
    monkeypatch.setattr("app.providers.openrouter.reserve_request", lambda: None)
    return embeddings.configured()


class ProviderDouble:
    """Deterministic vectors exist only in tests; production has no fake mode."""

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(texts)
        return [
            [1.0, 0.0, 0.0] if t.startswith("abc") else [0.0, 1.0, 0.0] for t in texts
        ]


@pytest.fixture
def index_api(documents_api, embedding_config, monkeypatch):  # noqa: F811
    client, engine, p, q = documents_api
    provider = ProviderDouble()
    monkeypatch.setattr(embeddings, "provider_for", lambda config: provider)
    yield client, engine, p, q, provider
    with Session(engine) as session:
        ids = select(IndexVersion.id).where(
            IndexVersion.project_id.in_([UUID(p), UUID(q)])
        )
        session.execute(delete(IndexChunk).where(IndexChunk.index_id.in_(ids)))
        session.execute(delete(IndexVersion).where(IndexVersion.id.in_(ids)))
        session.commit()


def prepared(client, engine, p):
    doc = upload(client, p)
    run = start(client, p, doc["id"])
    process(UUID(run["id"]), engine)
    return doc, run


def create(client, p):
    response = client.post(f"/api/projects/{p}/indexes")
    assert response.status_code == 202, response.text
    return response.json()


def search(client, p, index, **kwargs):
    return client.post(
        f"/api/projects/{p}/retrieval",
        json={"index_id": index["id"], "query": "abcd", "top_k": 2, **kwargs},
    )


def test_snapshot_retrieval_provenance_scope_and_reuse(index_api):
    client, engine, p, q, provider = index_api
    doc, run = prepared(client, engine, p)
    index = create(client, p)
    route = f"/api/projects/{p}/indexes/{index['id']}"
    assert index["embedding_config"]["provider"] == "openrouter"
    assert index["knowledge_set_name"] == "Uploaded documents"
    assert index["processing_run_count"] == 1
    assert index["is_current"] is False
    assert "secret" not in json.dumps(index) and "execution_token" not in index
    assert client.post(f"/api/projects/{p}/indexes").status_code == 409
    assert search(client, p, index).status_code == 409
    assert search(client, q, index).status_code == 404
    assert client.get(route.replace(p, q)).status_code == 404
    assert client.post(route.replace(p, q) + "/cancel").status_code == 404
    assert client.get(f"/api/projects/{q}/indexes").json()["total"] == 0
    # Processing after snapshot creation cannot replace its exact membership.
    next_run = start(client, p, doc["id"], 5, 0)
    process(UUID(next_run["id"]), engine)
    process_index(UUID(index["id"]), engine)
    process_index(UUID(index["id"]), engine)
    ready = client.get(route).json()
    assert (
        ready["status"] == "succeeded"
        and ready["embedded_count"] == 3
        and ready["attempts"] == 1
    )
    assert ready["is_current"] is True
    sets = client.get(f"/api/projects/{p}/knowledge-sets").json()
    assert sets["total"] == 1
    assert sets["items"][0]["current_ready_index_id"] == index["id"]
    assert (
        client.get(
            f"/api/projects/{p}/knowledge-sets/{index['knowledge_set_id']}/indexes"
        ).json()["items"][0]["id"]
        == index["id"]
    )
    assert (
        client.get(
            f"/api/projects/{q}/knowledge-sets/{index['knowledge_set_id']}/indexes"
        ).status_code
        == 404
    )
    result = search(client, p, index).json()
    first = result["items"][0]
    assert result["index_version"] == 1
    assert first["text"] == "abcd" and first["cosine_distance"] == pytest.approx(0)
    assert first["run_id"] == run["id"] and first["processing_version"] == 1
    assert (
        first["document_id"] == doc["id"]
        and first["content_hash"] == doc["content_hash"]
    )
    assert first["start_char"] == 0 and first["end_char"] == 4
    assert result["items"][1]["cosine_distance"] == pytest.approx(1)
    # A new run with identical text windows can reuse project-local vectors.
    matching = start(client, p, doc["id"])
    process(UUID(matching["id"]), engine)
    replacement = create(client, p)
    provider.calls.clear()
    process_index(UUID(replacement["id"]), engine)
    assert provider.calls == []
    assert search(client, p, index).status_code == 200
    # An identical document in another project must call its provider anew.
    prepared(client, engine, q)
    other = create(client, q)
    provider.calls.clear()
    process_index(UUID(other["id"]), engine)
    assert len(provider.calls) == 1
    assert (
        client.get(f"/api/projects/{p}/indexes?limit=1&offset=1").json()["items"][0][
            "id"
        ]
        == index["id"]
    )


def test_explicit_document_snapshot_and_project_boundaries(index_api):
    client, engine, p, q, _ = index_api
    selected = upload(client, p, b"selected text", "selected.txt")
    selected_run = start(client, p, selected["id"], 20, 0)
    process(UUID(selected_run["id"]), engine)
    ignored = upload(client, p, b"ignored text", "ignored.txt")
    ignored_run = start(client, p, ignored["id"], 20, 0)
    process(UUID(ignored_run["id"]), engine)
    foreign = upload(client, q, b"foreign text", "foreign.txt")
    foreign_run = start(client, q, foreign["id"], 20, 0)
    process(UUID(foreign_run["id"]), engine)

    response = client.post(
        f"/api/projects/{p}/indexes", json={"document_ids": [selected["id"]]}
    )
    assert response.status_code == 202, response.text
    index = response.json()
    assert index["processing_run_count"] == 1 and index["chunk_count"] == 1
    with Session(engine) as session:
        assert set(
            session.scalars(
                select(IndexChunk.run_id).where(
                    IndexChunk.index_id == UUID(index["id"])
                )
            )
        ) == {UUID(selected_run["id"])}

    newer = start(client, p, selected["id"], 5, 0)
    process(UUID(newer["id"]), engine)
    with Session(engine) as session:
        assert set(
            session.scalars(
                select(IndexChunk.run_id).where(
                    IndexChunk.index_id == UUID(index["id"])
                )
            )
        ) == {UUID(selected_run["id"])}

    assert (
        client.post(
            f"/api/projects/{p}/indexes", json={"document_ids": [foreign["id"]]}
        ).status_code
        == 404
    )
    foreign_set = client.get(f"/api/projects/{q}/knowledge-sets").json()["items"][0]
    assert (
        client.post(
            f"/api/projects/{p}/indexes",
            json={
                "knowledge_set_id": foreign_set["id"],
                "document_ids": [selected["id"]],
            },
        ).status_code
        == 404
    )


def test_database_rejects_cross_project_knowledge_set(index_api):
    client, engine, p, q, _ = index_api
    prepared(client, engine, p)
    index = create(client, p)
    prepared(client, engine, q)
    foreign_index = create(client, q)
    client.post(f"/api/projects/{q}/indexes/{foreign_index['id']}/cancel")
    foreign_set = client.get(f"/api/projects/{q}/knowledge-sets").json()["items"][0]
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.execute(
            update(IndexVersion)
            .where(IndexVersion.id == UUID(index["id"]))
            .values(knowledge_set_id=UUID(foreign_set["id"]), version=2)
        )
        session.commit()
    with Session(engine) as session:
        own_set = session.get(KnowledgeSet, UUID(index["knowledge_set_id"]))
        with pytest.raises(IntegrityError):
            own_set.current_ready_index_id = UUID(foreign_index["id"])
            session.commit()


def test_partial_failure_resume_and_no_publication(index_api, monkeypatch):
    client, engine, p, _, provider = index_api
    prepared(client, engine, p)
    index = create(client, p)
    id = UUID(index["id"])
    monkeypatch.setattr("app.workers.indexing.BATCH_SIZE", 1)
    process_index(id, engine)
    with Session(engine) as session:
        assert session.get(IndexVersion, id).embedded_count == 1
    assert search(client, p, index).status_code == 409
    with patch.object(
        provider,
        "embed",
        side_effect=embeddings.EmbeddingError("Temporary failure.", transient=True),
    ):
        process_index(id, engine)
    with Session(engine) as session:
        assert session.get(IndexVersion, id).status == "queued"
        assert session.get(IndexVersion, id).failures == 1
    process_index(id, engine)
    process_index(id, engine)
    assert all("abcd" not in texts for texts in provider.calls[1:])
    assert search(client, p, index).status_code == 200


def test_invalid_dimensions_fail_without_publishing(index_api):
    client, engine, p, _, provider = index_api
    prepared(client, engine, p)
    index = create(client, p)
    with patch.object(provider, "embed", return_value=[[1, 2]] * 3):
        process_index(UUID(index["id"]), engine)
    route = f"/api/projects/{p}/indexes/{index['id']}"
    assert client.get(route).json()["status"] == "failed"
    assert search(client, p, index).status_code == 409
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(IndexChunk)
                .where(
                    IndexChunk.index_id == UUID(index["id"]),
                    IndexChunk.embedding.is_not(None),
                )
            )
            == 0
        )
    assert create(client, p)["version"] == 2


def test_cancellation_fences_inflight_batch(index_api):
    client, engine, p, _, provider = index_api
    prepared(client, engine, p)
    index = create(client, p)
    route = f"/api/projects/{p}/indexes/{index['id']}"

    def cancel(texts):
        assert client.post(route + "/cancel").json()["status"] == "cancelled"
        return [[1, 0, 0]] * len(texts)

    with patch.object(provider, "embed", side_effect=cancel):
        process_index(UUID(index["id"]), engine)
    result = client.get(route).json()
    assert result["embedded_count"] == 0 and result["status"] == "cancelled"
    process_index(UUID(index["id"]), engine)
    assert client.get(route).json()["attempts"] == 1
    assert search(client, p, index).status_code == 409


def test_stale_recovery_fences_old_attempt_and_broker_outage(index_api):
    client, engine, p, _, provider = index_api
    prepared(client, engine, p)
    index = create(client, p)
    id = UUID(index["id"])
    with pytest.raises(OSError):
        dispatch_indexes_once(engine, send=lambda _: (_ for _ in ()).throw(OSError()))

    def stale(texts):
        with Session(engine) as session:
            session.execute(
                update(IndexVersion)
                .where(IndexVersion.id == id)
                .values(started_at=now() - timedelta(seconds=181))
            )
            session.commit()
        sent = []
        dispatch_indexes_once(engine, send=sent.append)
        assert sent == [id]
        with patch.object(provider, "embed", return_value=[[0, 1, 0]] * len(texts)):
            process_index(id, engine)
        return [[1, 0, 0]] * len(texts)

    with patch.object(provider, "embed", side_effect=stale):
        process_index(id, engine)
    with Session(engine) as session:
        assert session.get(IndexVersion, id).status == "succeeded"
        values = session.scalars(
            select(IndexChunk.embedding).where(IndexChunk.index_id == id)
        ).all()
        assert all(v.tolist() == [0, 1, 0] for v in values)


def test_bounded_retries_and_concurrent_delivery(index_api):
    client, engine, p, _, provider = index_api
    prepared(client, engine, p)
    index = create(client, p)
    with patch.object(
        provider,
        "embed",
        side_effect=embeddings.EmbeddingError("Unavailable.", transient=True),
    ):
        for _ in range(5):
            process_index(UUID(index["id"]), engine)
    with Session(engine) as session:
        result = session.get(IndexVersion, UUID(index["id"]))
        assert result.status == "failed" and result.attempts == result.failures == 3
    retry = create(client, p)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(process_index, UUID(retry["id"]), engine) for _ in range(2)
        ]
        for future in futures:
            future.result(timeout=10)
    with Session(engine) as session:
        assert session.get(IndexVersion, UUID(retry["id"])).attempts == 1


@pytest.mark.parametrize(
    "values",
    [
        {"query": " "},
        {"query": "a" * 8001},
        {"top_k": 0},
        {"top_k": 51},
        {"top_k": True},
        {"top_k": 1.5},
        {"top_k": "2"},
        {"extra": "value"},
    ],
)
def test_retrieval_validation(index_api, values):
    client, _, p, _, _ = index_api
    assert search(client, p, {"id": str(uuid4())}, **values).status_code == 422


def test_configuration_unavailable_and_incompatible(index_api, monkeypatch):
    client, engine, p, _, _ = index_api
    prepared(client, engine, p)
    index = create(client, p)
    process_index(UUID(index["id"]), engine)
    # Restore real adapter configuration gate; no provider network call should run.
    monkeypatch.undo()
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr(""))
    route = f"/api/projects/{p}"
    assert client.post(route + "/indexes").status_code == 503
    assert client.get(route + "/embedding-settings").json()["configured"] is False
    assert search(client, p, index).status_code == 503
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("test-secret"))
    monkeypatch.setattr(settings, "embedding_dimensions", 2)
    assert search(client, p, index).status_code == 503


def test_empty_index_and_database_dimension_constraints(index_api):
    client, engine, p, _, _ = index_api
    assert client.post(f"/api/projects/{p}/indexes").status_code == 409
    prepared(client, engine, p)
    index = create(client, p)
    with Session(engine) as session:
        with pytest.raises(IntegrityError):
            session.execute(
                update(IndexChunk)
                .where(IndexChunk.index_id == UUID(index["id"]))
                .values(embedding=[1, 2])
            )
            session.commit()
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                update(IndexChunk)
                .where(IndexChunk.index_id == UUID(index["id"]))
                .values(embedding=[0, 0, 0])
            )
            session.commit()
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                update(IndexVersion)
                .where(IndexVersion.id == UUID(index["id"]))
                .values(status="succeeded")
            )
            session.commit()


@pytest.mark.parametrize(
    "vectors",
    [
        [],
        [[1, 2]],
        [[0, 0, 0]],
        [[1, float("nan"), 0]],
        [[1, float("inf"), 0]],
        [[True, 0, 0]],
        [["1", 0, 0]],
        [[1e40, 0, 0]],
    ],
)
def test_vector_validation(vectors):
    with pytest.raises(embeddings.EmbeddingError):
        embeddings.validate_vectors(vectors, 1, 3)


def test_openrouter_adapter_request_and_response_order(embedding_config):
    def respond(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/embeddings"
        assert request.headers["Authorization"] == "Bearer test-only-secret"
        body = json.loads(request.content)
        assert body == {
            "model": "openai/text-embedding-3-small",
            "dimensions": 3,
            "encoding_format": "float",
            "input": ["a", "b"],
        }
        return httpx.Response(
            200,
            json={
                "model": embedding_config.model,
                "data": [
                    {"index": 1, "embedding": [0, 1, 0]},
                    {"index": 0, "embedding": [1, 0, 0]},
                ],
            },
        )

    provider = OpenRouterEmbeddings(
        embedding_config, transport=httpx.MockTransport(respond)
    )
    assert provider.embed(["a", "b"]) == [[1, 0, 0], [0, 1, 0]]


@pytest.mark.parametrize(
    "status,transient",
    [
        (401, False),
        (402, False),
        (403, False),
        (400, False),
        (429, True),
        (500, True),
        (302, False),
    ],
)
def test_adapter_safe_errors_and_no_internal_retry(embedding_config, status, transient):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, text="private text and credentials")

    provider = OpenRouterEmbeddings(
        embedding_config, transport=httpx.MockTransport(respond)
    )
    with pytest.raises(embeddings.EmbeddingError) as error:
        provider.embed(["text"])
    assert error.value.transient is transient
    assert "private" not in str(error.value) and len(calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"model": "other", "data": []},
        {
            "model": "openai/text-embedding-3-small",
            "data": [{"index": 1, "embedding": [1, 0, 0]}],
        },
        {
            "model": "openai/text-embedding-3-small",
            "data": [{"index": 0, "embedding": [1, 0]}],
        },
    ],
)
def test_adapter_malformed_response(embedding_config, payload):
    provider = OpenRouterEmbeddings(
        embedding_config,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )
    with pytest.raises(embeddings.EmbeddingError):
        provider.embed(["text"])


def test_adapter_input_bound(embedding_config):
    provider = OpenRouterEmbeddings(
        embedding_config,
        transport=httpx.MockTransport(
            lambda _: pytest.fail("Must reject before sending.")
        ),
    )
    for texts in [[], [" "], ["a" * 8192], ["😀" * 2048], ["a"] * 17]:
        with pytest.raises(embeddings.EmbeddingError):
            provider.embed(texts)


def test_vector_extension(database):
    engine, _ = database
    with engine.connect() as conn:
        assert conn.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )


def test_limiter_budget_and_unavailability(monkeypatch):
    from unittest.mock import MagicMock
    from redis import RedisError
    from app.providers.rate_limit import reserve_request

    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(
        "app.providers.rate_limit.Redis.from_url", lambda *a, **kw: connection
    )
    monkeypatch.setattr(settings, "embedding_requests_per_minute", 2)
    connection.eval.side_effect = [1, 2, 3, RedisError("private details")]
    reserve_request()
    reserve_request()
    with pytest.raises(embeddings.EmbeddingError, match="budget"):
        reserve_request()
    with pytest.raises(embeddings.EmbeddingError, match="unavailable") as error:
        reserve_request()
    assert "private" not in str(error.value)


def test_adapter_timeout_is_transient(embedding_config):
    def timeout(request):
        raise httpx.ReadTimeout("private endpoint")

    with pytest.raises(embeddings.EmbeddingError) as error:
        OpenRouterEmbeddings(
            embedding_config, transport=httpx.MockTransport(timeout)
        ).embed(["text"])
    assert error.value.transient and "private" not in str(error.value)


@pytest.mark.parametrize(
    "returned_model,accepted",
    [
        ("openai/text-embedding-3-small", True),
        ("text-embedding-3-small", True),
        ("text-embedding-3-large", False),
        ("openai/text-embedding-3-large", False),
        ("other/text-embedding-3-small", False),
        (None, False),
    ],
)
def test_exact_upstream_model_alias(embedding_config, returned_model, accepted):
    payload = {"model": returned_model, "data": [{"index": 0, "embedding": [1, 0, 0]}]}
    provider = OpenRouterEmbeddings(
        embedding_config,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )
    if accepted:
        assert provider.embed(["test"]) == [[1, 0, 0]]
    else:
        with pytest.raises(embeddings.EmbeddingError, match="different model"):
            provider.embed(["test"])
